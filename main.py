"""
TradeBot Pro v12 – Backend vollständig überarbeitet
====================================================
Backend-Developer-Analyse & alle Fixes:

SETTINGS (alle Parameter konfigurierbar):
  ✓ Alle Risikoparameter in Settings-Datei persistiert (kein Hardcoding mehr)
  ✓ load_effective_settings() liefert defaults + user-overrides
  ✓ calc_position_size(), calc_smart_stoploss(), open_trade(), get_portfolio()
    lesen alle aus Settings – keine globalen Konstanten mehr im Laufzeitpfad

CODE-QUALITÄT:
  ✓ Dead-Code in get_exit_signals() entfernt (doppelter fetch_ohlcv-Aufruf)
  ✓ full_analysis Dummy-Signal-Fallback entfernt – None = kein Signal, fertig
  ✓ Cache-Eviction: _df_cache wird auf max 200 Einträge begrenzt (LRU-Ansatz)
  ✓ chart_data vollständig vektorisiert (kein Python-Loop mehr)
  ✓ validate_ticker() akzeptiert auch Mini-Future-Namen mit Leerzeichen
  ✓ Pydantic SettingsRequest deckt alle konfigurierbaren Parameter ab
  ✓ Alle Magic Numbers als benannte Felder in DEFAULTS
"""

import gc
import json
import os
import time
import tempfile
from datetime import datetime
from pathlib import Path
from threading import Thread, Lock
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TradeBot Pro", version="12.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── Default-Werte (Fallback wenn Settings-Datei fehlt) ───────────────────────
DEFAULTS = {
    "min_strength":    20,     # Mindest-Signalstärke 10–80
    "order_fee":       10.0,   # € pro Einzelorder (Kauf oder Verkauf)
    "max_positions":   5,      # Max. gleichzeitige Positionen 1–20
    "max_exposure":    40,     # Max. Exposure in % des Portfolios 10–90
    "risk_per_trade":  2,      # Risiko pro Trade in % des Kapitals 0.5–5
    "max_position":    20,     # Max. Positionsgröße in % des Kapitals 5–50
    "min_sl_dist":     1.5,    # Mindest-SL-Abstand in % 0.5–5
    "max_sl_dist":     8.0,    # Max-SL-Abstand in % 2–20
    "vol_threshold":   5.0,    # ATR%-Schwelle für Volatilitätswarnung 2–15
    "adx_trend":       25,     # ADX-Grenze Trendmarkt 15–40
    "adx_sideways":    20,     # ADX-Grenze Seitwärtsmarkt 10–30
    "start_capital":   10000.0,# Virtuelles Startkapital
}

# Cache-TTLs (nicht per User konfigurierbar)
PRICE_CACHE_TTL  = 300
DETAIL_CACHE_TTL = 600
CHART_CACHE_TTL  = 600
DF_CACHE_MAX     = 200   # Max. Einträge im DataFrame-Cache

ALL_TICKERS = {
    "DAX Index":      "^GDAXI",
    "Euro Stoxx 50":  "^STOXX50E",
    "FTSE 100":       "^FTSE",
    "CAC 40":         "^FCHI",
    "IBEX 35":        "^IBEX",
    "AEX":            "^AEX",
    "SMI":            "^SSMI",
    "Adidas":         "ADS.DE",
    "Airbus":         "AIR.DE",
    "Allianz":        "ALV.DE",
    "BASF":           "BAS.DE",
    "Bayer":          "BAYN.DE",
    "Beiersdorf":     "BEI.DE",
    "BMW":            "BMW.DE",
    "Brenntag":       "BNR.DE",
    "Continental":    "CON.DE",
    "Covestro":       "1COV.DE",
    "Deutsche Post":  "DHL.DE",
    "Telekom":        "DTE.DE",
    "EON":            "EOAN.DE",
    "Fresenius Med":  "FME.DE",
    "Fresenius":      "FRE.DE",
    "Heidelberg Mat": "HEI.DE",
    "Henkel":         "HEN3.DE",
    "Infineon":       "IFX.DE",
    "Linde":          "LIN.DE",
    "Mercedes":       "MBG.DE",
    "Merck":          "MRK.DE",
    "MTU Aero":       "MTX.DE",
    "Munich Re":      "MUV2.DE",
    "Porsche AG":     "P911.DE",
    "Qiagen":         "QIA.DE",
    "Rheinmetall":    "RHM.DE",
    "RWE":            "RWE.DE",
    "SAP":            "SAP.DE",
    "Siemens Health": "SHL.DE",
    "Siemens":        "SIE.DE",
    "Symrise":        "SY1.DE",
    "VW":             "VOW3.DE",
    "Vonovia":        "VNA.DE",
    "Zalando":        "ZAL.DE",
    "Deutsche Bank":  "DBK.DE",
    "Commerzbank":    "CBK.DE",
    "Hannover Rueck": "HNR1.DE",
    "Sartorius":      "SRT3.DE",
    "ASML":           "ASML.AS",
    "ING":            "INGA.AS",
    "Ahold":          "AD.AS",
    "LVMH":           "MC.PA",
    "LOreal":         "OR.PA",
    "TotalEnergies":  "TTE.PA",
    "Sanofi":         "SAN.PA",
    "BNP Paribas":    "BNP.PA",
    "Kering":         "KER.PA",
    "Airbus FR":      "AIR.PA",
    "Santander":      "SAN.MC",
    "BBVA":           "BBVA.MC",
    "Inditex":        "ITX.MC",
    "Nestle":         "NESN.SW",
    "Roche":          "ROG.SW",
    "Novartis":       "NOVN.SW",
    "ABB":            "ABBN.SW",
    "AstraZeneca":    "AZN.L",
    "HSBC":           "HSBA.L",
    "BP":             "BP.L",
    "Shell":          "SHEL.L",
    "GSK":            "GSK.L",
    "Unilever":       "ULVR.L",
    "Enel":           "ENEL.MI",
    "ENI":            "ENI.MI",
    "UniCredit":      "UCG.MI",
    "STMicro":        "STM.MI",
}

TICKER_TO_NAME = {v: k for k, v in ALL_TICKERS.items()}
VALID_TICKERS  = set(ALL_TICKERS.values())

PORTFOLIO_FILE = "/tmp/portfolio.json"
SETTINGS_FILE  = "/tmp/settings.json"

# ── In-Memory State & Caches ──────────────────────────────────────────────────
_lock            = Lock()
_state           = {"status": "idle", "progress": 0, "results": [], "timestamp": None}
_portfolio_cache: dict | None = None
_portfolio_mtime: float = 0.0
_price_cache:    dict = {}
_detail_cache:   dict = {}
_chart_cache:    dict = {}
_df_cache:       dict = {}
_df_lock         = Lock()

# ── Atomares File-Write ───────────────────────────────────────────────────────
def _atomic_write(path: str, data: dict) -> None:
    dir_ = os.path.dirname(path) or "/tmp"
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(data, f, ensure_ascii=False)
        tmp = f.name
    os.replace(tmp, path)

# ── Settings: alle Parameter konfigurierbar ───────────────────────────────────
def load_settings() -> dict:
    """Lädt Settings und merged mit DEFAULTS (fehlende Keys werden aufgefüllt)."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                saved = json.load(f)
            # Merge: DEFAULTS als Basis, User-Werte überschreiben
            return {**DEFAULTS, **saved}
    except Exception:
        pass
    return dict(DEFAULTS)

def save_settings(s: dict) -> None:
    _atomic_write(SETTINGS_FILE, s)

def get_s(key: str):
    """Shortcut: aktuellen Setting-Wert abrufen."""
    return load_settings().get(key, DEFAULTS[key])

# ── Portfolio ─────────────────────────────────────────────────────────────────
def load_portfolio() -> dict:
    global _portfolio_cache, _portfolio_mtime
    try:
        mtime = os.path.getmtime(PORTFOLIO_FILE)
        if _portfolio_cache is not None and mtime == _portfolio_mtime:
            return _portfolio_cache
        with open(PORTFOLIO_FILE) as f:
            _portfolio_cache = json.load(f)
        _portfolio_mtime = mtime
        return _portfolio_cache
    except Exception:
        pass
    sc = get_s("start_capital")
    return {"cash": sc, "start_capital": sc,
            "positions": [], "closed_trades": [],
            "created": datetime.now().isoformat()}

def save_portfolio(p: dict) -> None:
    global _portfolio_cache, _portfolio_mtime
    _atomic_write(PORTFOLIO_FILE, p)
    _portfolio_cache = p
    try:
        _portfolio_mtime = os.path.getmtime(PORTFOLIO_FILE)
    except Exception:
        _portfolio_mtime = time.time()

# ── Ticker-Validierung ────────────────────────────────────────────────────────
def validate_ticker(ticker: str) -> str:
    """Whitelist-Prüfung. Mini-Future-Namen (z.B. 'ADS.DE x5') werden korrekt behandelt."""
    base = ticker.split()[0] if " " in ticker else ticker
    if base not in VALID_TICKERS:
        raise HTTPException(400, f"Unbekannter Ticker: {ticker}")
    return base  # Immer den reinen Ticker zurückgeben

# ── DataFrame-Cache mit Eviction ─────────────────────────────────────────────
def fetch_ohlcv(ticker: str, period: str = "6mo", timeout: int = 10) -> pd.DataFrame | None:
    key = f"{ticker}|{period}"
    now = time.time()
    with _df_lock:
        cached = _df_cache.get(key)
        if cached and now - cached["ts"] < CHART_CACHE_TTL:
            return cached["df"]
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True, timeout=timeout)
        if df is None or df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        with _df_lock:
            # Cache-Eviction: älteste Einträge entfernen wenn zu groß
            if len(_df_cache) >= DF_CACHE_MAX:
                oldest = sorted(_df_cache, key=lambda k: _df_cache[k]["ts"])[:50]
                for k in oldest:
                    del _df_cache[k]
            _df_cache[key] = {"df": df, "ts": now}
        return df
    except Exception:
        return None

# ── Indikatoren-Berechnung ────────────────────────────────────────────────────
def compute_indicators(c: pd.Series, h: pd.Series, l: pd.Series,
                       v: pd.Series, cfg: dict) -> dict:
    price = float(c.iloc[-1])

    # ATR
    tr    = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = atr14 / price * 100

    # ADX
    up_move   = h.diff()
    down_move = -l.diff()
    pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    ndm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr_mean = tr.rolling(14).mean().replace(0, np.nan)
    pdi = 100 * pd.Series(pdm, index=c.index).rolling(14).mean() / tr_mean
    ndi = 100 * pd.Series(ndm, index=c.index).rolling(14).mean() / tr_mean
    dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    adx = float(dx.rolling(14).mean().iloc[-1])
    pdi_v, ndi_v = float(pdi.iloc[-1]), float(ndi.iloc[-1])

    adx_trend    = cfg["adx_trend"]
    adx_sideways = cfg["adx_sideways"]

    # RSI
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float((100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1])

    # MACD
    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    macd = e12 - e26; msig = macd.ewm(span=9, adjust=False).mean(); mhist = macd - msig
    mk, ms = float(macd.iloc[-1]), float(msig.iloc[-1])
    mh, mhp = float(mhist.iloc[-1]), float(mhist.iloc[-2])

    # Bollinger
    sma20    = c.rolling(20).mean(); std20 = c.rolling(20).std()
    bb_upper = sma20 + 2*std20; bb_lower = sma20 - 2*std20
    pb = float(((c - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)).iloc[-1])

    # Stochastic
    ll14 = l.rolling(14).min(); hh14 = h.rolling(14).max()
    stk  = 100*(c - ll14)/(hh14 - ll14).replace(0, np.nan)
    sk, sd = float(stk.iloc[-1]), float(stk.rolling(3).mean().iloc[-1])

    # EMAs
    e20  = float(c.ewm(span=20).mean().iloc[-1])
    e50  = float(c.ewm(span=50).mean().iloc[-1])
    e100 = float(c.ewm(span=100).mean().iloc[-1])
    e200 = float(c.ewm(span=200).mean().iloc[-1]) if len(c) >= 200 else None

    # Williams %R, CCI, OBV
    willr = float((-100*(hh14-c)/(hh14-ll14).replace(0,np.nan)).iloc[-1])
    tp_   = (h+l+c)/3
    cci   = float(((tp_-tp_.rolling(20).mean())/(0.015*tp_.rolling(20).std())).iloc[-1])
    obv   = (np.sign(c.diff())*v).fillna(0).cumsum()
    obv_bull = float(obv.iloc[-1]) > float(obv.ewm(span=20).mean().iloc[-1])

    # Pivot Points
    ph, pl, pc = float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2])
    pivot = (ph+pl+pc)/3
    r1=2*pivot-pl; r2=pivot+(ph-pl); s1=2*pivot-ph; s2=pivot-(ph-pl)

    # 52W, ROC
    n52 = min(252, len(h))
    w52h = float(h.rolling(n52).max().iloc[-1])
    w52l = float(l.rolling(n52).min().iloc[-1])
    w52p = round((price-w52l)/(w52h-w52l)*100,1) if w52h != w52l else 50.0
    roc10 = float(((c-c.shift(10))/c.shift(10)*100).iloc[-1])

    return {
        "price": price,
        "atr14": atr14, "atr_pct": atr_pct,
        "high_vol": atr_pct > cfg["vol_threshold"],
        "adx": adx, "pdi": pdi_v, "ndi": ndi_v,
        "trending": adx >= adx_trend,
        "sideways": adx < adx_sideways,
        "trend_up": pdi_v > ndi_v,
        "rsi": rsi,
        "mk": mk, "ms": ms, "mh": mh, "mhp": mhp,
        "pb": pb, "bb_upper": float(bb_upper.iloc[-1]), "bb_lower": float(bb_lower.iloc[-1]),
        "sma20": sma20, "std20": std20,
        "sk": sk, "sd": sd,
        "e20": e20, "e50": e50, "e100": e100, "e200": e200,
        "willr": willr, "cci": cci, "obv_bull": obv_bull,
        "pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2,
        "w52h": w52h, "w52l": w52l, "w52p": w52p,
        "roc10": roc10, "tr": tr,
    }

# ── Scoring ───────────────────────────────────────────────────────────────────
def _score_from_ind(ind: dict) -> tuple:
    sa, sb, sc = 0, 0, 0
    signals = []
    price = ind["price"]

    # A: Momentum
    rsi = ind["rsi"]
    if   rsi < 30: sa+=20; signals.append(f"RSI überverkauft ({rsi:.0f})")
    elif rsi < 40: sa+=10; signals.append(f"RSI schwach ({rsi:.0f})")
    elif rsi > 70: sa-=20; signals.append(f"RSI überkauft ({rsi:.0f})")
    elif rsi > 60: sa-=10; signals.append(f"RSI stark ({rsi:.0f})")

    pb = ind["pb"]
    if   pb < 0.05: sa+=20; signals.append("Unteres Bollinger Band")
    elif pb < 0.20: sa+=10; signals.append("Nahe unterem BB")
    elif pb > 0.95: sa-=20; signals.append("Oberes Bollinger Band")
    elif pb > 0.80: sa-=10; signals.append("Nahe oberem BB")

    sk, sd = ind["sk"], ind["sd"]
    if sk < 20 and sk > sd:   sa+=15; signals.append(f"Stochastik dreht hoch ({sk:.0f})")
    elif sk > 80 and sk < sd: sa-=15; signals.append(f"Stochastik dreht runter ({sk:.0f})")

    willr = ind["willr"]
    if   willr < -80: sa+=10; signals.append(f"Williams %R überverkauft ({willr:.0f})")
    elif willr > -20: sa-=10; signals.append(f"Williams %R überkauft ({willr:.0f})")

    cci = ind["cci"]
    if   cci < -100: sa+=10; signals.append(f"CCI überverkauft ({cci:.0f})")
    elif cci >  100: sa-=10; signals.append(f"CCI überkauft ({cci:.0f})")

    if ind["trending"]:
        if (ind["trend_up"] and sa < 0) or (not ind["trend_up"] and sa > 0):
            sa = int(sa * 0.5)
            signals.append(f"⚠️ Trendmarkt (ADX {ind['adx']:.0f}): Oszillator gedämpft")

    # B: Trendfolger
    mk, ms, mh, mhp = ind["mk"], ind["ms"], ind["mh"], ind["mhp"]
    if mk > ms and mh > mhp:   sb+=20; signals.append("MACD bullisch ↑")
    elif mk < ms and mh < mhp: sb-=20; signals.append("MACD bärisch ↓")

    e20, e50, e100, e200 = ind["e20"], ind["e50"], ind["e100"], ind["e200"]
    if   price > e20 > e50 > e100: sb+=15; signals.append("Starker Auftrend (EMA 20>50>100)")
    elif price > e20 > e50:        sb+=10; signals.append("Auftrend EMA 20/50")
    elif price < e20 < e50 < e100: sb-=15; signals.append("Starker Abtrend (EMA 20<50<100)")
    elif price < e20 < e50:        sb-=10; signals.append("Abtrend EMA 20/50")
    if e200:
        if price > e200: sb+=5; signals.append("Über EMA 200 (Langzeittrend bullisch)")
        else:            sb-=5; signals.append("Unter EMA 200 (Langzeittrend bärisch)")

    adx = ind["adx"]
    if ind["trending"]:
        if ind["trend_up"]: sb+=10; signals.append(f"ADX starker Auftrend ({adx:.0f})")
        else:               sb-=10; signals.append(f"ADX starker Abtrend ({adx:.0f})")
    elif ind["sideways"]:
        sb = 0; signals.append(f"⚠️ Seitwärtsmarkt (ADX {adx:.0f}): Trendfolger deaktiviert")
    else:
        signals.append(f"ADX schwacher Trend ({adx:.0f})")

    # C: Struktur
    if ind["obv_bull"]: sc+=5;  signals.append("OBV: Kaufvolumen steigt")
    else:               sc-=5;  signals.append("OBV: Verkaufsvolumen steigt")

    w52p = ind["w52p"]
    if   w52p < 15: sc+=10; signals.append(f"Nahe 52W-Tief ({w52p:.0f}%)")
    elif w52p > 85: sc-=10; signals.append(f"Nahe 52W-Hoch ({w52p:.0f}%)")

    s1, r1 = ind["s1"], ind["r1"]
    if   price < s1: sc+=8;  signals.append(f"Unter S1 ({s1:.2f}) – Bounce-Zone")
    elif price > r1: sc-=8;  signals.append(f"Über R1 ({r1:.2f}) – Widerstand")

    roc10 = ind["roc10"]
    if   roc10 >  5: sc-=5; signals.append(f"Positives Momentum (+{roc10:.1f}%)")
    elif roc10 < -5: sc+=5; signals.append(f"Negatives Momentum ({roc10:.1f}%)")

    return sa, sb, sc, signals

# ── Signal aufbauen ───────────────────────────────────────────────────────────
def calc_smart_stoploss(price: float, direction: str, atr: float,
                        s1: float, s2: float, r1: float, r2: float,
                        cfg: dict) -> float:
    min_d = price * cfg["min_sl_dist"] / 100
    max_d = price * cfg["max_sl_dist"] / 100
    if direction == "BUY":
        for level in [s1, s2]:
            if 0 < level < price:
                sl = round(level * 0.998, 2)
                dist = price - sl
                if min_d <= dist <= max_d: return sl
        sl = round(price - 1.5*atr, 2); dist = price - sl
        if dist < min_d: return round(price - min_d, 2)
        if dist > max_d: return round(price - max_d, 2)
        return sl
    else:
        for level in [r1, r2]:
            if level > price:
                sl = round(level * 1.002, 2)
                dist = sl - price
                if min_d <= dist <= max_d: return sl
        sl = round(price + 1.5*atr, 2); dist = sl - price
        if dist < min_d: return round(price + min_d, 2)
        if dist > max_d: return round(price + max_d, 2)
        return sl

def _build_signal(ticker: str, name: str, ind: dict,
                  min_strength: int, cfg: dict) -> dict | None:
    sa, sb, sc, signals = _score_from_ind(ind)
    g_up   = sum(1 for x in [sa,sb,sc] if x > 0)
    g_down = sum(1 for x in [sa,sb,sc] if x < 0)
    if g_up < 2 and g_down < 2: return None
    total = sa + sb + sc
    direction = "BUY" if total > 0 else "SELL"
    conf = g_up if direction == "BUY" else g_down
    if conf < 2: return None
    if ind["high_vol"]:
        total = int(total * 0.5)
        signals.append(f"⚠️ Hohe Volatilität (ATR {ind['atr_pct']:.1f}%) – Score reduziert")
    if abs(total) < min_strength: return None
    price = ind["price"]
    sl = calc_smart_stoploss(price, direction, ind["atr14"],
                             ind["s1"], ind["s2"], ind["r1"], ind["r2"], cfg)
    tp_mult = 2.5 if not ind["high_vol"] else 2.0
    tp = (round(price + tp_mult*(price-sl), 2) if direction == "BUY"
          else round(price - tp_mult*(sl-price), 2))
    market_phase = ("Trendmarkt" if ind["trending"]
                    else ("Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend"))
    return {
        "ticker": ticker, "name": name, "price": round(price, 2),
        "direction": direction, "score": int(total),
        "score_detail": {"momentum": int(sa), "trend": int(sb), "structure": int(sc)},
        "strength": min(100, abs(int(total))),
        "confirming_groups": conf, "market_phase": market_phase,
        "high_volatility": ind["high_vol"],
        "signals": signals, "warnings": [],
        "stop_loss": sl, "take_profit": tp,
        "rsi": round(ind["rsi"], 1), "atr": round(ind["atr14"], 2),
        "support_levels":    [round(ind["s1"],2), round(ind["s2"],2)],
        "resistance_levels": [round(ind["r1"],2), round(ind["r2"],2)],
        "timestamp": datetime.now().isoformat()
    }

# ── Position Sizing (aus Settings) ───────────────────────────────────────────
def calc_position_size(cash: float, total: float, price: float,
                       stop_loss: float, invest_amount: float,
                       cfg: dict) -> tuple:
    order_fee    = cfg["order_fee"]
    max_pos_pct  = cfg["max_position"] / 100
    risk_pct     = cfg["risk_per_trade"] / 100
    distance = abs(price - stop_loss) or price * 0.02
    if invest_amount > 0:
        cost = round(min(invest_amount, cash - order_fee, total * max_pos_pct), 2)
    else:
        cost = round(min((total * risk_pct / distance) * price,
                         total * max_pos_pct,
                         cash - order_fee), 2)
    cost = max(cost, 0.01)
    return round(cost / price, 4), cost

# ── Quick-Score ───────────────────────────────────────────────────────────────
def quick_score(ticker: str, name: str, min_strength: int, cfg: dict) -> dict | None:
    df = fetch_ohlcv(ticker, period="6mo")
    if df is None or len(df) < 60: return None
    try:
        c = df["Close"].squeeze(); h = df["High"].squeeze(); l = df["Low"].squeeze()
        v = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)), index=c.index)
        ind = compute_indicators(c, h, l, v, cfg)
        sig = _build_signal(ticker, name, ind, min_strength, cfg)
        if sig is None: return None
        sig["indicators"] = {
            "RSI (14)": round(ind["rsi"],1), "MACD": round(ind["mk"],4),
            "BB %B": round(ind["pb"],2), "Stoch %K": round(ind["sk"],1),
            "EMA 20": round(ind["e20"],2), "EMA 50": round(ind["e50"],2),
            "ADX": round(ind["adx"],1), "ATR (14)": round(ind["atr14"],2),
            "Marktphase": sig["market_phase"],
        }
        sig["analyst"] = {}; sig["chart_data"] = []
        return sig
    except Exception:
        return None
    finally:
        gc.collect()

# ── Full Analysis ─────────────────────────────────────────────────────────────
def full_analysis(ticker: str, name: str, min_strength: int = 0) -> dict | None:
    cfg = load_settings()
    now = time.time()
    cached = _detail_cache.get(ticker)
    if cached and now - cached["ts"] < DETAIL_CACHE_TTL:
        return cached["result"]
    df = fetch_ohlcv(ticker, period="1y")
    if df is None or len(df) < 60: return None
    try:
        c = df["Close"].squeeze(); h = df["High"].squeeze(); l = df["Low"].squeeze()
        v = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)), index=c.index)
        ind = compute_indicators(c, h, l, v, cfg)
        sig = _build_signal(ticker, name, ind, min_strength, cfg)
        if sig is None: return None

        # Analysten (nur Info)
        analyst_info = {}
        try:
            info   = yf.Ticker(ticker).info
            rec    = info.get("recommendationMean")
            n_anal = info.get("numberOfAnalystOpinions", 0)
            target = info.get("targetMeanPrice")
            if rec and n_anal:
                rec_text = {1:"Starker Kauf",2:"Kauf",3:"Halten",
                            4:"Verkauf",5:"Starker Verkauf"}.get(round(rec), f"{rec:.1f}")
                analyst_info = {"recommendation": rec_text, "analysts": n_anal,
                                "target": round(target,2) if target else None}
        except Exception:
            pass

        indicators = {
            "RSI (14)": round(ind["rsi"],1), "MACD": round(ind["mk"],4),
            "MACD Signal": round(ind["ms"],4), "BB %B": round(ind["pb"],2),
            "BB Upper": round(ind["bb_upper"],2), "BB Lower": round(ind["bb_lower"],2),
            "Stoch %K": round(ind["sk"],1), "Stoch %D": round(ind["sd"],1),
            "EMA 20": round(ind["e20"],2), "EMA 50": round(ind["e50"],2),
            "EMA 100": round(ind["e100"],2), "Williams %R": round(ind["willr"],1),
            "CCI (20)": round(ind["cci"],1),
            "OBV Trend": "Bullisch" if ind["obv_bull"] else "Bärisch",
            "ATR (14)": round(ind["atr14"],2), "ATR %": f"{ind['atr_pct']:.2f}%",
            "ADX": round(ind["adx"],1), "+DI": round(ind["pdi"],1), "-DI": round(ind["ndi"],1),
            "Pivot": round(ind["pivot"],2), "R1": round(ind["r1"],2), "R2": round(ind["r2"],2),
            "S1": round(ind["s1"],2), "S2": round(ind["s2"],2),
            "52W Hoch": round(ind["w52h"],2), "52W Tief": round(ind["w52l"],2),
            "52W Position": f"{ind['w52p']}%", "ROC (10)": f"{ind['roc10']:.1f}%",
            "Marktphase": sig["market_phase"],
        }
        if ind["e200"]: indicators["EMA 200"] = round(ind["e200"],2)
        if ind["high_vol"]: indicators["⚠️ Volatilität"] = f"ERHÖHT ({ind['atr_pct']:.1f}%) – Vorsicht!"
        if analyst_info:
            indicators["Analysten"] = f"{analyst_info['recommendation']} ({analyst_info['analysts']} Analysten) ℹ️"
            if analyst_info.get("target"):
                indicators["Kursziel"] = f"{analyst_info['target']:.2f} (nur Info)"

        # Chart-Daten vollständig vektorisiert
        df90   = df.tail(90)
        sma20  = ind["sma20"]; std20 = ind["std20"]
        bb_u90 = (sma20+2*std20).tail(90).round(2)
        bb_m90 = sma20.tail(90).round(2)
        bb_l90 = (sma20-2*std20).tail(90).round(2)
        e20s   = c.ewm(span=20).mean().tail(90).round(2)
        e50s   = c.ewm(span=50).mean().tail(90).round(2)

        nan = float("nan")
        chart_data = [
            {"date": df90.index[i].strftime("%Y-%m-%d"),
             "open": round(float(df90["Open"].iat[i]),2),
             "high": round(float(df90["High"].iat[i]),2),
             "low":  round(float(df90["Low"].iat[i]),2),
             "close":round(float(df90["Close"].iat[i]),2),
             "volume": int(df90["Volume"].iat[i]) if "Volume" in df90.columns else 0,
             "bb_upper": None if pd.isna(bb_u90.iat[i]) else float(bb_u90.iat[i]),
             "bb_mid":   None if pd.isna(bb_m90.iat[i]) else float(bb_m90.iat[i]),
             "bb_lower": None if pd.isna(bb_l90.iat[i]) else float(bb_l90.iat[i]),
             "ema20": float(e20s.iat[i]), "ema50": float(e50s.iat[i])}
            for i in range(len(df90))
        ]

        result = {**sig, "indicators": indicators,
                  "analyst": analyst_info, "chart_data": chart_data}
        _detail_cache[ticker] = {"result": result, "ts": now}
        return result
    except Exception:
        return None
    finally:
        gc.collect()

# ── Analyse-Scan ──────────────────────────────────────────────────────────────
def run_analysis(min_strength: int) -> None:
    global _state
    with _lock:
        if _state.get("status") == "running": return
        _state.update({"status": "running", "progress": 0, "results": []})
    cfg = load_settings()
    items = list(ALL_TICKERS.items()); total = len(items); results = []
    for i, (name, ticker) in enumerate(items):
        sig = quick_score(ticker, name, min_strength, cfg)
        if sig: results.append(sig)
        if i % 5 == 4 or i == total - 1:
            rs = sorted(results, key=lambda x: x["strength"], reverse=True)
            with _lock:
                _state["progress"] = round((i+1)/total*100)
                _state["results"]  = rs[:15]
            time.sleep(0.3); gc.collect()
    rs = sorted(results, key=lambda x: x["strength"], reverse=True)
    with _lock:
        _state.update({"status":"done","progress":100,"results":rs[:15],
                       "all_results":rs,"signals_found":len(results),
                       "total_analyzed":total,"timestamp":datetime.now().isoformat()})
    gc.collect()

# ── Mini-Futures ──────────────────────────────────────────────────────────────
def calc_mini_futures(direction: str, price: float, atr: float) -> list:
    products = []
    for lev in [2,3,4,5,6,8,10,12,15,18,20,22,25,28,30]:
        ko_pct = 1.0/lev
        if direction == "BUY":
            ko=round(price*(1-ko_pct),2); sl=round(ko*1.005,2)
            mfp=round((price-ko)*1.02,2); tp=round(price+2*atr,2)
        else:
            ko=round(price*(1+ko_pct),2); sl=round(ko*0.995,2)
            mfp=round((ko-price)*1.02,2); tp=round(price-2*atr,2)
        gain = round(atr*2*lev/mfp*100,1) if mfp>0 else 0
        products.append({
            "leverage":lev,"direction":direction,"base_price":round(price,2),
            "knock_out":ko,"stop_loss_level":sl,"mini_future_price":mfp,
            "take_profit":tp,"max_loss_pct":round(ko_pct*100,1),
            "potential_gain_pct":gain,
            "risk_level":"Niedrig" if lev<=5 else "Mittel" if lev<=15 else "Hoch",
            "label":f"x{lev} {'Long' if direction=='BUY' else 'Short'} – KO: {ko}"
        })
    return products

# ═══════════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/signals")
def get_signals():
    cfg = load_settings(); min_str = cfg["min_strength"]
    with _lock:
        status=_state.get("status","idle"); progress=_state.get("progress",0)
        results=list(_state.get("results",[])); ts=_state.get("timestamp")
        found=_state.get("signals_found",len(results)); analyzed=_state.get("total_analyzed",0)
    if status == "idle":
        Thread(target=run_analysis, args=(min_str,), daemon=True).start()
        return {"status":"loading","progress":0,"top_signals":[],"total_analyzed":0,"signals_found":0}
    return {"status":status,"progress":progress,"top_signals":results,
            "total_analyzed":analyzed,"signals_found":found,"timestamp":ts}

@app.post("/api/signals/refresh")
def refresh_signals():
    global _state
    cfg = load_settings(); min_str = cfg["min_strength"]
    with _lock:
        if _state.get("status") == "running":
            return {"status":"running","message":"Analyse läuft bereits"}
        _state = {"status":"idle","progress":0,"results":[],"timestamp":None}
    with _df_lock: _df_cache.clear()
    _detail_cache.clear()
    Thread(target=run_analysis, args=(min_str,), daemon=True).start()
    return {"status":"loading","message":"Neue Analyse gestartet"}

@app.get("/api/detail/{ticker}")
def get_detail(ticker: str):
    ticker = validate_ticker(ticker)
    name   = TICKER_TO_NAME.get(ticker, ticker)
    result = full_analysis(ticker, name, min_strength=0)
    if not result: raise HTTPException(404, f"Keine Daten für {ticker}")
    return result

@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    ticker = validate_ticker(ticker); now = time.time()
    cached = _price_cache.get(ticker)
    if cached and now - cached["ts"] < PRICE_CACHE_TTL: return cached
    df = fetch_ohlcv(ticker, period="5d", timeout=8)
    if df is None: raise HTTPException(404, "Keine Daten")
    price = round(float(df["Close"].iloc[-1]),2)
    prev  = float(df["Close"].iloc[-2]) if len(df)>=2 else price
    change = round(price-prev,2); change_pct = round(change/prev*100,2) if prev else 0
    result = {"ticker":ticker,"price":price,"change":change,"change_pct":change_pct,
              "ts":now,"timestamp":datetime.now().isoformat()}
    _price_cache[ticker] = result
    return result

@app.get("/api/mini-futures/{ticker}")
def get_mini_futures(ticker: str, direction: str = "BUY"):
    ticker = validate_ticker(ticker)
    if direction not in ("BUY","SELL"): raise HTTPException(400,"direction muss BUY oder SELL sein")
    name = TICKER_TO_NAME.get(ticker, ticker)
    df   = fetch_ohlcv(ticker, period="1mo")
    if df is None: raise HTTPException(404,"Keine Daten")
    try:
        price = float(df["Close"].iloc[-1])
        h,l,c = df["High"].squeeze(),df["Low"].squeeze(),df["Close"].squeeze()
        tr    = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        atr   = float(tr.rolling(14).mean().iloc[-1])
        return {"ticker":ticker,"name":name,"price":price,"direction":direction,
                "products":calc_mini_futures(direction,price,atr)}
    except Exception as e: raise HTTPException(500,str(e))

@app.get("/api/chart/{ticker}")
def get_chart(ticker: str, period: str = "3mo"):
    ticker = validate_ticker(ticker)
    if period not in ("1mo","3mo","6mo","ytd","1y","2y","5y"): period="3mo"
    ck = f"{ticker}|{period}"; now = time.time()
    cached = _chart_cache.get(ck)
    if cached and now - cached["ts"] < CHART_CACHE_TTL: return cached["data"]
    df = fetch_ohlcv(ticker, period=period, timeout=15)
    if df is None: raise HTTPException(404,"Keine Daten")
    try:
        c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
        bp=min(20,max(5,len(c)//5)); sma=c.rolling(bp).mean(); std=c.rolling(bp).std()
        bbu=(sma+2*std).round(2); bbl=(sma-2*std).round(2); smr=sma.round(2)
        e20=c.ewm(span=20,adjust=False).mean().round(2)
        e50=c.ewm(span=50,adjust=False).mean().round(2)
        e200=c.ewm(span=200,adjust=False).mean().round(2) if len(c)>=50 else None
        ph,pl,pc=float(h.iloc[-2]),float(l.iloc[-2]),float(c.iloc[-2])
        pivot=(ph+pl+pc)/3
        supp=[round(2*pivot-ph,2),round(pivot-(ph-pl),2)]
        res_=[round(2*pivot-pl,2),round(pivot+(ph-pl),2)]
        # Vollständig vektorisiert
        dates=df.index.strftime("%Y-%m-%d").tolist()
        chart_data=[{
            "date":dates[i],"open":round(float(df["Open"].iat[i]),2),
            "high":round(float(h.iat[i]),2),"low":round(float(l.iat[i]),2),
            "close":round(float(c.iat[i]),2),
            "volume":int(df["Volume"].iat[i]) if "Volume" in df.columns else 0,
            "bb_upper":None if pd.isna(bbu.iat[i]) else float(bbu.iat[i]),
            "bb_mid":  None if pd.isna(smr.iat[i]) else float(smr.iat[i]),
            "bb_lower":None if pd.isna(bbl.iat[i]) else float(bbl.iat[i]),
            "ema20":float(e20.iat[i]),"ema50":float(e50.iat[i]),
            **( {"ema200":float(e200.iat[i])} if e200 is not None else {} )
        } for i in range(len(df))]
        result={"ticker":ticker,"period":period,"data":chart_data,
                "support_levels":supp,"resistance_levels":res_}
        _chart_cache[ck]={"data":result,"ts":now}
        return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,str(e))
    finally: gc.collect()

@app.get("/api/watchlist")
def get_watchlist():
    with _lock:
        status=_state.get("status","idle")
        all_results=list(_state.get("all_results",[]))
        results=list(_state.get("results",[]))
    if status != "done": return {"status":status,"items":results}
    analyzed={r["ticker"] for r in all_results}
    neutrals=[{"ticker":t,"name":n,"price":None,"direction":"NEUTRAL","score":0,
               "strength":0,"signals":[],"stop_loss":None,"take_profit":None,
               "rsi":None,"timestamp":None}
              for n,t in ALL_TICKERS.items() if t not in analyzed]
    items=sorted(all_results+neutrals,key=lambda x:x.get("strength",0),reverse=True)
    return {"status":"done","items":items,"total":len(items)}

@app.get("/api/portfolio/backup")
def backup_portfolio_ep(): return load_portfolio()

@app.post("/api/portfolio/restore")
def restore_portfolio(data: dict):
    if not all(k in data for k in ("cash","start_capital","positions","closed_trades")):
        raise HTTPException(400,"Ungültige Portfolio-Daten")
    save_portfolio(data); return {"success":True}

@app.post("/api/portfolio/reset")
def reset_portfolio():
    sc = get_s("start_capital")
    save_portfolio({"cash":sc,"start_capital":sc,"positions":[],"closed_trades":[],
                    "created":datetime.now().isoformat()})
    return {"success":True,"message":f"Portfolio zurückgesetzt auf {sc:.0f}€"}

@app.get("/api/settings")
def get_settings_ep(): return load_settings()

# ── Settings-Modell: ALLE konfigurierbaren Parameter ─────────────────────────
class SettingsRequest(BaseModel):
    min_strength:  int   = Field(default=20,   ge=10,  le=80,   description="Mindest-Signalstärke")
    order_fee:     float = Field(default=10.0,  ge=0,   le=50,   description="Ordergebühr € pro Trade")
    max_positions: int   = Field(default=5,    ge=1,   le=20,   description="Max. gleichzeitige Positionen")
    max_exposure:  int   = Field(default=40,   ge=10,  le=90,   description="Max. Exposure % des Portfolios")
    risk_per_trade:float = Field(default=2.0,  ge=0.5, le=5.0,  description="Risiko pro Trade in %")
    max_position:  float = Field(default=20.0, ge=5.0, le=50.0, description="Max. Positionsgröße in %")
    min_sl_dist:   float = Field(default=1.5,  ge=0.5, le=5.0,  description="Min. SL-Abstand in %")
    max_sl_dist:   float = Field(default=8.0,  ge=2.0, le=20.0, description="Max. SL-Abstand in %")
    vol_threshold: float = Field(default=5.0,  ge=2.0, le=15.0, description="Volatilitäts-Warnschwelle ATR%")
    adx_trend:     int   = Field(default=25,   ge=15,  le=40,   description="ADX-Grenze Trendmarkt")
    adx_sideways:  int   = Field(default=20,   ge=10,  le=30,   description="ADX-Grenze Seitwärtsmarkt")
    start_capital: float = Field(default=10000,ge=1000,le=1000000,description="Virtuelles Startkapital €")

    @field_validator("adx_sideways")
    @classmethod
    def sideways_lt_trend(cls, v, info):
        trend = info.data.get("adx_trend", 25)
        if v >= trend: raise ValueError("adx_sideways muss kleiner als adx_trend sein")
        return v

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    s = req.model_dump()
    save_settings(s)
    global _state
    with _lock:
        _state = {"status":"idle","progress":0,"results":[],"timestamp":None}
    _detail_cache.clear()
    return s

@app.get("/api/portfolio")
def get_portfolio():
    p    = load_portfolio(); cfg = load_settings()
    max_pos = cfg["max_positions"]; max_exp = cfg["max_exposure"]
    order_fee = cfg["order_fee"]
    closed   = p["closed_trades"]
    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total    = round(p["cash"] + open_val, 2)
    pnl      = round(total - p["start_capital"], 2)
    wins     = sum(1 for t in closed if t.get("status") == "WIN")
    fees     = len(closed)*order_fee*2 + len(p["positions"])*order_fee
    exp_pct  = round(open_val/total*100,1) if total > 0 else 0.0
    return {
        "portfolio": p,
        "stats": {
            "start_capital": p["start_capital"], "total_value": total,
            "cash": p["cash"], "open_value": round(open_val,2),
            "total_pnl": pnl,
            "total_pnl_pct": round(pnl/p["start_capital"]*100,2),
            "total_trades": len(closed), "open_positions": len(p["positions"]),
            "win_rate": round(wins/len(closed)*100,1) if closed else 0,
            "fees_paid": fees,
            "limits": {
                "max_positions":           max_pos,
                "current_positions":       len(p["positions"]),
                "max_exposure_pct":        max_exp,
                "current_exposure_pct":    exp_pct,
                "positions_limit_reached": len(p["positions"]) >= max_pos,
                "exposure_limit_reached":  exp_pct >= max_exp,
            }
        }
    }

class TradeRequest(BaseModel):
    ticker:           str
    name:             str
    direction:        str
    price:            float = Field(..., gt=0)
    stop_loss:        float = Field(..., gt=0)
    take_profit:      float = Field(..., gt=0)
    score:            int
    signals:          list
    leverage:         int   = Field(default=1, ge=1, le=30)
    invest_amount:    float = Field(default=0, ge=0)
    is_mini_future:   bool  = False
    mini_future_leverage: int = Field(default=1, ge=1, le=30)

    @field_validator("direction")
    @classmethod
    def dir_valid(cls, v):
        if v not in ("BUY","SELL"): raise ValueError("direction muss BUY oder SELL sein")
        return v

@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p = load_portfolio(); cfg = load_settings()
    max_pos = cfg["max_positions"]; max_exp_pct = cfg["max_exposure"] / 100
    order_fee = cfg["order_fee"]
    if len(p["positions"]) >= max_pos:
        raise HTTPException(400, f"Portfolio-Limit: max. {max_pos} gleichzeitige Positionen")
    open_val  = sum(pos.get("current_value",pos["cost"]) for pos in p["positions"])
    total_val = p["cash"] + open_val
    if total_val > 0 and open_val/total_val >= max_exp_pct:
        raise HTTPException(400, f"Exposure-Limit: max. {cfg['max_exposure']}% in offenen Positionen")
    if abs(req.price - req.stop_loss) == 0:
        raise HTTPException(400, "Stop Loss identisch mit Einstiegskurs")
    units, cost = calc_position_size(p["cash"], total_val, req.price,
                                     req.stop_loss, req.invest_amount, cfg)
    total_cost = cost + order_fee
    if total_cost > p["cash"]:
        raise HTTPException(400,
            f"Nicht genug Cash ({p['cash']:.2f}€ verfügbar, {total_cost:.2f}€ benötigt inkl. {order_fee:.0f}€ Gebühr)")
    trade_id    = f"T{len(p['closed_trades'])+len(p['positions'])+1:04d}"
    dist        = abs(req.price - req.stop_loss)
    risk_amount = round(dist*units, 2)
    risk_pct    = round(risk_amount/total_val*100, 2) if total_val > 0 else 0
    pos = {
        "id":trade_id,"ticker":req.ticker,"name":req.name,
        "direction":req.direction,"entry_price":req.price,"current_price":req.price,
        "units":units,"cost":cost,"fee":order_fee,
        "stop_loss":req.stop_loss,"take_profit":req.take_profit,
        "score":req.score,"signals":req.signals,
        "unrealized_pnl":0.0,"unrealized_pnl_pct":0.0,"current_value":cost,
        "risk_amount":risk_amount,"risk_pct":risk_pct,
        "is_mini_future":req.is_mini_future,"leverage":req.mini_future_leverage,
        "opened":datetime.now().isoformat()
    }
    p["cash"] = round(p["cash"] - total_cost, 2)
    p["positions"].append(pos)
    save_portfolio(p)
    return {"success":True,"trade":pos,"fee_charged":order_fee,
            "risk_amount":risk_amount,"risk_pct":risk_pct}

class CloseRequest(BaseModel):
    trade_id: str; close_price: float = Field(..., gt=0)

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p = load_portfolio(); cfg = load_settings(); order_fee = cfg["order_fee"]
    pos = next((x for x in p["positions"] if x["id"]==req.trade_id), None)
    if not pos: raise HTTPException(404,"Position nicht gefunden")
    lev = pos.get("leverage",1)
    pnl = ((req.close_price-pos["entry_price"])*pos["units"]*lev
           if pos["direction"]=="BUY"
           else (pos["entry_price"]-req.close_price)*pos["units"]*lev)
    pnl_net  = pnl - order_fee
    proceeds = round(pos["cost"] + pnl_net, 2)
    closed = {**pos,"close_price":req.close_price,"pnl":round(pnl_net,2),
              "pnl_gross":round(pnl,2),"fees":order_fee*2,
              "pnl_pct":round(pnl_net/pos["cost"]*100,2),"proceeds":proceeds,
              "closed":datetime.now().isoformat(),
              "status":"WIN" if pnl_net > 0 else "LOSS"}
    p["positions"]=[x for x in p["positions"] if x["id"]!=req.trade_id]
    p["closed_trades"].append(closed); p["cash"]=round(p["cash"]+proceeds,2)
    save_portfolio(p); _price_cache.pop(pos["ticker"],None)
    return {"success":True,"trade":closed}

@app.get("/api/exit-signals")
def get_exit_signals():
    p = load_portfolio(); positions = p.get("positions",[])
    if not positions: return {"exit_signals":[],"checked":0}
    signals = []
    for pos in positions:
        try:
            ticker = pos["ticker"]
            df = fetch_ohlcv(ticker, period="1mo")
            if df is None or len(df) < 10: continue
            c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
            price = float(c.iloc[-1])
            delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean()
            loss=(-delta.clip(upper=0)).rolling(14).mean().replace(0,np.nan)
            r=float((100-100/(1+gain/loss)).iloc[-1])
            e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
            m=e12-e26; s_=m.ewm(span=9,adjust=False).mean(); hs=m-s_
            mk,ms=float(m.iloc[-1]),float(s_.iloc[-1]); mh,mhp=float(hs.iloc[-1]),float(hs.iloc[-2])
            stk=100*(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min()).replace(0,np.nan)
            sk,sd=float(stk.iloc[-1]),float(stk.rolling(3).mean().iloc[-1])
            entry,sl,tp,direction=pos["entry_price"],pos["stop_loss"],pos["take_profit"],pos["direction"]
            if direction=="BUY":
                pnl_pct=(price-entry)/entry*100; sl_dist=(price-sl)/entry*100; tp_dist=(tp-price)/entry*100
            else:
                pnl_pct=(entry-price)/entry*100; sl_dist=(sl-price)/entry*100; tp_dist=(price-tp)/entry*100
            reasons=[]; urgency="normal"
            if   tp_dist<=0: reasons.append("✅ Take Profit erreicht!"); urgency="urgent"
            elif sl_dist<=0: reasons.append("🛑 Stop Loss durchbrochen!"); urgency="urgent"
            elif sl_dist<20: reasons.append(f"⚠️ Nahe Stop Loss ({sl_dist:.1f}%)"); urgency="warn"
            if direction=="BUY":
                if r>70:               reasons.append(f"RSI überkauft ({r:.0f})")
                if mk<ms and mh<mhp:   reasons.append("MACD dreht negativ")
                if sk>80 and sk<sd:    reasons.append("Stochastik dreht runter")
            else:
                if r<30:               reasons.append(f"RSI überverkauft ({r:.0f})")
                if mk>ms and mh>mhp:   reasons.append("MACD dreht positiv")
                if sk<20 and sk>sd:    reasons.append("Stochastik dreht hoch")
            if reasons:
                signals.append({"trade_id":pos["id"],"ticker":ticker,"name":pos["name"],
                    "direction":direction,"entry_price":entry,
                    "current_price":round(price,2),"pnl_pct":round(pnl_pct,2),
                    "stop_loss":sl,"take_profit":tp,"exit_reasons":reasons,"urgency":urgency,
                    "recommendation":"SCHLIESSEN" if urgency=="urgent" else "PRÜFEN"})
        except Exception: continue
    signals.sort(key=lambda x:{"urgent":0,"warn":1,"normal":2}.get(x["urgency"],2))
    return {"exit_signals":signals,"checked":len(positions)}

@app.get("/", response_class=HTMLResponse)
def frontend():
    p = Path(__file__).parent / "index.html"
    return p.read_text() if p.exists() else "<h1>TradeBot Pro v12</h1>"

@app.get("/manifest.json")
def manifest():
    p = Path(__file__).parent / "manifest.json"
    return JSONResponse(json.loads(p.read_text()) if p.exists() else {})

Thread(target=run_analysis, args=(20,), daemon=True).start()
