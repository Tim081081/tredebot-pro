"""
TradeBot Pro v4 - Alle DAX & Euro Stoxx 50 Werte + Async Background Analysis
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
from threading import Thread

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Alle 40 DAX Werte ─────────────────────────────────────────────────────────
DAX_STOCKS = [
    "ADS.DE","AIR.DE","ALV.DE","BAS.DE","BAYN.DE","BEI.DE","BMW.DE","BNR.DE",
    "CON.DE","1COV.DE","DHER.DE","DHL.DE","DTE.DE","DTG.DE","ENR.DE","EOAN.DE",
    "FME.DE","FRE.DE","HEI.DE","HEN3.DE","HFG.DE","HOT.DE","IFX.DE","LIN.DE",
    "MBG.DE","MEO.DE","MRK.DE","MTX.DE","MUV2.DE","NDA.DE","P911.DE","PAH3.DE",
    "QIA.DE","RHM.DE","RWE.DE","SAP.DE","SHL.DE","SIE.DE","SY1.DE","VOW3.DE",
    "VNA.DE","ZAL.DE"
]

# ── Alle 50 Euro Stoxx Werte ──────────────────────────────────────────────────
EUROSTOXX_STOCKS = [
    "ASML.AS","INGA.AS","PHIA.AS","AD.AS","WKL.AS","ABN.AS",
    "MC.PA","OR.PA","TTE.PA","SAN.PA","AIR.PA","BNP.PA","ACA.PA","GLE.PA","KER.PA","RI.PA","DSY.PA","EL.PA",
    "SAN.MC","BBVA.MC","ITX.MC","REP.MC",
    "NESN.SW","ROG.SW","NOVN.SW","ABBN.SW","CSGN.SW",
    "AZN.L","HSBA.L","BP.L","SHEL.L","GSK.L","ULVR.L","RIO.L","BT-A.L",
    "ENEL.MI","ENI.MI","ISP.MI","UCG.MI","STM.MI",
    "MUV2.DE","ALV.DE","SIE.DE","SAP.DE","BAS.DE","BAYN.DE","DTE.DE","BMW.DE","MBG.DE","VOW3.DE"
]

# Indizes
INDICES = {
    "DAX": "^GDAXI",
    "Euro Stoxx 50": "^STOXX50E",
    "FTSE 100": "^FTSE",
    "CAC 40": "^FCHI",
    "IBEX 35": "^IBEX",
    "AEX": "^AEX",
    "SMI": "^SSMI",
    "ATX": "^ATX",
    "MIB": "FTSEMIB.MI",
}

# Alle Einzelwerte (dedupliziert)
ALL_STOCKS = list(dict.fromkeys(DAX_STOCKS + EUROSTOXX_STOCKS))

PORTFOLIO_FILE = "/tmp/portfolio.json"
SETTINGS_FILE = "/tmp/settings.json"

# ── Global State ──────────────────────────────────────────────────────────────
_cache = {"status": "idle", "data": None}
_running = False

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"min_strength": 60}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f)

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {"cash": 10000.0, "start_capital": 10000.0, "positions": [], "closed_trades": [], "created": datetime.now().isoformat()}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f)

# ── Indikatoren ───────────────────────────────────────────────────────────────
def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(close):
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    m = e12 - e26
    s = m.ewm(span=9, adjust=False).mean()
    return m, s, m - s

def bollinger(close, period=20):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    pct_b = (close - (sma - 2*std)) / (4*std).replace(0, np.nan)
    return pct_b

def stochastic(high, low, close, k=14, d=3):
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    k_val = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return k_val, k_val.rolling(d).mean()

def atr_calc(high, low, close, period=14):
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def score_ticker(ticker, name, min_strength):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 30:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()

        r = float(rsi(c).iloc[-1])
        mk, ms, mh = macd(c)
        pb = float(bollinger(c).iloc[-1])
        sk, sd = stochastic(h, l, c)
        sk_val, sd_val = float(sk.iloc[-1]), float(sd.iloc[-1])
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        e50 = float(c.ewm(span=50).mean().iloc[-1])
        atr_val = float(atr_calc(h, l, c).iloc[-1])
        price = float(c.iloc[-1])
        mk_val, ms_val = float(mk.iloc[-1]), float(ms.iloc[-1])
        mh_val, mh_prev = float(mh.iloc[-1]), float(mh.iloc[-2])

        score = 0
        signals = []
        if r < 30: score += 20; signals.append(f"RSI überverkauft ({r:.1f})")
        elif r < 40: score += 10; signals.append(f"RSI schwach ({r:.1f})")
        elif r > 70: score -= 20; signals.append(f"RSI überkauft ({r:.1f})")
        elif r > 60: score -= 10; signals.append(f"RSI stark ({r:.1f})")
        if mk_val > ms_val and mh_val > mh_prev: score += 20; signals.append("MACD bullisch")
        elif mk_val < ms_val and mh_val < mh_prev: score -= 20; signals.append("MACD bärisch")
        if pb < 0.05: score += 20; signals.append("Unteres Bollinger Band")
        elif pb < 0.2: score += 10; signals.append("Nahe unterem BB")
        elif pb > 0.95: score -= 20; signals.append("Oberes Bollinger Band")
        elif pb > 0.8: score -= 10; signals.append("Nahe oberem BB")
        if sk_val < 20 and sk_val > sd_val: score += 15; signals.append(f"Stochastik dreht hoch ({sk_val:.1f})")
        elif sk_val > 80 and sk_val < sd_val: score -= 15; signals.append(f"Stochastik dreht runter ({sk_val:.1f})")
        if price > e20 > e50: score += 10; signals.append("Auftrend EMA20/50")
        elif price < e20 < e50: score -= 10; signals.append("Abtrend EMA20/50")

        if abs(score) < min_strength:
            return None

        direction = "BUY" if score > 0 else "SELL"
        sl = round(price - 1.5*atr_val, 2) if direction == "BUY" else round(price + 1.5*atr_val, 2)
        tp = round(price + 3*atr_val, 2) if direction == "BUY" else round(price - 3*atr_val, 2)

        return {"ticker": ticker, "name": name, "price": round(price, 2), "direction": direction,
                "score": int(score), "strength": min(100, abs(int(score))), "signals": signals,
                "stop_loss": sl, "take_profit": tp, "rsi": round(r, 1),
                "timestamp": datetime.now().isoformat()}
    except:
        return None

# ── Hintergrundanalyse ────────────────────────────────────────────────────────
def run_analysis_background(min_strength=60):
    global _running, _cache
    if _running:
        return
    _running = True
    _cache["status"] = "running"
    try:
        results = []
        all_tickers = list(INDICES.items()) + [(t, t) for t in ALL_STOCKS]
        total = len(all_tickers)
        for i, (name, ticker) in enumerate(all_tickers):
            sig = score_ticker(ticker, name, min_strength)
            if sig:
                results.append(sig)
            _cache["progress"] = round((i+1)/total*100)
        results.sort(key=lambda x: x["strength"], reverse=True)
        _cache = {
            "status": "done",
            "timestamp": datetime.now().isoformat(),
            "total_analyzed": total,
            "signals_found": len(results),
            "top_signals": results[:10],
            "all_signals": results,
            "min_strength": min_strength,
            "progress": 100
        }
    except Exception as e:
        _cache["status"] = "error"
    finally:
        _running = False

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/signals")
def get_signals():
    global _running
    settings = load_settings()
    min_str = settings.get("min_strength", 60)
    if _cache.get("status") == "done":
        return _cache
    if not _running:
        Thread(target=run_analysis_background, args=(min_str,), daemon=True).start()
    return {"status": "loading", "progress": _cache.get("progress", 0),
            "message": f"Analyse läuft... {_cache.get('progress', 0)}% – bitte warten",
            "top_signals": [], "total_analyzed": 0, "signals_found": 0}

@app.post("/api/signals/refresh")
def refresh_signals():
    global _cache, _running
    settings = load_settings()
    min_str = settings.get("min_strength", 60)
    _cache = {"status": "idle", "progress": 0}
    if not _running:
        Thread(target=run_analysis_background, args=(min_str,), daemon=True).start()
    return {"status": "loading", "message": "Neue Analyse gestartet"}

@app.get("/api/signals/status")
def signals_status():
    return {"status": _cache.get("status","idle"), "progress": _cache.get("progress",0), "running": _running}

@app.get("/api/settings")
def get_settings_ep():
    return load_settings()

class SettingsRequest(BaseModel):
    min_strength: int

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    if not 20 <= req.min_strength <= 100:
        raise HTTPException(400, "Stärke zwischen 20 und 100")
    s = load_settings()
    s["min_strength"] = req.min_strength
    save_settings(s)
    global _cache
    _cache = {"status": "idle", "progress": 0}
    return s

@app.get("/api/portfolio")
def get_portfolio():
    p = load_portfolio()
    closed = p["closed_trades"]
    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total = round(p["cash"] + open_val, 2)
    pnl = round(total - p["start_capital"], 2)
    wins = [t for t in closed if t.get("status") == "WIN"]
    stats = {"start_capital": p["start_capital"], "total_value": total, "cash": p["cash"],
             "open_value": round(open_val, 2), "total_pnl": pnl,
             "total_pnl_pct": round(pnl / p["start_capital"] * 100, 2),
             "total_trades": len(closed), "open_positions": len(p["positions"]),
             "win_rate": round(len(wins)/len(closed)*100, 1) if closed else 0}
    return {"portfolio": p, "stats": stats}

class TradeRequest(BaseModel):
    ticker: str; name: str; direction: str; price: float
    stop_loss: float; take_profit: float; score: int
    signals: list; leverage: int = 1; invest_amount: float = 0

@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p = load_portfolio()
    distance = abs(req.price - req.stop_loss)
    if distance == 0:
        raise HTTPException(400, "Stop loss identisch mit Preis")
    if req.invest_amount > 0:
        cost = round(min(req.invest_amount, p["cash"]), 2)
        units = round(cost / req.price, 4)
    else:
        units = round((p["cash"] * 0.05) / distance, 4)
        cost = round(req.price * units, 2)
    if cost > p["cash"]:
        raise HTTPException(400, f"Nicht genug Cash ({p['cash']:.2f}€)")
    trade_id = f"T{len(p['closed_trades'])+len(p['positions'])+1:04d}"
    pos = {"id": trade_id, "ticker": req.ticker, "name": req.name, "direction": req.direction,
           "entry_price": req.price, "current_price": req.price, "units": units, "cost": cost,
           "stop_loss": req.stop_loss, "take_profit": req.take_profit, "score": req.score,
           "signals": req.signals, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0,
           "current_value": cost, "opened": datetime.now().isoformat()}
    p["cash"] = round(p["cash"] - cost, 2)
    p["positions"].append(pos)
    save_portfolio(p)
    return {"success": True, "trade": pos}

class CloseRequest(BaseModel):
    trade_id: str; close_price: float

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p = load_portfolio()
    pos = next((x for x in p["positions"] if x["id"] == req.trade_id), None)
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    pnl = (req.close_price - pos["entry_price"]) * pos["units"] if pos["direction"] == "BUY" else (pos["entry_price"] - req.close_price) * pos["units"]
    proceeds = round(pos["cost"] + pnl, 2)
    closed = {**pos, "close_price": req.close_price, "pnl": round(pnl, 2),
              "pnl_pct": round(pnl/pos["cost"]*100, 2), "proceeds": proceeds,
              "closed": datetime.now().isoformat(), "status": "WIN" if pnl > 0 else "LOSS"}
    p["positions"] = [x for x in p["positions"] if x["id"] != req.trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"] + proceeds, 2)
    save_portfolio(p)
    return {"success": True, "trade": closed}

@app.get("/api/exit-signals")
def get_exit_signals():
    p = load_portfolio()
    positions = p.get("positions", [])
    if not positions:
        return {"exit_signals": [], "checked": 0}
    signals = []
    for pos in positions:
        try:
            ticker = pos["ticker"]
            direction = pos["direction"]
            entry = pos["entry_price"]
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            df = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 10:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            c = df["Close"].squeeze()
            h = df["High"].squeeze()
            l = df["Low"].squeeze()
            current_price = float(c.iloc[-1])
            r = float(rsi(c).iloc[-1])
            mk, ms, mh = macd(c)
            mk_val, ms_val = float(mk.iloc[-1]), float(ms.iloc[-1])
            mh_val, mh_prev = float(mh.iloc[-1]), float(mh.iloc[-2])
            sk, sd = stochastic(h, l, c)
            sk_val, sd_val = float(sk.iloc[-1]), float(sd.iloc[-1])

            if direction == "BUY":
                pnl_pct = (current_price - entry) / entry * 100
                sl_dist = (current_price - sl) / entry * 100
                tp_dist = (tp - current_price) / entry * 100
            else:
                pnl_pct = (entry - current_price) / entry * 100
                sl_dist = (sl - current_price) / entry * 100
                tp_dist = (current_price - tp) / entry * 100

            exit_reasons = []
            urgency = "normal"
            if tp_dist <= 0: exit_reasons.append("✅ Take Profit erreicht!"); urgency = "urgent"
            elif sl_dist <= 0: exit_reasons.append("🛑 Stop Loss durchbrochen!"); urgency = "urgent"
            elif sl_dist < 20: exit_reasons.append(f"⚠️ Nahe Stop Loss ({sl_dist:.1f}%)"); urgency = "warn"

            if direction == "BUY":
                if r > 70: exit_reasons.append(f"RSI überkauft ({r:.1f})")
                if mk_val < ms_val and mh_val < mh_prev: exit_reasons.append("MACD dreht negativ")
                if sk_val > 80 and sk_val < sd_val: exit_reasons.append("Stochastik dreht runter")
            else:
                if r < 30: exit_reasons.append(f"RSI überverkauft ({r:.1f})")
                if mk_val > ms_val and mh_val > mh_prev: exit_reasons.append("MACD dreht positiv")
                if sk_val < 20 and sk_val > sd_val: exit_reasons.append("Stochastik dreht hoch")

            if exit_reasons:
                signals.append({"trade_id": pos["id"], "ticker": ticker, "name": pos["name"],
                    "direction": direction, "entry_price": entry, "current_price": round(current_price, 2),
                    "pnl_pct": round(pnl_pct, 2), "stop_loss": sl, "take_profit": tp,
                    "exit_reasons": exit_reasons, "urgency": urgency,
                    "recommendation": "SCHLIESSEN" if urgency == "urgent" else "PRÜFEN"})
        except:
            continue
    signals.sort(key=lambda x: {"urgent":0,"warn":1,"normal":2}.get(x["urgency"],2))
    return {"exit_signals": signals, "checked": len(positions)}

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>TradeBot Pro</h1>"

@app.get("/manifest.json")
def manifest():
    mf_path = Path(__file__).parent / "manifest.json"
    if mf_path.exists():
        return JSONResponse(json.loads(mf_path.read_text()))
    return JSONResponse({})

# Analyse beim Start
Thread(target=run_analysis_background, args=(60,), daemon=True).start()
