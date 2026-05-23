"""
TradeBot Pro v2 - Einstellbare Signalstärke + Investitionsbetrag
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

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

INDICES = {"DAX": "^GDAXI", "Euro Stoxx 50": "^STOXX50E", "FTSE 100": "^FTSE", "CAC 40": "^FCHI", "IBEX 35": "^IBEX", "AEX": "^AEX", "SMI": "^SSMI"}
STOCKS = ["SAP.DE","SIE.DE","ALV.DE","MUV2.DE","DTE.DE","BAYN.DE","BMW.DE","MBG.DE","ASML.AS","MC.PA","TTE.PA","SAN.MC","NESN.SW","ROG.SW","NOVN.SW","AZN.L","HSBA.L","BP.L","SHEL.L","GSK.L","AIR.PA","BNP.PA","OR.PA"]

PORTFOLIO_FILE = "/tmp/portfolio.json"
SETTINGS_FILE = "/tmp/settings.json"

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
    upper = sma + 2 * std
    lower = sma - 2 * std
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return upper, sma, lower, pct_b

def stochastic(high, low, close, k=14, d=3):
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    k_val = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return k_val, k_val.rolling(d).mean()

def atr(high, low, close, period=14):
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def score_ticker(ticker, name, min_strength=60):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 30:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()

        r = rsi(c).iloc[-1]
        mk, ms, mh = macd(c)
        pb = bollinger(c)[3].iloc[-1]
        sk, sd = stochastic(h, l, c)
        sk_val, sd_val = sk.iloc[-1], sd.iloc[-1]
        e20 = c.ewm(span=20).mean().iloc[-1]
        e50 = c.ewm(span=50).mean().iloc[-1]
        atr_val = atr(h, l, c).iloc[-1]
        price = float(c.iloc[-1])
        mk_val, ms_val, mh_val, mh_prev = float(mk.iloc[-1]), float(ms.iloc[-1]), float(mh.iloc[-1]), float(mh.iloc[-2])

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
        sl = round(price - 1.5 * atr_val, 2) if direction == "BUY" else round(price + 1.5 * atr_val, 2)
        tp = round(price + 3 * atr_val, 2) if direction == "BUY" else round(price - 3 * atr_val, 2)

        return {"ticker": ticker, "name": name, "price": round(price, 2), "direction": direction,
                "score": int(score), "strength": min(100, abs(int(score))), "signals": signals,
                "stop_loss": sl, "take_profit": tp, "rsi": round(float(r), 1),
                "timestamp": datetime.now().isoformat()}
    except:
        return None

_cache = {}

@app.get("/api/signals")
async def get_signals():
    settings = load_settings()
    min_str = settings.get("min_strength", 60)
    cache_key = f"signals_{min_str}"
    if _cache.get(cache_key) and (datetime.now() - datetime.fromisoformat(_cache["time"])).seconds < 3600:
        return _cache[cache_key]
    results = []
    all_tickers = list(INDICES.items()) + [(t, t) for t in STOCKS]
    for name, ticker in all_tickers:
        sig = score_ticker(ticker, name, min_str)
        if sig:
            results.append(sig)
    results.sort(key=lambda x: x["strength"], reverse=True)
    data = {"timestamp": datetime.now().isoformat(), "total_analyzed": len(all_tickers),
            "signals_found": len(results), "top_signals": results[:5], "min_strength": min_str}
    _cache[cache_key] = data
    _cache["time"] = datetime.now().isoformat()
    return data

@app.post("/api/signals/refresh")
async def refresh_signals():
    _cache.clear()
    return await get_signals()

@app.get("/api/settings")
def get_settings():
    return load_settings()

class SettingsRequest(BaseModel):
    min_strength: int

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    if not 20 <= req.min_strength <= 100:
        raise HTTPException(400, "Stärke muss zwischen 20 und 100 liegen")
    s = load_settings()
    s["min_strength"] = req.min_strength
    save_settings(s)
    _cache.clear()
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
             "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0}
    return {"portfolio": p, "stats": stats}

class TradeRequest(BaseModel):
    ticker: str; name: str; direction: str; price: float
    stop_loss: float; take_profit: float; score: int
    signals: list; leverage: int = 1
    invest_amount: float = 0  # 0 = auto (5% of portfolio)

@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p = load_portfolio()
    distance = abs(req.price - req.stop_loss)
    if distance == 0:
        raise HTTPException(400, "Stop loss identisch mit Preis")

    # Use custom amount or auto 5%
    if req.invest_amount > 0:
        cost = round(min(req.invest_amount, p["cash"]), 2)
        units = round(cost / req.price, 4)
    else:
        risk = p["cash"] * 0.05
        units = round(risk / distance, 4)
        cost = round(req.price * units, 2)

    if cost > p["cash"]:
        raise HTTPException(400, f"Nicht genug Cash ({p['cash']:.2f}€)")
    if cost <= 0:
        raise HTTPException(400, "Investitionsbetrag muss größer als 0 sein")

    trade_id = f"T{len(p['closed_trades']) + len(p['positions']) + 1:04d}"
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
              "pnl_pct": round(pnl / pos["cost"] * 100, 2), "proceeds": proceeds,
              "closed": datetime.now().isoformat(), "status": "WIN" if pnl > 0 else "LOSS"}
    p["positions"] = [x for x in p["positions"] if x["id"] != req.trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"] + proceeds, 2)
    save_portfolio(p)
    return {"success": True, "trade": closed}

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>TradeBot Pro - index.html fehlt</h1>"

@app.get("/manifest.json")
def manifest():
    mf_path = Path(__file__).parent / "manifest.json"
    if mf_path.exists():
        return JSONResponse(json.loads(mf_path.read_text()))
    return JSONResponse({})
