"""
TradeBot Pro v10 – Optimierte Signallogik, Marktphasenfilter, korrektes Risk Management
Verbesserungen:
 - ADX-basierte Marktphasenerkennung (Trend vs. Seitwärts)
 - Konfirmationslogik: mind. 2 von 3 unabhängigen Indikatorgruppen
 - Stop-Loss an S1/S2 Pivot-Levels orientiert (mit Min/Max-Abstandsgrenzen)
 - Korrektes Position Sizing (2% Risiko-pro-Trade statt fehlerhafter Formel)
 - Volatilitätsfilter: ATR% > 5% → Score-Reduktion + Warnung
 - Portfolio-Risikolimits: max. 5 Positionen, max. 40% Exposure
 - Analysten-Rating NUR als Info, nicht im Score
 - Zeitraum quick_score: 6mo (statt 3mo) für stabilere Indikatoren
 - /api/price Endpoint für Live-Kurs-Updates
 - /api/portfolio/reset Endpoint
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import numpy as np
import json, os
from datetime import datetime
from pathlib import Path
from threading import Thread, Lock

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ORDER_FEE = 10.0        # € pro Trade (Kauf oder Verkauf)
MAX_POSITIONS = 5       # Maximale gleichzeitige Positionen
MAX_EXPOSURE_PCT = 0.40 # Maximal 40% des Portfolios in offenen Positionen
RISK_PER_TRADE = 0.02   # 2% Kapitalrisiko pro Trade
MAX_POSITION_PCT = 0.20 # Maximale Positionsgröße: 20% des Portfolios
MIN_SL_DIST_PCT = 0.015 # Mindest-SL-Abstand: 1,5%
MAX_SL_DIST_PCT = 0.08  # Maximal-SL-Abstand: 8%

ALL_TICKERS = {
    # Indizes (handelbar als CFD/Mini-Future)
    "DAX Index": "^GDAXI",
    "Euro Stoxx 50": "^STOXX50E",
    "FTSE 100": "^FTSE",
    "CAC 40": "^FCHI",
    "IBEX 35": "^IBEX",
    "AEX": "^AEX",
    "SMI": "^SSMI",
    # DAX 40 Werte
    "Adidas": "ADS.DE",
    "Airbus": "AIR.DE",
    "Allianz": "ALV.DE",
    "BASF": "BAS.DE",
    "Bayer": "BAYN.DE",
    "Beiersdorf": "BEI.DE",
    "BMW": "BMW.DE",
    "Brenntag": "BNR.DE",
    "Continental": "CON.DE",
    "Covestro": "1COV.DE",
    "Deutsche Post": "DHL.DE",
    "Telekom": "DTE.DE",
    "EON": "EOAN.DE",
    "Fresenius Med": "FME.DE",
    "Fresenius": "FRE.DE",
    "Heidelberg Mat": "HEI.DE",
    "Henkel": "HEN3.DE",
    "Infineon": "IFX.DE",
    "Linde": "LIN.DE",
    "Mercedes": "MBG.DE",
    "Merck": "MRK.DE",
    "MTU Aero": "MTX.DE",
    "Munich Re": "MUV2.DE",
    "Porsche AG": "P911.DE",
    "Qiagen": "QIA.DE",
    "Rheinmetall": "RHM.DE",
    "RWE": "RWE.DE",
    "SAP": "SAP.DE",
    "Siemens Health": "SHL.DE",
    "Siemens": "SIE.DE",
    "Symrise": "SY1.DE",
    "VW": "VOW3.DE",
    "Vonovia": "VNA.DE",
    "Zalando": "ZAL.DE",
    "Deutsche Bank": "DBK.DE",
    "Commerzbank": "CBK.DE",
    "Hannover Rueck": "HNR1.DE",
    "Sartorius": "SRT3.DE",
    # Euro Stoxx 50 weitere
    "ASML": "ASML.AS",
    "ING": "INGA.AS",
    "Ahold": "AD.AS",
    "LVMH": "MC.PA",
    "LOreal": "OR.PA",
    "TotalEnergies": "TTE.PA",
    "Sanofi": "SAN.PA",
    "BNP Paribas": "BNP.PA",
    "Kering": "KER.PA",
    "Airbus FR": "AIR.PA",
    "Santander": "SAN.MC",
    "BBVA": "BBVA.MC",
    "Inditex": "ITX.MC",
    "Nestle": "NESN.SW",
    "Roche": "ROG.SW",
    "Novartis": "NOVN.SW",
    "ABB": "ABBN.SW",
    "AstraZeneca": "AZN.L",
    "HSBC": "HSBA.L",
    "BP": "BP.L",
    "Shell": "SHEL.L",
    "GSK": "GSK.L",
    "Unilever": "ULVR.L",
    "Enel": "ENEL.MI",
    "ENI": "ENI.MI",
    "UniCredit": "UCG.MI",
    "STMicro": "STM.MI",
}

PORTFOLIO_FILE = "/tmp/portfolio.json"
SETTINGS_FILE  = "/tmp/settings.json"

_lock  = Lock()
_state = {"status": "idle", "progress": 0, "results": [], "timestamp": None}

# ── Persistenz ────────────────────────────────────────────────────────────────
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f: return json.load(f)
    return {"min_strength": 20}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f: json.dump(s, f)

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {"cash": 10000.0, "start_capital": 10000.0,
            "positions": [], "closed_trades": [],
            "created": datetime.now().isoformat()}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f: json.dump(p, f)

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def calc_smart_stoploss(price: float, direction: str, atr: float,
                        s1: float, s2: float, r1: float, r2: float) -> float:
    """
    Stop-Loss orientiert an S1/S2 (BUY) bzw. R1/R2 (SELL).
    Fallback auf ATR-basiert wenn Pivot-Level zu weit oder zu nah.
    Erzwingt Min-Abstand 1,5% und Max-Abstand 8%.
    """
    min_dist = price * MIN_SL_DIST_PCT
    max_dist = price * MAX_SL_DIST_PCT

    if direction == "BUY":
        # Bevorzuge S1 als SL-Level (etwas darunter)
        candidates = []
        for level in [s1, s2]:
            if level > 0 and level < price:
                sl = round(level * 0.998, 2)  # 0,2% unter dem Support
                dist = price - sl
                if min_dist <= dist <= max_dist:
                    candidates.append(sl)
        if candidates:
            return max(candidates)  # nehme den nächsten validen Support
        # Fallback ATR
        atr_sl = round(price - 1.5 * atr, 2)
        dist = price - atr_sl
        if dist < min_dist: atr_sl = round(price - min_dist, 2)
        if dist > max_dist: atr_sl = round(price - max_dist, 2)
        return atr_sl
    else:
        candidates = []
        for level in [r1, r2]:
            if level > price:
                sl = round(level * 1.002, 2)
                dist = sl - price
                if min_dist <= dist <= max_dist:
                    candidates.append(sl)
        if candidates:
            return min(candidates)
        atr_sl = round(price + 1.5 * atr, 2)
        dist = atr_sl - price
        if dist < min_dist: atr_sl = round(price + min_dist, 2)
        if dist > max_dist: atr_sl = round(price + max_dist, 2)
        return atr_sl


def calc_position_size(portfolio_cash: float, portfolio_total: float,
                       price: float, stop_loss: float,
                       invest_amount: float = 0) -> tuple:
    """
    Korrektes Position Sizing:
    - Risikiere max. 2% des Gesamtkapitals pro Trade
    - Maximale Positionsgröße: 20% des Portfolios
    - Gibt (units, cost) zurück
    """
    distance = abs(price - stop_loss)
    if distance <= 0:
        distance = price * 0.02  # Fallback: 2% Abstand

    if invest_amount > 0:
        # Nutzer hat manuell einen Betrag eingegeben
        cost = round(min(invest_amount, portfolio_cash - ORDER_FEE,
                         portfolio_total * MAX_POSITION_PCT), 2)
    else:
        # Risk-based sizing: risk_amount = Gesamtkapital * 2%
        risk_amount = portfolio_total * RISK_PER_TRADE
        units_by_risk = risk_amount / distance
        cost_by_risk = units_by_risk * price
        # Deckelung auf MAX_POSITION_PCT des Portfolios
        max_cost = portfolio_total * MAX_POSITION_PCT
        cost = round(min(cost_by_risk, max_cost, portfolio_cash - ORDER_FEE), 2)

    cost = max(cost, 0.01)
    units = round(cost / price, 4)
    return units, cost


# ── Vollständige Analyse (Detail-Modal) ───────────────────────────────────────
def full_analysis(ticker, name, min_strength=0):
    try:
        df = yf.download(ticker, period="1y", interval="1d",
                         progress=False, auto_adjust=True, timeout=12)
        if df is None or df.empty or len(df) < 60:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c  = df["Close"].squeeze()
        h  = df["High"].squeeze()
        l  = df["Low"].squeeze()
        v  = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)), index=c.index)

        price = float(c.iloc[-1])
        indicators = {}
        warnings = []

        # ── ATR & Volatilität (zuerst berechnen – wird für SL und Score benötigt) ─
        tr    = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = atr14 / price * 100
        indicators["ATR (14)"]  = round(atr14, 2)
        indicators["ATR %"]     = f"{atr_pct:.2f}%"
        high_volatility = atr_pct > 5.0

        # ── ADX (Trendstärke – bestimmt Marktphase) ───────────────────────────
        up_move   = h.diff()
        down_move = -l.diff()
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        ndm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        pdi = 100 * pd.Series(pdm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0, np.nan)
        ndi = 100 * pd.Series(ndm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0, np.nan)
        dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        adx = float(dx.rolling(14).mean().iloc[-1])
        pdi_val = float(pdi.iloc[-1])
        ndi_val = float(ndi.iloc[-1])
        indicators["ADX"]  = round(adx, 1)
        indicators["+DI"]  = round(pdi_val, 1)
        indicators["-DI"]  = round(ndi_val, 1)

        trending_market    = adx >= 25   # Trendmarkt
        sideways_market    = adx < 20    # Seitwärtsmarkt
        trend_is_up        = pdi_val > ndi_val
        trend_is_down      = ndi_val > pdi_val

        # ── RSI ───────────────────────────────────────────────────────────────
        delta = c.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = float((100 - 100/(1 + gain/loss.replace(0, np.nan))).iloc[-1])
        indicators["RSI (14)"] = round(rsi, 1)

        # ── MACD ──────────────────────────────────────────────────────────────
        e12         = c.ewm(span=12, adjust=False).mean()
        e26         = c.ewm(span=26, adjust=False).mean()
        macd_line   = e12 - e26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist        = macd_line - signal_line
        mk, ms      = float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
        mh, mhp     = float(hist.iloc[-1]), float(hist.iloc[-2])
        indicators["MACD"]        = round(mk, 4)
        indicators["MACD Signal"] = round(ms, 4)

        # ── Bollinger Bands ───────────────────────────────────────────────────
        sma20     = c.rolling(20).mean()
        std20     = c.rolling(20).std()
        bb_upper  = sma20 + 2*std20
        bb_lower  = sma20 - 2*std20
        pb        = float(((c - bb_lower)/(bb_upper - bb_lower)).iloc[-1])
        indicators["BB %B"]    = round(pb, 2)
        indicators["BB Upper"] = round(float(bb_upper.iloc[-1]), 2)
        indicators["BB Lower"] = round(float(bb_lower.iloc[-1]), 2)

        # ── Stochastic ────────────────────────────────────────────────────────
        ll_14    = l.rolling(14).min()
        hh_14    = h.rolling(14).max()
        stoch_k  = 100*(c - ll_14)/(hh_14 - ll_14).replace(0, np.nan)
        stoch_d  = stoch_k.rolling(3).mean()
        sk, sd   = float(stoch_k.iloc[-1]), float(stoch_d.iloc[-1])
        indicators["Stoch %K"] = round(sk, 1)
        indicators["Stoch %D"] = round(sd, 1)

        # ── EMAs ──────────────────────────────────────────────────────────────
        e20  = float(c.ewm(span=20).mean().iloc[-1])
        e50  = float(c.ewm(span=50).mean().iloc[-1])
        e100 = float(c.ewm(span=100).mean().iloc[-1])
        e200 = float(c.ewm(span=200).mean().iloc[-1]) if len(c) >= 200 else None
        indicators["EMA 20"]  = round(e20, 2)
        indicators["EMA 50"]  = round(e50, 2)
        indicators["EMA 100"] = round(e100, 2)
        if e200: indicators["EMA 200"] = round(e200, 2)

        # ── Williams %R ───────────────────────────────────────────────────────
        hh14  = h.rolling(14).max()
        ll14  = l.rolling(14).min()
        willr = float((-100*(hh14 - c)/(hh14 - ll14).replace(0, np.nan)).iloc[-1])
        indicators["Williams %R"] = round(willr, 1)

        # ── CCI ───────────────────────────────────────────────────────────────
        tp_  = (h + l + c) / 3
        cci  = float(((tp_ - tp_.rolling(20).mean()) / (0.015 * tp_.rolling(20).std())).iloc[-1])
        indicators["CCI (20)"] = round(cci, 1)

        # ── OBV ───────────────────────────────────────────────────────────────
        obv      = (np.sign(c.diff()) * v).fillna(0).cumsum()
        obv_ema  = obv.ewm(span=20).mean()
        obv_bull = float(obv.iloc[-1]) > float(obv_ema.iloc[-1])
        indicators["OBV Trend"] = "Bullisch" if obv_bull else "Bärisch"

        # ── Pivot Points ──────────────────────────────────────────────────────
        prev_h = float(h.iloc[-2])
        prev_l = float(l.iloc[-2])
        prev_c = float(c.iloc[-2])
        pivot  = (prev_h + prev_l + prev_c) / 3
        r1 = 2*pivot - prev_l
        r2 = pivot + (prev_h - prev_l)
        s1 = 2*pivot - prev_h
        s2 = pivot - (prev_h - prev_l)
        indicators["Pivot"] = round(pivot, 2)
        indicators["R1"]    = round(r1, 2)
        indicators["R2"]    = round(r2, 2)
        indicators["S1"]    = round(s1, 2)
        indicators["S2"]    = round(s2, 2)

        # ── 52-Wochen ─────────────────────────────────────────────────────────
        w52_high = float(h.rolling(252).max().iloc[-1])
        w52_low  = float(l.rolling(252).min().iloc[-1])
        w52_pct  = round((price - w52_low)/(w52_high - w52_low)*100, 1) if w52_high != w52_low else 50
        indicators["52W Hoch"]     = round(w52_high, 2)
        indicators["52W Tief"]     = round(w52_low, 2)
        indicators["52W Position"] = f"{w52_pct}%"

        # ── ROC ───────────────────────────────────────────────────────────────
        roc10 = float(((c - c.shift(10))/c.shift(10)*100).iloc[-1])
        indicators["ROC (10)"] = f"{roc10:.1f}%"

        # ── Analysten-Ratings (nur als Info, NICHT im Score) ──────────────────
        analyst_info = {}
        try:
            t_obj  = yf.Ticker(ticker)
            info   = t_obj.info
            rec    = info.get("recommendationMean")
            n_anal = info.get("numberOfAnalystOpinions", 0)
            target = info.get("targetMeanPrice")
            if rec and n_anal:
                rec_text = {1:"Starker Kauf", 2:"Kauf", 3:"Halten",
                            4:"Verkauf", 5:"Starker Verkauf"}.get(round(rec), f"{rec:.1f}")
                analyst_info = {
                    "recommendation": rec_text,
                    "analysts": n_anal,
                    "target": round(target, 2) if target else None
                }
                indicators["Analysten"] = f"{rec_text} ({n_anal} Analysten) ℹ️"
                if target: indicators["Kursziel"] = f"{target:.2f} (nur Info)"
        except:
            pass

        # ══════════════════════════════════════════════════════════════════════
        # SCORING – 3 unabhängige Gruppen + Konfirmationslogik
        # ══════════════════════════════════════════════════════════════════════
        #
        # Gruppe A: Momentum-Oszillatoren (RSI, Stoch, Williams %R, CCI, BB)
        #   → gut in Seitwärtsmärkten
        # Gruppe B: Trendfolger (MACD, EMA-Struktur)
        #   → gut in Trenmärkten
        # Gruppe C: Volumen + Marktstruktur (OBV, 52W-Position, Pivot, ROC)
        #   → immer relevant
        #
        # Signal gültig wenn: mind. 2 von 3 Gruppen in dieselbe Richtung zeigen
        # ADX < 20: Trendfolger-Signale (B) werden ignoriert
        # ADX > 25: Oszillator-Gegensignale (A) werden auf 50% reduziert
        # ATR% > 5%: Score insgesamt um 50% reduziert + Warnung
        # ══════════════════════════════════════════════════════════════════════

        score_a = 0  # Momentum/Oszillatoren
        score_b = 0  # Trendfolger
        score_c = 0  # Volumen/Marktstruktur
        signals = []

        # ── Gruppe A: Momentum-Oszillatoren ───────────────────────────────────
        # RSI
        if rsi < 30:   score_a += 20; signals.append(f"RSI überverkauft ({rsi:.0f})")
        elif rsi < 40: score_a += 10; signals.append(f"RSI schwach ({rsi:.0f})")
        elif rsi > 70: score_a -= 20; signals.append(f"RSI überkauft ({rsi:.0f})")
        elif rsi > 60: score_a -= 10; signals.append(f"RSI stark ({rsi:.0f})")

        # Bollinger Bands
        if pb < 0.05:   score_a += 20; signals.append("Unteres Bollinger Band")
        elif pb < 0.2:  score_a += 10; signals.append("Nahe unterem BB")
        elif pb > 0.95: score_a -= 20; signals.append("Oberes Bollinger Band")
        elif pb > 0.8:  score_a -= 10; signals.append("Nahe oberem BB")

        # Stochastic
        if sk < 20 and sk > sd:   score_a += 15; signals.append(f"Stochastik dreht hoch ({sk:.0f})")
        elif sk > 80 and sk < sd: score_a -= 15; signals.append(f"Stochastik dreht runter ({sk:.0f})")

        # Williams %R
        if willr < -80:  score_a += 10; signals.append(f"Williams %R überverkauft ({willr:.0f})")
        elif willr > -20: score_a -= 10; signals.append(f"Williams %R überkauft ({willr:.0f})")

        # CCI
        if cci < -100:  score_a += 10; signals.append(f"CCI überverkauft ({cci:.0f})")
        elif cci > 100: score_a -= 10; signals.append(f"CCI überkauft ({cci:.0f})")

        # In Trenmärkten Oszillator-Gegensignale dämpfen
        if trending_market:
            if (trend_is_up and score_a < 0) or (trend_is_down and score_a > 0):
                score_a = int(score_a * 0.5)
                signals.append(f"⚠️ Trendmarkt (ADX {adx:.0f}): Gegen-Trend Oszillator-Signale gedämpft")

        # ── Gruppe B: Trendfolger ─────────────────────────────────────────────
        # MACD
        if mk > ms and mh > mhp: score_b += 20; signals.append("MACD bullisch ↑")
        elif mk < ms and mh < mhp: score_b -= 20; signals.append("MACD bärisch ↓")

        # EMA-Struktur
        if price > e20 > e50 > e100:   score_b += 15; signals.append("Starker Auftrend (EMA 20>50>100)")
        elif price > e20 > e50:         score_b += 10; signals.append("Auftrend EMA 20/50")
        elif price < e20 < e50 < e100: score_b -= 15; signals.append("Starker Abtrend (EMA 20<50<100)")
        elif price < e20 < e50:         score_b -= 10; signals.append("Abtrend EMA 20/50")
        if e200:
            if price > e200: score_b += 5;  signals.append("Über EMA 200 (Langzeittrend bullisch)")
            else:            score_b -= 5;  signals.append("Unter EMA 200 (Langzeittrend bärisch)")

        # ADX-Verstärker für Trendfolger
        if trending_market:
            if trend_is_up:   score_b += 10; signals.append(f"ADX starker Auftrend ({adx:.0f})")
            else:             score_b -= 10; signals.append(f"ADX starker Abtrend ({adx:.0f})")
        elif sideways_market:
            # In Seitwärtsmärkten Trendfolger-Signale ignorieren
            score_b = 0
            signals.append(f"⚠️ Seitwärtsmarkt (ADX {adx:.0f}): Trendfolger-Signale deaktiviert")
        else:
            signals.append(f"ADX schwacher Trend ({adx:.0f})")

        # ── Gruppe C: Volumen & Marktstruktur ─────────────────────────────────
        # OBV
        if obv_bull: score_c += 5;  signals.append("OBV: Kaufvolumen steigt")
        else:        score_c -= 5;  signals.append("OBV: Verkaufsvolumen steigt")

        # 52-Wochen-Position
        if w52_pct < 15:   score_c += 10; signals.append(f"Nahe 52W-Tief ({w52_pct:.0f}%)")
        elif w52_pct > 85: score_c -= 10; signals.append(f"Nahe 52W-Hoch ({w52_pct:.0f}%)")

        # Pivot Points
        if price < s1:   score_c += 8;  signals.append(f"Unter S1 ({s1:.2f}) – mögliche Bounce-Zone")
        elif price > r1: score_c -= 8;  signals.append(f"Über R1 ({r1:.2f}) – möglicher Widerstand")

        # ROC
        if roc10 > 5:   score_c -= 5; signals.append(f"Starkes positives Momentum (+{roc10:.1f}%)")
        elif roc10 < -5: score_c += 5; signals.append(f"Starkes negatives Momentum ({roc10:.1f}%)")

        # ── Konfirmationslogik: mind. 2 von 3 Gruppen müssen übereinstimmen ───
        groups_up   = sum(1 for s in [score_a, score_b, score_c] if s > 0)
        groups_down = sum(1 for s in [score_a, score_b, score_c] if s < 0)

        if groups_up < 2 and groups_down < 2:
            # Keine ausreichende Konfirmation → kein Signal
            return None

        total_score = score_a + score_b + score_c
        direction_raw = "BUY" if total_score > 0 else "SELL"

        # Richtungsprüfung: Alle drei Gruppen-Richtungen müssen konsistent sein
        # (mind. 2 von 3 in dieselbe Richtung wie total_score)
        confirming = groups_up if direction_raw == "BUY" else groups_down
        if confirming < 2:
            return None

        # ── Volatilitätsfilter ────────────────────────────────────────────────
        if high_volatility:
            total_score = int(total_score * 0.5)
            warnings.append(f"⚠️ Hohe Volatilität (ATR {atr_pct:.1f}%) – Score reduziert, erhöhtes Risiko!")
            signals.append(f"⚠️ Hohe Volatilität (ATR {atr_pct:.1f}%) – Vorsicht!")

        if abs(total_score) < min_strength:
            return None

        direction = "BUY" if total_score > 0 else "SELL"

        # ── Intelligenter Stop-Loss (Pivot-orientiert) ────────────────────────
        sl = calc_smart_stoploss(price, direction, atr14, s1, s2, r1, r2)
        tp_mult = 2.5 if not high_volatility else 2.0
        tp = round(price + tp_mult*(price - sl), 2) if direction == "BUY" else round(price - tp_mult*(sl - price), 2)

        # ── Marktphasen-Info für Frontend ─────────────────────────────────────
        market_phase = "Trendmarkt" if trending_market else ("Seitwärtsmarkt" if sideways_market else "Schwacher Trend")
        indicators["Marktphase"] = f"{market_phase} (ADX {adx:.0f})"
        if high_volatility:
            indicators["⚠️ Volatilität"] = f"ERHÖHT ({atr_pct:.1f}%) – Vorsicht!"

        # ── Chart-Daten (letzte 90 Tage) ─────────────────────────────────────
        chart_data = []
        df90      = df.tail(90)
        bb_u90    = (sma20 + 2*std20).tail(90)
        bb_m90    = sma20.tail(90)
        bb_l90    = (sma20 - 2*std20).tail(90)
        ema20_90  = c.ewm(span=20).mean().tail(90)
        ema50_90  = c.ewm(span=50).mean().tail(90)
        for i in range(len(df90)):
            try:
                chart_data.append({
                    "date":     df90.index[i].strftime("%Y-%m-%d"),
                    "open":     round(float(df90["Open"].iloc[i]), 2),
                    "high":     round(float(df90["High"].iloc[i]), 2),
                    "low":      round(float(df90["Low"].iloc[i]), 2),
                    "close":    round(float(df90["Close"].iloc[i]), 2),
                    "volume":   int(df90["Volume"].iloc[i]) if "Volume" in df90.columns else 0,
                    "bb_upper": round(float(bb_u90.iloc[i]), 2),
                    "bb_mid":   round(float(bb_m90.iloc[i]), 2),
                    "bb_lower": round(float(bb_l90.iloc[i]), 2),
                    "ema20":    round(float(ema20_90.iloc[i]), 2),
                    "ema50":    round(float(ema50_90.iloc[i]), 2),
                })
            except:
                pass

        return {
            "ticker": ticker, "name": name, "price": round(price, 2),
            "direction": direction, "score": int(total_score),
            "score_detail": {"momentum": int(score_a), "trend": int(score_b), "structure": int(score_c)},
            "strength": min(100, abs(int(total_score))),
            "confirming_groups": confirming,
            "market_phase": market_phase,
            "high_volatility": high_volatility,
            "signals": signals, "warnings": warnings,
            "stop_loss": sl, "take_profit": tp,
            "rsi": round(rsi, 1), "atr": round(atr14, 2),
            "indicators": indicators, "analyst": analyst_info,
            "chart_data": chart_data,
            "support_levels": [round(s1, 2), round(s2, 2)],
            "resistance_levels": [round(r1, 2), round(r2, 2)],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return None


# ── Quick-Score (Scan aller Ticker, 6mo für stabile Indikatoren) ──────────────
def quick_score(ticker, name, min_strength):
    import gc
    try:
        # 6 Monate statt 3 → stabilere Indikatoren (besonders EMA 50, ADX)
        df = yf.download(ticker, period="6mo", interval="1d",
                         progress=False, auto_adjust=True, timeout=8)
        if df is None or df.empty or len(df) < 60:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        price = float(c.iloc[-1])

        # ATR & Volatilität
        tr   = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        atr  = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = atr / price * 100
        high_vol = atr_pct > 5.0

        # ADX – Marktphasenerkennung
        up_move   = h.diff()
        down_move = -l.diff()
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        ndm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        pdi = 100 * pd.Series(pdm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0, np.nan)
        ndi = 100 * pd.Series(ndm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0, np.nan)
        dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        adx = float(dx.rolling(14).mean().iloc[-1])
        pdi_v, ndi_v = float(pdi.iloc[-1]), float(ndi.iloc[-1])
        trending = adx >= 25
        sideways = adx < 20

        # RSI
        delta = c.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = float((100 - 100/(1 + gain/loss.replace(0, np.nan))).iloc[-1])

        # MACD
        e12 = c.ewm(span=12, adjust=False).mean()
        e26 = c.ewm(span=26, adjust=False).mean()
        ml  = e12 - e26
        sl2 = ml.ewm(span=9, adjust=False).mean()
        hs  = ml - sl2
        mk, ms, mh, mhp = float(ml.iloc[-1]), float(sl2.iloc[-1]), float(hs.iloc[-1]), float(hs.iloc[-2])

        # Bollinger
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        pb    = float(((c - (sma20 - 2*std20))/(4*std20)).iloc[-1])

        # Stochastic
        sk_s = 100*(c - l.rolling(14).min())/(h.rolling(14).max() - l.rolling(14).min()).replace(0, np.nan)
        sk   = float(sk_s.iloc[-1])
        sd   = float(sk_s.rolling(3).mean().iloc[-1])

        # EMA
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        e50 = float(c.ewm(span=50).mean().iloc[-1])

        # OBV
        v_col = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)), index=c.index)
        obv      = (np.sign(c.diff()) * v_col).fillna(0).cumsum()
        obv_bull = float(obv.iloc[-1]) > float(obv.ewm(span=20).mean().iloc[-1])

        # Pivot
        prev_h = float(h.iloc[-2]); prev_l = float(l.iloc[-2]); prev_c = float(c.iloc[-2])
        pivot  = (prev_h + prev_l + prev_c) / 3
        r1 = 2*pivot - prev_l
        s1 = 2*pivot - prev_h
        s2 = pivot - (prev_h - prev_l)
        r2 = pivot + (prev_h - prev_l)

        # Memory freigeben
        del df, c, h, l, tr, delta, gain, loss, e12, e26, ml, sl2, hs
        del sma20, std20, sk_s, up_move, down_move, pdm, ndm, pdi, ndi, v_col, obv
        gc.collect()

        # ── Scoring mit Konfirmationslogik ─────────────────────────────────────
        sa, sb, sc = 0, 0, 0
        signals = []

        # Gruppe A: Momentum
        if rsi < 30:    sa += 20; signals.append(f"RSI überverkauft ({rsi:.0f})")
        elif rsi < 40:  sa += 10; signals.append(f"RSI schwach ({rsi:.0f})")
        elif rsi > 70:  sa -= 20; signals.append(f"RSI überkauft ({rsi:.0f})")
        elif rsi > 60:  sa -= 10; signals.append(f"RSI stark ({rsi:.0f})")

        if pb < 0.05:   sa += 20; signals.append("Unteres Bollinger Band")
        elif pb < 0.2:  sa += 10; signals.append("Nahe unterem BB")
        elif pb > 0.95: sa -= 20; signals.append("Oberes Bollinger Band")
        elif pb > 0.8:  sa -= 10; signals.append("Nahe oberem BB")

        if sk < 20 and sk > sd:   sa += 15; signals.append(f"Stochastik dreht hoch ({sk:.0f})")
        elif sk > 80 and sk < sd: sa -= 15; signals.append(f"Stochastik dreht runter ({sk:.0f})")

        if trending:
            if (pdi_v > ndi_v and sa < 0) or (ndi_v > pdi_v and sa > 0):
                sa = int(sa * 0.5)

        # Gruppe B: Trendfolger
        if mk > ms and mh > mhp:  sb += 20; signals.append("MACD bullisch ↑")
        elif mk < ms and mh < mhp: sb -= 20; signals.append("MACD bärisch ↓")

        if price > e20 > e50:   sb += 10; signals.append("Auftrend EMA")
        elif price < e20 < e50: sb -= 10; signals.append("Abtrend EMA")

        if trending:
            if pdi_v > ndi_v: sb += 10; signals.append(f"ADX Auftrend ({adx:.0f})")
            else:             sb -= 10; signals.append(f"ADX Abtrend ({adx:.0f})")
        elif sideways:
            sb = 0  # Trendfolger in Seitwärtsmärkten ignorieren

        # Gruppe C: Struktur
        if obv_bull: sc += 5;  signals.append("OBV bullisch")
        else:        sc -= 5;  signals.append("OBV bärisch")

        if price < s1: sc += 8;  signals.append(f"Unter S1 ({s1:.2f})")
        elif price > r1: sc -= 8; signals.append(f"Über R1 ({r1:.2f})")

        # Konfirmation
        g_up   = sum(1 for x in [sa, sb, sc] if x > 0)
        g_down = sum(1 for x in [sa, sb, sc] if x < 0)
        if g_up < 2 and g_down < 2:
            return None

        total = sa + sb + sc
        direction = "BUY" if total > 0 else "SELL"
        conf = g_up if direction == "BUY" else g_down
        if conf < 2:
            return None

        if high_vol:
            total = int(total * 0.5)
            signals.append(f"⚠️ Hohe Volatilität (ATR {atr_pct:.1f}%)")

        if abs(total) < min_strength:
            return None

        sl = calc_smart_stoploss(price, direction, atr, s1, s2, r1, r2)
        tp_m = 2.5 if not high_vol else 2.0
        tp = round(price + tp_m*(price - sl), 2) if direction == "BUY" else round(price - tp_m*(sl - price), 2)

        market_phase = "Trendmarkt" if trending else ("Seitwärtsmarkt" if sideways else "Schwacher Trend")

        return {
            "ticker": ticker, "name": name, "price": round(price, 2),
            "direction": direction, "score": int(total),
            "strength": min(100, abs(int(total))),
            "confirming_groups": conf,
            "market_phase": market_phase,
            "high_volatility": high_vol,
            "signals": signals, "warnings": [],
            "stop_loss": sl, "take_profit": tp,
            "rsi": round(rsi, 1), "atr": round(atr, 2),
            "indicators": {
                "RSI": round(rsi, 1), "MACD": round(mk, 4),
                "BB %B": round(pb, 2), "Stoch %K": round(sk, 1),
                "EMA 20": round(e20, 2), "EMA 50": round(e50, 2),
                "ADX": round(adx, 1), "ATR": round(atr, 2),
                "Marktphase": market_phase,
            },
            "analyst": {}, "chart_data": [],
            "support_levels": [round(s1, 2), round(s2, 2)],
            "resistance_levels": [round(r1, 2), round(r2, 2)],
            "timestamp": datetime.now().isoformat()
        }
    except Exception:
        return None


def run_analysis(min_strength):
    global _state
    import time, gc
    with _lock:
        if _state.get("status") == "running": return
        _state["status"] = "running"
        _state["progress"] = 0
        _state["results"] = []

    items = list(ALL_TICKERS.items())
    total = len(items)
    results = []

    for i, (name, ticker) in enumerate(items):
        sig = quick_score(ticker, name, min_strength)
        if sig:
            results.append(sig)
        results_sorted = sorted(results, key=lambda x: x["strength"], reverse=True)
        with _lock:
            _state["progress"] = round((i+1)/total*100)
            _state["results"]  = results_sorted[:15]
        if i % 5 == 4:
            time.sleep(0.5)
            gc.collect()

    with _lock:
        _state.update({
            "status": "done", "progress": 100,
            "results": results_sorted[:15] if results else [],
            "all_results": results_sorted if results else [],
            "signals_found": len(results),
            "total_analyzed": total,
            "timestamp": datetime.now().isoformat()
        })
    gc.collect()


# ── Mini Future Calculator ────────────────────────────────────────────────────
def calc_mini_futures(ticker: str, direction: str, price: float, atr: float):
    """Synthetische Mini-Future Kombinationen (simuliert, keine echten Produkte)"""
    products = []
    leverages = [2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 20, 22, 25, 28, 30]
    for lev in leverages:
        ko_distance_pct = 1.0 / lev
        if direction == "BUY":
            knock_out  = round(price * (1 - ko_distance_pct), 2)
            stop_loss  = round(knock_out * 1.005, 2)
            mf_price   = round((price - knock_out) * 1.02, 2)
            take_profit = round(price + 2 * atr, 2)
        else:
            knock_out  = round(price * (1 + ko_distance_pct), 2)
            stop_loss  = round(knock_out * 0.995, 2)
            mf_price   = round((knock_out - price) * 1.02, 2)
            take_profit = round(price - 2 * atr, 2)

        max_loss_pct    = round(ko_distance_pct * 100, 1)
        potential_gain  = round(atr * 2 * lev / mf_price * 100, 1) if mf_price > 0 else 0

        products.append({
            "leverage": lev, "direction": direction,
            "base_price": round(price, 2),
            "knock_out": knock_out, "stop_loss_level": stop_loss,
            "mini_future_price": mf_price, "take_profit": take_profit,
            "max_loss_pct": max_loss_pct, "potential_gain_pct": potential_gain,
            "risk_level": "Niedrig" if lev <= 5 else "Mittel" if lev <= 15 else "Hoch",
            "label": f"x{lev} {'Long' if direction=='BUY' else 'Short'} – KO: {knock_out}"
        })
    return products


# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/signals")
def get_signals():
    s = load_settings()
    min_str = s.get("min_strength", 20)
    with _lock:
        status   = _state.get("status", "idle")
        progress = _state.get("progress", 0)
        results  = _state.get("results", [])
        ts       = _state.get("timestamp")
        found    = _state.get("signals_found", len(results))
        analyzed = _state.get("total_analyzed", 0)
    if status == "idle":
        Thread(target=run_analysis, args=(min_str,), daemon=True).start()
        return {"status": "loading", "progress": 0,
                "top_signals": [], "total_analyzed": 0, "signals_found": 0}
    return {"status": status, "progress": progress, "top_signals": results,
            "total_analyzed": analyzed, "signals_found": found, "timestamp": ts}


@app.post("/api/signals/refresh")
def refresh_signals():
    global _state
    s = load_settings()
    min_str = s.get("min_strength", 20)
    with _lock:
        if _state.get("status") == "running":
            return {"status": "running", "message": "Analyse läuft bereits"}
        _state = {"status": "idle", "progress": 0, "results": [], "timestamp": None}
    Thread(target=run_analysis, args=(min_str,), daemon=True).start()
    return {"status": "loading", "message": "Neue Analyse gestartet"}


@app.get("/api/detail/{ticker}")
def get_detail(ticker: str):
    name   = next((k for k, v in ALL_TICKERS.items() if v == ticker), ticker)
    result = full_analysis(ticker, name, min_strength=0)
    if not result:
        raise HTTPException(404, f"Keine Daten für {ticker}")
    return result


@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    """Aktueller Kurs für ein einzelnes Instrument (für Portfolio Live-Updates)"""
    try:
        df = yf.download(ticker, period="5d", interval="1d",
                         progress=False, auto_adjust=True, timeout=8)
        if df is None or df.empty:
            raise HTTPException(404, "Keine Daten")
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        price  = float(df["Close"].iloc[-1])
        change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2]) if len(df) >= 2 else 0
        change_pct = round(change / float(df["Close"].iloc[-2]) * 100, 2) if len(df) >= 2 else 0
        return {
            "ticker": ticker,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": change_pct,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/mini-futures/{ticker}")
def get_mini_futures(ticker: str, direction: str = "BUY"):
    name = next((k for k, v in ALL_TICKERS.items() if v == ticker), ticker)
    try:
        df = yf.download(ticker, period="1mo", interval="1d",
                         progress=False, auto_adjust=True, timeout=8)
        if df is None or df.empty:
            raise HTTPException(404, "Keine Daten")
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        price = float(df["Close"].iloc[-1])
        h_col = df["High"].squeeze(); l_col = df["Low"].squeeze(); c_col = df["Close"].squeeze()
        tr    = pd.concat([h_col-l_col, (h_col-c_col.shift()).abs(), (l_col-c_col.shift()).abs()], axis=1).max(axis=1)
        atr   = float(tr.rolling(14).mean().iloc[-1])
        products = calc_mini_futures(ticker, direction, price, atr)
        return {"ticker": ticker, "name": name, "price": price,
                "direction": direction, "products": products}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/chart/{ticker}")
def get_chart(ticker: str, period: str = "3mo"):
    import gc
    valid_periods = ["1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y"]
    if period not in valid_periods:
        period = "3mo"
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True, timeout=15)
        if df is None or df.empty:
            raise HTTPException(404, "Keine Daten")
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()

        bb_period = min(20, max(5, len(c)//5))
        sma       = c.rolling(bb_period).mean()
        std       = c.rolling(bb_period).std()
        bb_upper  = sma + 2*std
        bb_lower  = sma - 2*std
        ema20     = c.ewm(span=20, adjust=False).mean()
        ema50     = c.ewm(span=50, adjust=False).mean()
        ema200    = c.ewm(span=200, adjust=False).mean() if len(c) >= 50 else None

        prev_h = float(h.iloc[-2]); prev_l = float(l.iloc[-2]); prev_c = float(c.iloc[-2])
        pivot  = (prev_h + prev_l + prev_c) / 3
        support_levels    = [round(2*pivot - prev_h, 2), round(pivot - (prev_h - prev_l), 2)]
        resistance_levels = [round(2*pivot - prev_l, 2), round(pivot + (prev_h - prev_l), 2)]

        chart_data = []
        for i in range(len(df)):
            try:
                row = {
                    "date":     df.index[i].strftime("%Y-%m-%d"),
                    "open":     round(float(df["Open"].iloc[i]), 2),
                    "high":     round(float(df["High"].iloc[i]), 2),
                    "low":      round(float(df["Low"].iloc[i]), 2),
                    "close":    round(float(c.iloc[i]), 2),
                    "volume":   int(df["Volume"].iloc[i]) if "Volume" in df.columns else 0,
                    "bb_upper": round(float(bb_upper.iloc[i]), 2) if not np.isnan(bb_upper.iloc[i]) else None,
                    "bb_mid":   round(float(sma.iloc[i]), 2) if not np.isnan(sma.iloc[i]) else None,
                    "bb_lower": round(float(bb_lower.iloc[i]), 2) if not np.isnan(bb_lower.iloc[i]) else None,
                    "ema20":    round(float(ema20.iloc[i]), 2),
                    "ema50":    round(float(ema50.iloc[i]), 2),
                }
                if ema200 is not None:
                    row["ema200"] = round(float(ema200.iloc[i]), 2)
                chart_data.append(row)
            except:
                pass

        del df, c, h, l, sma, std, bb_upper, bb_lower, ema20, ema50
        gc.collect()

        return {"ticker": ticker, "period": period,
                "data": chart_data,
                "support_levels": support_levels,
                "resistance_levels": resistance_levels}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/watchlist")
def get_watchlist():
    with _lock:
        status      = _state.get("status", "idle")
        all_results = _state.get("all_results", [])
        results     = _state.get("results", [])

    if status != "done":
        return {"status": status, "items": results}

    analyzed_tickers = {r["ticker"] for r in all_results}
    items = list(all_results)
    for name, ticker in ALL_TICKERS.items():
        if ticker not in analyzed_tickers:
            items.append({
                "ticker": ticker, "name": name, "price": None,
                "direction": "NEUTRAL", "score": 0, "strength": 0,
                "signals": [], "stop_loss": None, "take_profit": None,
                "rsi": None, "timestamp": None
            })

    items.sort(key=lambda x: x.get("strength", 0), reverse=True)
    return {"status": "done", "items": items, "total": len(items)}


@app.get("/api/portfolio/backup")
def backup_portfolio():
    return load_portfolio()


@app.post("/api/portfolio/restore")
def restore_portfolio(data: dict):
    required = ["cash", "start_capital", "positions", "closed_trades"]
    if not all(k in data for k in required):
        raise HTTPException(400, "Ungültige Portfolio-Daten")
    save_portfolio(data)
    return {"success": True, "message": "Portfolio wiederhergestellt"}


@app.post("/api/portfolio/reset")
def reset_portfolio():
    """Setzt das Portfolio auf 10.000€ Startkapital zurück"""
    fresh = {
        "cash": 10000.0, "start_capital": 10000.0,
        "positions": [], "closed_trades": [],
        "created": datetime.now().isoformat()
    }
    save_portfolio(fresh)
    return {"success": True, "message": "Portfolio zurückgesetzt auf 10.000€"}


@app.get("/api/settings")
def get_settings_ep():
    return load_settings()


class SettingsRequest(BaseModel):
    min_strength: int


@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    if not 10 <= req.min_strength <= 100:
        raise HTTPException(400, "Stärke zwischen 10 und 100")
    s = load_settings()
    s["min_strength"] = req.min_strength
    save_settings(s)
    global _state
    with _lock:
        _state = {"status": "idle", "progress": 0, "results": [], "timestamp": None}
    return s


@app.get("/api/portfolio")
def get_portfolio():
    p      = load_portfolio()
    closed = p["closed_trades"]
    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total  = round(p["cash"] + open_val, 2)
    pnl    = round(total - p["start_capital"], 2)
    wins   = [t for t in closed if t.get("status") == "WIN"]
    fees_paid = len(closed) * ORDER_FEE * 2 + len(p["positions"]) * ORDER_FEE

    # Portfolio-Risikolimits prüfen
    exposure_pct = round(open_val / total * 100, 1) if total > 0 else 0
    limits = {
        "max_positions":    MAX_POSITIONS,
        "current_positions": len(p["positions"]),
        "max_exposure_pct":  int(MAX_EXPOSURE_PCT * 100),
        "current_exposure_pct": exposure_pct,
        "positions_limit_reached": len(p["positions"]) >= MAX_POSITIONS,
        "exposure_limit_reached":  open_val / total >= MAX_EXPOSURE_PCT if total > 0 else False,
    }

    stats = {
        "start_capital": p["start_capital"], "total_value": total,
        "cash": p["cash"], "open_value": round(open_val, 2),
        "total_pnl": pnl,
        "total_pnl_pct": round(pnl / p["start_capital"] * 100, 2),
        "total_trades": len(closed), "open_positions": len(p["positions"]),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "fees_paid": fees_paid,
        "limits": limits
    }
    return {"portfolio": p, "stats": stats}


class TradeRequest(BaseModel):
    ticker: str; name: str; direction: str; price: float
    stop_loss: float; take_profit: float; score: int
    signals: list; leverage: int = 1; invest_amount: float = 0
    is_mini_future: bool = False; mini_future_leverage: int = 1


@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p = load_portfolio()

    # Portfolio-Risikolimits prüfen
    if len(p["positions"]) >= MAX_POSITIONS:
        raise HTTPException(400,
            f"Portfolio-Limit erreicht: max. {MAX_POSITIONS} gleichzeitige Positionen")

    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total_val = p["cash"] + open_val
    if open_val / total_val >= MAX_EXPOSURE_PCT if total_val > 0 else False:
        raise HTTPException(400,
            f"Exposure-Limit erreicht: max. {int(MAX_EXPOSURE_PCT*100)}% des Portfolios in offenen Positionen")

    distance = abs(req.price - req.stop_loss)
    if distance == 0:
        raise HTTPException(400, "Stop Loss identisch mit Preis")

    units, cost = calc_position_size(
        portfolio_cash=p["cash"],
        portfolio_total=total_val,
        price=req.price,
        stop_loss=req.stop_loss,
        invest_amount=req.invest_amount
    )
    total_cost = cost + ORDER_FEE
    if total_cost > p["cash"]:
        raise HTTPException(400,
            f"Nicht genug Cash ({p['cash']:.2f}€, inkl. 10€ Gebühr). Berechnet: {total_cost:.2f}€")

    trade_id = f"T{len(p['closed_trades']) + len(p['positions']) + 1:04d}"
    risk_amount = round(distance * units, 2)
    risk_pct    = round(risk_amount / total_val * 100, 2) if total_val > 0 else 0

    pos = {
        "id": trade_id, "ticker": req.ticker, "name": req.name,
        "direction": req.direction, "entry_price": req.price,
        "current_price": req.price, "units": units, "cost": cost,
        "fee": ORDER_FEE, "stop_loss": req.stop_loss, "take_profit": req.take_profit,
        "score": req.score, "signals": req.signals,
        "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0, "current_value": cost,
        "risk_amount": risk_amount, "risk_pct": risk_pct,
        "is_mini_future": req.is_mini_future, "leverage": req.mini_future_leverage,
        "opened": datetime.now().isoformat()
    }
    p["cash"] = round(p["cash"] - total_cost, 2)
    p["positions"].append(pos)
    save_portfolio(p)
    return {"success": True, "trade": pos, "fee_charged": ORDER_FEE,
            "risk_amount": risk_amount, "risk_pct": risk_pct}


class CloseRequest(BaseModel):
    trade_id: str; close_price: float


@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p   = load_portfolio()
    pos = next((x for x in p["positions"] if x["id"] == req.trade_id), None)
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    lev = pos.get("leverage", 1)
    pnl = ((req.close_price - pos["entry_price"]) * pos["units"] * lev
           if pos["direction"] == "BUY"
           else (pos["entry_price"] - req.close_price) * pos["units"] * lev)
    pnl_after_fee = pnl - ORDER_FEE
    proceeds = round(pos["cost"] + pnl_after_fee, 2)
    closed = {
        **pos,
        "close_price": req.close_price,
        "pnl": round(pnl_after_fee, 2),
        "pnl_gross": round(pnl, 2),
        "fees": ORDER_FEE * 2,
        "pnl_pct": round(pnl_after_fee / pos["cost"] * 100, 2),
        "proceeds": proceeds,
        "closed": datetime.now().isoformat(),
        "status": "WIN" if pnl_after_fee > 0 else "LOSS"
    }
    p["positions"]     = [x for x in p["positions"] if x["id"] != req.trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"] + proceeds, 2)
    save_portfolio(p)
    return {"success": True, "trade": closed}


@app.get("/api/exit-signals")
def get_exit_signals():
    p         = load_portfolio()
    positions = p.get("positions", [])
    if not positions:
        return {"exit_signals": [], "checked": 0}
    signals = []
    for pos in positions:
        try:
            ticker = pos["ticker"]
            df = yf.download(ticker, period="1mo", interval="1d",
                             progress=False, auto_adjust=True, timeout=8)
            if df is None or df.empty or len(df) < 10: continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            c  = df["Close"].squeeze()
            h  = df["High"].squeeze()
            l  = df["Low"].squeeze()
            price = float(c.iloc[-1])

            delta = c.diff()
            r = float((100 - 100/(1 + (
                delta.clip(lower=0).rolling(14).mean() /
                (-delta.clip(upper=0)).rolling(14).mean().replace(0, np.nan)
            ))).iloc[-1])
            e12 = c.ewm(span=12, adjust=False).mean()
            e26 = c.ewm(span=26, adjust=False).mean()
            m   = e12 - e26
            s2  = m.ewm(span=9, adjust=False).mean()
            hs  = m - s2
            mk, ms, mh, mhp = float(m.iloc[-1]), float(s2.iloc[-1]), float(hs.iloc[-1]), float(hs.iloc[-2])
            ll  = l.rolling(14).min(); hh = h.rolling(14).max()
            sk_s = 100*(c - ll)/(hh - ll).replace(0, np.nan)
            sk   = float(sk_s.iloc[-1])
            sd   = float(sk_s.rolling(3).mean().iloc[-1])

            entry     = pos["entry_price"]
            sl        = pos["stop_loss"]
            tp        = pos["take_profit"]
            direction = pos["direction"]
            if direction == "BUY":
                pnl_pct  = (price - entry)/entry*100
                sl_dist  = (price - sl)/entry*100
                tp_dist  = (tp - price)/entry*100
            else:
                pnl_pct  = (entry - price)/entry*100
                sl_dist  = (sl - price)/entry*100
                tp_dist  = (price - tp)/entry*100

            reasons = []; urgency = "normal"
            if tp_dist <= 0:   reasons.append("✅ Take Profit erreicht!"); urgency = "urgent"
            elif sl_dist <= 0: reasons.append("🛑 Stop Loss durchbrochen!"); urgency = "urgent"
            elif sl_dist < 20: reasons.append(f"⚠️ Nahe Stop Loss ({sl_dist:.1f}%)"); urgency = "warn"

            if direction == "BUY":
                if r > 70:                reasons.append(f"RSI überkauft ({r:.0f})")
                if mk < ms and mh < mhp:  reasons.append("MACD dreht negativ")
                if sk > 80 and sk < sd:   reasons.append("Stochastik dreht runter")
            else:
                if r < 30:                reasons.append(f"RSI überverkauft ({r:.0f})")
                if mk > ms and mh > mhp:  reasons.append("MACD dreht positiv")
                if sk < 20 and sk > sd:   reasons.append("Stochastik dreht hoch")

            if reasons:
                signals.append({
                    "trade_id": pos["id"], "ticker": ticker, "name": pos["name"],
                    "direction": direction, "entry_price": entry,
                    "current_price": round(price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "stop_loss": sl, "take_profit": tp,
                    "exit_reasons": reasons, "urgency": urgency,
                    "recommendation": "SCHLIESSEN" if urgency == "urgent" else "PRÜFEN"
                })
        except:
            continue

    signals.sort(key=lambda x: {"urgent": 0, "warn": 1, "normal": 2}.get(x["urgency"], 2))
    return {"exit_signals": signals, "checked": len(positions)}


@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>TradeBot Pro v10</h1>"


@app.get("/manifest.json")
def manifest():
    mf_path = Path(__file__).parent / "manifest.json"
    if mf_path.exists(): return JSONResponse(json.loads(mf_path.read_text()))
    return JSONResponse({})


Thread(target=run_analysis, args=(20,), daemon=True).start()
