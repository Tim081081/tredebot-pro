"""
TradeBot Pro v6 - Extended Indicators, Analyst Ratings, Mini Futures, 10€ Fee
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

ORDER_FEE = 10.0  # €

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
SETTINGS_FILE = "/tmp/settings.json"

_lock = Lock()
_state = {"status": "idle", "progress": 0, "results": [], "timestamp": None}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f: return json.load(f)
    return {"min_strength": 20}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f: json.dump(s, f)

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {"cash": 10000.0, "start_capital": 10000.0, "positions": [], "closed_trades": [], "created": datetime.now().isoformat()}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f: json.dump(p, f)

# ── Extended Technical Analysis ───────────────────────────────────────────────
def full_analysis(ticker, name, min_strength=60):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True, timeout=12)
        if df is None or df.empty or len(df) < 50:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        v = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)), index=c.index)

        price = float(c.iloc[-1])
        score = 0
        signals = []
        indicators = {}

        # ── RSI ───────────────────────────────────────────────────────────────
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1 + gain/loss.replace(0,np.nan))).iloc[-1])
        indicators["RSI (14)"] = round(rsi, 1)
        if rsi < 30: score += 20; signals.append(f"RSI überverkauft ({rsi:.0f})")
        elif rsi < 40: score += 10; signals.append(f"RSI schwach ({rsi:.0f})")
        elif rsi > 70: score -= 20; signals.append(f"RSI überkauft ({rsi:.0f})")
        elif rsi > 60: score -= 10; signals.append(f"RSI stark ({rsi:.0f})")

        # ── MACD ──────────────────────────────────────────────────────────────
        e12 = c.ewm(span=12, adjust=False).mean()
        e26 = c.ewm(span=26, adjust=False).mean()
        macd_line = e12 - e26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        mk, ms, mh, mhp = float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1]), float(hist.iloc[-2])
        indicators["MACD"] = round(mk, 4)
        indicators["MACD Signal"] = round(ms, 4)
        if mk > ms and mh > mhp: score += 20; signals.append("MACD bullisch ↑")
        elif mk < ms and mh < mhp: score -= 20; signals.append("MACD bärisch ↓")

        # ── Bollinger Bands ───────────────────────────────────────────────────
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        bb_upper = sma20 + 2*std20
        bb_lower = sma20 - 2*std20
        pb = float(((c - bb_lower)/(bb_upper - bb_lower)).iloc[-1])
        indicators["BB %B"] = round(pb, 2)
        indicators["BB Upper"] = round(float(bb_upper.iloc[-1]), 2)
        indicators["BB Lower"] = round(float(bb_lower.iloc[-1]), 2)
        if pb < 0.05: score += 20; signals.append("Unteres Bollinger Band")
        elif pb < 0.2: score += 10; signals.append("Nahe unterem BB")
        elif pb > 0.95: score -= 20; signals.append("Oberes Bollinger Band")
        elif pb > 0.8: score -= 10; signals.append("Nahe oberem BB")

        # ── Stochastic ────────────────────────────────────────────────────────
        ll = l.rolling(14).min()
        hh = h.rolling(14).max()
        stoch_k = 100*(c-ll)/(hh-ll).replace(0,np.nan)
        stoch_d = stoch_k.rolling(3).mean()
        sk, sd = float(stoch_k.iloc[-1]), float(stoch_d.iloc[-1])
        indicators["Stoch %K"] = round(sk, 1)
        indicators["Stoch %D"] = round(sd, 1)
        if sk < 20 and sk > sd: score += 15; signals.append(f"Stochastik dreht hoch ({sk:.0f})")
        elif sk > 80 and sk < sd: score -= 15; signals.append(f"Stochastik dreht runter ({sk:.0f})")

        # ── EMAs ──────────────────────────────────────────────────────────────
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        e50 = float(c.ewm(span=50).mean().iloc[-1])
        e100 = float(c.ewm(span=100).mean().iloc[-1])
        e200 = float(c.ewm(span=200).mean().iloc[-1]) if len(c) >= 200 else None
        indicators["EMA 20"] = round(e20, 2)
        indicators["EMA 50"] = round(e50, 2)
        indicators["EMA 100"] = round(e100, 2)
        if e200: indicators["EMA 200"] = round(e200, 2)
        if price > e20 > e50 > e100: score += 15; signals.append("Starker Auftrend (EMA 20>50>100)")
        elif price > e20 > e50: score += 10; signals.append("Auftrend EMA 20/50")
        elif price < e20 < e50 < e100: score -= 15; signals.append("Starker Abtrend (EMA 20<50<100)")
        elif price < e20 < e50: score -= 10; signals.append("Abtrend EMA 20/50")
        if e200:
            if price > e200: score += 5; signals.append("Über EMA 200 (Langzeittrend bullisch)")
            else: score -= 5; signals.append("Unter EMA 200 (Langzeittrend bärisch)")

        # ── ADX (Trendstärke) ─────────────────────────────────────────────────
        up_move = h.diff()
        down_move = -l.diff()
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        ndm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        pdi = 100 * pd.Series(pdm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0,np.nan)
        ndi = 100 * pd.Series(ndm, index=c.index).rolling(14).mean() / tr.rolling(14).mean().replace(0,np.nan)
        dx = 100 * (pdi-ndi).abs() / (pdi+ndi).replace(0,np.nan)
        adx = float(dx.rolling(14).mean().iloc[-1])
        indicators["ADX"] = round(adx, 1)
        indicators["+DI"] = round(float(pdi.iloc[-1]), 1)
        indicators["-DI"] = round(float(ndi.iloc[-1]), 1)
        if adx > 25:
            if float(pdi.iloc[-1]) > float(ndi.iloc[-1]): score += 10; signals.append(f"ADX starker Auftrend ({adx:.0f})")
            else: score -= 10; signals.append(f"ADX starker Abtrend ({adx:.0f})")
        else:
            signals.append(f"ADX schwacher Trend ({adx:.0f})")

        # ── Williams %R ───────────────────────────────────────────────────────
        hh14 = h.rolling(14).max()
        ll14 = l.rolling(14).min()
        willr = float((-100*(hh14-c)/(hh14-ll14).replace(0,np.nan)).iloc[-1])
        indicators["Williams %R"] = round(willr, 1)
        if willr < -80: score += 10; signals.append(f"Williams %R überverkauft ({willr:.0f})")
        elif willr > -20: score -= 10; signals.append(f"Williams %R überkauft ({willr:.0f})")

        # ── CCI ───────────────────────────────────────────────────────────────
        tp = (h + l + c) / 3
        cci = float(((tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())).iloc[-1])
        indicators["CCI (20)"] = round(cci, 1)
        if cci < -100: score += 10; signals.append(f"CCI überverkauft ({cci:.0f})")
        elif cci > 100: score -= 10; signals.append(f"CCI überkauft ({cci:.0f})")

        # ── OBV (Volumen) ─────────────────────────────────────────────────────
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        obv_ema = obv.ewm(span=20).mean()
        if float(obv.iloc[-1]) > float(obv_ema.iloc[-1]): score += 5; signals.append("OBV: Kaufvolumen steigt")
        else: score -= 5; signals.append("OBV: Verkaufsvolumen steigt")
        indicators["OBV Trend"] = "Bullisch" if float(obv.iloc[-1]) > float(obv_ema.iloc[-1]) else "Bärisch"

        # ── ATR Volatilität ───────────────────────────────────────────────────
        atr_pct = round(atr14 / price * 100, 2)
        indicators["ATR (14)"] = round(atr14, 2)
        indicators["ATR %"] = f"{atr_pct}%"

        # ── Pivot Points (Support/Resistance) ─────────────────────────────────
        prev_h = float(h.iloc[-2])
        prev_l = float(l.iloc[-2])
        prev_c = float(c.iloc[-2])
        pivot = (prev_h + prev_l + prev_c) / 3
        r1 = 2*pivot - prev_l
        r2 = pivot + (prev_h - prev_l)
        s1 = 2*pivot - prev_h
        s2 = pivot - (prev_h - prev_l)
        indicators["Pivot"] = round(pivot, 2)
        indicators["R1"] = round(r1, 2)
        indicators["R2"] = round(r2, 2)
        indicators["S1"] = round(s1, 2)
        indicators["S2"] = round(s2, 2)
        if price < s1: score += 8; signals.append(f"Unter Support S1 ({s1:.2f}) – mögliche Bounce-Zone")
        elif price > r1: score -= 8; signals.append(f"Über Resistance R1 ({r1:.2f}) – möglicher Widerstand")

        # ── 52-Wochen Hoch/Tief ───────────────────────────────────────────────
        w52_high = float(h.rolling(252).max().iloc[-1])
        w52_low = float(l.rolling(252).min().iloc[-1])
        w52_pct = round((price - w52_low) / (w52_high - w52_low) * 100, 1) if w52_high != w52_low else 50
        indicators["52W Hoch"] = round(w52_high, 2)
        indicators["52W Tief"] = round(w52_low, 2)
        indicators["52W Position"] = f"{w52_pct}%"
        if w52_pct < 15: score += 10; signals.append(f"Nahe 52W-Tief ({w52_pct:.0f}% von unten)")
        elif w52_pct > 85: score -= 10; signals.append(f"Nahe 52W-Hoch ({w52_pct:.0f}% von unten)")

        # ── Momentum (ROC) ────────────────────────────────────────────────────
        roc10 = float(((c - c.shift(10)) / c.shift(10) * 100).iloc[-1])
        indicators["ROC (10)"] = f"{roc10:.1f}%"
        if roc10 > 5: score -= 5; signals.append(f"Starkes positives Momentum (+{roc10:.1f}%)")
        elif roc10 < -5: score += 5; signals.append(f"Starkes negatives Momentum ({roc10:.1f}%)")

        # ── Analyst Ratings via Yahoo ─────────────────────────────────────────
        analyst_info = {}
        try:
            t = yf.Ticker(ticker)
            info = t.info
            rec = info.get("recommendationMean")
            n_analysts = info.get("numberOfAnalystOpinions", 0)
            target = info.get("targetMeanPrice")
            if rec and n_analysts:
                rec_text = {1:"Starker Kauf", 2:"Kauf", 3:"Halten", 4:"Verkauf", 5:"Starker Verkauf"}.get(round(rec), f"{rec:.1f}")
                analyst_info = {"recommendation": rec_text, "analysts": n_analysts, "target": round(target, 2) if target else None}
                indicators["Analysten"] = f"{rec_text} ({n_analysts} Analysten)"
                if target: indicators["Kursziel"] = f"{target:.2f}"
                if rec <= 2: score += 10; signals.append(f"Analysten: {rec_text} ({n_analysts}x)")
                elif rec >= 4: score -= 10; signals.append(f"Analysten: {rec_text} ({n_analysts}x)")
        except:
            pass

        if abs(score) < min_strength:
            return None

        direction = "BUY" if score > 0 else "SELL"
        sl = round(price - 1.5*atr14, 2) if direction == "BUY" else round(price + 1.5*atr14, 2)
        tp = round(price + 3*atr14, 2) if direction == "BUY" else round(price - 3*atr14, 2)

        # Chart data (last 90 days)
        chart_data = []
        df90 = df.tail(90)
        bb_u = (sma20 + 2*std20).tail(90)
        bb_m = sma20.tail(90)
        bb_l = (sma20 - 2*std20).tail(90)
        ema20_s = c.ewm(span=20).mean().tail(90)
        ema50_s = c.ewm(span=50).mean().tail(90)
        for i in range(len(df90)):
            try:
                chart_data.append({
                    "date": df90.index[i].strftime("%Y-%m-%d"),
                    "open": round(float(df90["Open"].iloc[i]), 2),
                    "high": round(float(df90["High"].iloc[i]), 2),
                    "low": round(float(df90["Low"].iloc[i]), 2),
                    "close": round(float(df90["Close"].iloc[i]), 2),
                    "volume": int(df90["Volume"].iloc[i]) if "Volume" in df90.columns else 0,
                    "bb_upper": round(float(bb_u.iloc[i]), 2),
                    "bb_mid": round(float(bb_m.iloc[i]), 2),
                    "bb_lower": round(float(bb_l.iloc[i]), 2),
                    "ema20": round(float(ema20_s.iloc[i]), 2),
                    "ema50": round(float(ema50_s.iloc[i]), 2),
                })
            except:
                pass

        return {
            "ticker": ticker, "name": name, "price": round(price, 2),
            "direction": direction, "score": int(score),
            "strength": min(100, abs(int(score))), "signals": signals,
            "stop_loss": sl, "take_profit": tp,
            "rsi": round(rsi, 1), "atr": round(atr14, 2),
            "indicators": indicators, "analyst": analyst_info,
            "chart_data": chart_data,
            "support_levels": [round(s1,2), round(s2,2)],
            "resistance_levels": [round(r1,2), round(r2,2)],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return None

def quick_score(ticker, name, min_strength):
    """Lightweight version for scanning - no chart data, shorter period"""
    import time, gc
    try:
        df = yf.download(ticker, period="3mo", interval="1d",
                        progress=False, auto_adjust=True, timeout=8)
        if df is None or df.empty or len(df) < 30:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        price = float(c.iloc[-1])

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1 + gain/loss.replace(0,np.nan))).iloc[-1])

        # MACD
        e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
        macd_l=e12-e26; sig_l=macd_l.ewm(span=9,adjust=False).mean(); hist=macd_l-sig_l
        mk,ms,mh,mhp=float(macd_l.iloc[-1]),float(sig_l.iloc[-1]),float(hist.iloc[-1]),float(hist.iloc[-2])

        # Bollinger
        sma20=c.rolling(20).mean(); std20=c.rolling(20).std()
        pb=float(((c-(sma20-2*std20))/(4*std20)).iloc[-1])

        # Stochastic
        sk_s=100*(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min()).replace(0,np.nan)
        sk,sd=float(sk_s.iloc[-1]),float(sk_s.rolling(3).mean().iloc[-1])

        # EMA
        e20=float(c.ewm(span=20).mean().iloc[-1]); e50=float(c.ewm(span=50).mean().iloc[-1])

        # ATR
        tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        atr=float(tr.rolling(14).mean().iloc[-1])

        # ADX
        up_move=h.diff(); down_move=-l.diff()
        pdm=np.where((up_move>down_move)&(up_move>0),up_move,0.0)
        ndm=np.where((down_move>up_move)&(down_move>0),down_move,0.0)
        pdi=100*pd.Series(pdm,index=c.index).rolling(14).mean()/tr.rolling(14).mean().replace(0,np.nan)
        ndi=100*pd.Series(ndm,index=c.index).rolling(14).mean()/tr.rolling(14).mean().replace(0,np.nan)
        adx=float(((pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)).rolling(14).mean().iloc[-1]*100)

        # Free memory immediately
        del df, c, h, l, tr, delta, gain, loss, e12, e26, macd_l, sig_l, hist
        del sma20, std20, sk_s, up_move, down_move, pdm, ndm, pdi, ndi
        gc.collect()

        score=0; signals=[]
        if rsi<30: score+=20; signals.append(f"RSI überverkauft ({rsi:.0f})")
        elif rsi<40: score+=10; signals.append(f"RSI schwach ({rsi:.0f})")
        elif rsi>70: score-=20; signals.append(f"RSI überkauft ({rsi:.0f})")
        elif rsi>60: score-=10; signals.append(f"RSI stark ({rsi:.0f})")
        if mk>ms and mh>mhp: score+=20; signals.append("MACD bullisch ↑")
        elif mk<ms and mh<mhp: score-=20; signals.append("MACD bärisch ↓")
        if pb<0.05: score+=20; signals.append("Unteres Bollinger Band")
        elif pb<0.2: score+=10; signals.append("Nahe unterem BB")
        elif pb>0.95: score-=20; signals.append("Oberes Bollinger Band")
        elif pb>0.8: score-=10; signals.append("Nahe oberem BB")
        if sk<20 and sk>sd: score+=15; signals.append(f"Stochastik dreht hoch ({sk:.0f})")
        elif sk>80 and sk<sd: score-=15; signals.append(f"Stochastik dreht runter ({sk:.0f})")
        if price>e20>e50: score+=10; signals.append("Auftrend EMA")
        elif price<e20<e50: score-=10; signals.append("Abtrend EMA")
        if adx>25:
            if float(pdi.iloc[-1] if hasattr(pdi,'iloc') else 0) > float(ndi.iloc[-1] if hasattr(ndi,'iloc') else 0):
                score+=10; signals.append(f"ADX Auftrend ({adx:.0f})")
            else: score-=10; signals.append(f"ADX Abtrend ({adx:.0f})")

        if abs(score) < min_strength: return None

        direction="BUY" if score>0 else "SELL"
        sl=round(price-1.5*atr,2) if direction=="BUY" else round(price+1.5*atr,2)
        tp=round(price+3*atr,2) if direction=="BUY" else round(price-3*atr,2)

        return {"ticker":ticker,"name":name,"price":round(price,2),"direction":direction,
                "score":int(score),"strength":min(100,abs(int(score))),"signals":signals,
                "stop_loss":sl,"take_profit":tp,"rsi":round(rsi,1),"atr":round(atr,2),
                "indicators":{"RSI":round(rsi,1),"MACD":round(mk,4),"BB %B":round(pb,2),
                               "Stoch %K":round(sk,1),"EMA 20":round(e20,2),"EMA 50":round(e50,2),
                               "ADX":round(adx,1),"ATR":round(atr,2)},
                "analyst":{},"chart_data":[],"support_levels":[],"resistance_levels":[],
                "timestamp":datetime.now().isoformat()}
    except Exception as e:
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
            _state["results"] = results_sorted[:15]
        # Small pause every 5 tickers to prevent memory overflow
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
    """Generate 15 synthetic Mini Future combinations (BNP Paribas style)"""
    products = []
    leverages = [2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 20, 22, 25, 28, 30]

    for lev in leverages:
        if direction == "BUY":
            # Knock-out level below current price
            ko_distance_pct = 1.0 / lev
            knock_out = round(price * (1 - ko_distance_pct), 2)
            # Stop loss slightly above knock-out for buffer
            stop_loss = round(knock_out * 1.005, 2)
            # Mini future price = (price - knock_out) / ratio (ratio=1 for simplicity)
            mf_price = round((price - knock_out) * 1.02, 2)  # 2% premium
            take_profit = round(price + 2 * atr, 2)
            max_loss_pct = round(ko_distance_pct * 100, 1)
        else:
            ko_distance_pct = 1.0 / lev
            knock_out = round(price * (1 + ko_distance_pct), 2)
            stop_loss = round(knock_out * 0.995, 2)
            mf_price = round((knock_out - price) * 1.02, 2)
            take_profit = round(price - 2 * atr, 2)
            max_loss_pct = round(ko_distance_pct * 100, 1)

        potential_gain = round(atr * 2 * lev / mf_price * 100, 1) if mf_price > 0 else 0

        products.append({
            "leverage": lev,
            "direction": direction,
            "base_price": round(price, 2),
            "knock_out": knock_out,
            "stop_loss_level": stop_loss,
            "mini_future_price": mf_price,
            "take_profit": take_profit,
            "max_loss_pct": max_loss_pct,
            "potential_gain_pct": potential_gain,
            "risk_level": "Niedrig" if lev <= 5 else "Mittel" if lev <= 15 else "Hoch",
            "label": f"x{lev} {'Long' if direction=='BUY' else 'Short'} – KO: {knock_out}"
        })

    return products

# ── API ───────────────────────────────────────────────────────────────────────
@app.get("/api/signals")
def get_signals():
    s = load_settings()
    min_str = s.get("min_strength", 60)
    with _lock:
        status = _state.get("status", "idle")
        progress = _state.get("progress", 0)
        results = _state.get("results", [])
        ts = _state.get("timestamp")
        found = _state.get("signals_found", len(results))
        analyzed = _state.get("total_analyzed", 0)
    if status == "idle":
        Thread(target=run_analysis, args=(min_str,), daemon=True).start()
        return {"status":"loading","progress":0,"top_signals":[],"total_analyzed":0,"signals_found":0}
    return {"status":status,"progress":progress,"top_signals":results,
            "total_analyzed":analyzed,"signals_found":found,"timestamp":ts}

@app.post("/api/signals/refresh")
def refresh_signals():
    global _state
    s = load_settings()
    min_str = s.get("min_strength", 60)
    with _lock:
        if _state.get("status") == "running":
            return {"status":"running","message":"Analyse läuft bereits"}
        _state = {"status":"idle","progress":0,"results":[],"timestamp":None}
    Thread(target=run_analysis, args=(min_str,), daemon=True).start()
    return {"status":"loading","message":"Neue Analyse gestartet"}

@app.get("/api/detail/{ticker}")
def get_detail(ticker: str):
    """Full detail analysis for a single ticker"""
    # Find name
    name = next((k for k,v in ALL_TICKERS.items() if v==ticker), ticker)
    result = full_analysis(ticker, name, min_strength=0)
    if not result:
        raise HTTPException(404, f"Keine Daten für {ticker}")
    return result

@app.get("/api/mini-futures/{ticker}")
def get_mini_futures(ticker: str, direction: str = "BUY"):
    name = next((k for k,v in ALL_TICKERS.items() if v==ticker), ticker)
    try:
        df = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True, timeout=8)
        if df is None or df.empty:
            raise HTTPException(404, "Keine Daten")
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        price = float(df["Close"].iloc[-1])
        h = df["High"].squeeze(); l = df["Low"].squeeze(); c_col = df["Close"].squeeze()
        tr = pd.concat([h-l,(h-c_col.shift()).abs(),(l-c_col.shift()).abs()],axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        products = calc_mini_futures(ticker, direction, price, atr)
        return {"ticker": ticker, "name": name, "price": price, "direction": direction, "products": products}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/portfolio/backup")
def backup_portfolio():
    """Export portfolio as JSON for client-side storage"""
    return load_portfolio()

@app.post("/api/portfolio/restore")
def restore_portfolio(data: dict):
    """Restore portfolio from client-side backup"""
    required = ["cash", "start_capital", "positions", "closed_trades"]
    if not all(k in data for k in required):
        raise HTTPException(400, "Ungültige Portfolio-Daten")
    save_portfolio(data)
    return {"success": True, "message": "Portfolio wiederhergestellt"}

@app.get("/api/settings")
def get_settings_ep(): return load_settings()

class SettingsRequest(BaseModel):
    min_strength: int

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    if not 10 <= req.min_strength <= 100:
        raise HTTPException(400, "Stärke zwischen 20 und 100")
    s = load_settings(); s["min_strength"] = req.min_strength; save_settings(s)
    global _state
    with _lock: _state = {"status":"idle","progress":0,"results":[],"timestamp":None}
    return s

@app.get("/api/portfolio")
def get_portfolio():
    p = load_portfolio()
    closed = p["closed_trades"]
    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total = round(p["cash"] + open_val, 2)
    pnl = round(total - p["start_capital"], 2)
    wins = [t for t in closed if t.get("status") == "WIN"]
    fees_paid = len(closed) * ORDER_FEE * 2 + len(p["positions"]) * ORDER_FEE
    stats = {"start_capital":p["start_capital"],"total_value":total,"cash":p["cash"],
             "open_value":round(open_val,2),"total_pnl":pnl,
             "total_pnl_pct":round(pnl/p["start_capital"]*100,2),
             "total_trades":len(closed),"open_positions":len(p["positions"]),
             "win_rate":round(len(wins)/len(closed)*100,1) if closed else 0,
             "fees_paid":fees_paid}
    return {"portfolio":p,"stats":stats}

class TradeRequest(BaseModel):
    ticker:str; name:str; direction:str; price:float
    stop_loss:float; take_profit:float; score:int
    signals:list; leverage:int=1; invest_amount:float=0
    is_mini_future:bool=False; mini_future_leverage:int=1

@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p = load_portfolio()
    distance = abs(req.price - req.stop_loss)
    if distance == 0:
        raise HTTPException(400, "Stop loss identisch mit Preis")
    if req.invest_amount > 0:
        cost = round(min(req.invest_amount, p["cash"] - ORDER_FEE), 2)
        units = round(cost / req.price, 4)
    else:
        units = round((p["cash"] * 0.05) / distance, 4)
        cost = round(req.price * units, 2)
    total_cost = cost + ORDER_FEE
    if total_cost > p["cash"]:
        raise HTTPException(400, f"Nicht genug Cash ({p['cash']:.2f}€, inkl. 10€ Gebühr)")
    trade_id = f"T{len(p['closed_trades'])+len(p['positions'])+1:04d}"
    pos = {"id":trade_id,"ticker":req.ticker,"name":req.name,"direction":req.direction,
           "entry_price":req.price,"current_price":req.price,"units":units,"cost":cost,
           "fee":ORDER_FEE,"stop_loss":req.stop_loss,"take_profit":req.take_profit,
           "score":req.score,"signals":req.signals,"unrealized_pnl":0.0,
           "unrealized_pnl_pct":0.0,"current_value":cost,
           "is_mini_future":req.is_mini_future,"leverage":req.mini_future_leverage,
           "opened":datetime.now().isoformat()}
    p["cash"] = round(p["cash"] - total_cost, 2)
    p["positions"].append(pos)
    save_portfolio(p)
    return {"success":True,"trade":pos,"fee_charged":ORDER_FEE}

class CloseRequest(BaseModel):
    trade_id:str; close_price:float

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p = load_portfolio()
    pos = next((x for x in p["positions"] if x["id"]==req.trade_id), None)
    if not pos: raise HTTPException(404, "Position nicht gefunden")
    lev = pos.get("leverage", 1)
    pnl = (req.close_price-pos["entry_price"])*pos["units"]*lev if pos["direction"]=="BUY" else (pos["entry_price"]-req.close_price)*pos["units"]*lev
    pnl_after_fee = pnl - ORDER_FEE
    proceeds = round(pos["cost"] + pnl_after_fee, 2)
    closed = {**pos,"close_price":req.close_price,"pnl":round(pnl_after_fee,2),
              "pnl_gross":round(pnl,2),"fees":ORDER_FEE*2,
              "pnl_pct":round(pnl_after_fee/pos["cost"]*100,2),"proceeds":proceeds,
              "closed":datetime.now().isoformat(),"status":"WIN" if pnl_after_fee>0 else "LOSS"}
    p["positions"] = [x for x in p["positions"] if x["id"]!=req.trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"]+proceeds, 2)
    save_portfolio(p)
    return {"success":True,"trade":closed}

@app.get("/api/exit-signals")
def get_exit_signals():
    p = load_portfolio()
    positions = p.get("positions", [])
    if not positions: return {"exit_signals":[],"checked":0}
    signals = []
    for pos in positions:
        try:
            ticker = pos["ticker"]
            df = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True, timeout=8)
            if df is None or df.empty or len(df)<10: continue
            df.columns = [c[0] if isinstance(c,tuple) else c for c in df.columns]
            c = df["Close"].squeeze(); h = df["High"].squeeze(); l = df["Low"].squeeze()
            price = float(c.iloc[-1])
            delta = c.diff()
            r = float((100-100/(1+(delta.clip(lower=0).rolling(14).mean()/(-delta.clip(upper=0)).rolling(14).mean().replace(0,np.nan)))).iloc[-1])
            e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
            m=e12-e26; s=m.ewm(span=9,adjust=False).mean(); hist=m-s
            mk,ms,mh,mhp=float(m.iloc[-1]),float(s.iloc[-1]),float(hist.iloc[-1]),float(hist.iloc[-2])
            ll=l.rolling(14).min(); hh=h.rolling(14).max()
            sk_s=100*(c-ll)/(hh-ll).replace(0,np.nan)
            sk,sd=float(sk_s.iloc[-1]),float(sk_s.rolling(3).mean().iloc[-1])
            entry=pos["entry_price"]; sl=pos["stop_loss"]; tp=pos["take_profit"]; direction=pos["direction"]
            if direction=="BUY":
                pnl_pct=(price-entry)/entry*100; sl_dist=(price-sl)/entry*100; tp_dist=(tp-price)/entry*100
            else:
                pnl_pct=(entry-price)/entry*100; sl_dist=(sl-price)/entry*100; tp_dist=(price-tp)/entry*100
            reasons=[]; urgency="normal"
            if tp_dist<=0: reasons.append("✅ Take Profit erreicht!"); urgency="urgent"
            elif sl_dist<=0: reasons.append("🛑 Stop Loss durchbrochen!"); urgency="urgent"
            elif sl_dist<20: reasons.append(f"⚠️ Nahe Stop Loss ({sl_dist:.1f}%)"); urgency="warn"
            if direction=="BUY":
                if r>70: reasons.append(f"RSI überkauft ({r:.0f})")
                if mk<ms and mh<mhp: reasons.append("MACD dreht negativ")
                if sk>80 and sk<sd: reasons.append("Stochastik dreht runter")
            else:
                if r<30: reasons.append(f"RSI überverkauft ({r:.0f})")
                if mk>ms and mh>mhp: reasons.append("MACD dreht positiv")
                if sk<20 and sk>sd: reasons.append("Stochastik dreht hoch")
            if reasons:
                signals.append({"trade_id":pos["id"],"ticker":ticker,"name":pos["name"],
                    "direction":direction,"entry_price":entry,"current_price":round(price,2),
                    "pnl_pct":round(pnl_pct,2),"stop_loss":sl,"take_profit":tp,
                    "exit_reasons":reasons,"urgency":urgency,
                    "recommendation":"SCHLIESSEN" if urgency=="urgent" else "PRÜFEN"})
        except: continue
    signals.sort(key=lambda x:{"urgent":0,"warn":1,"normal":2}.get(x["urgency"],2))
    return {"exit_signals":signals,"checked":len(positions)}

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>TradeBot Pro</h1>"

@app.get("/manifest.json")
def manifest():
    mf_path = Path(__file__).parent / "manifest.json"
    if mf_path.exists(): return JSONResponse(json.loads(mf_path.read_text()))
    return JSONResponse({})

Thread(target=run_analysis, args=(20,), daemon=True).start()
