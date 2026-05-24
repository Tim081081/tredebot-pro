"""
TradeBot Pro v5 - Batch Analysis, Non-blocking, Fast
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

# ── Watchlist ─────────────────────────────────────────────────────────────────
ALL_TICKERS = {
    # Indizes
    "DAX": "^GDAXI", "Euro Stoxx 50": "^STOXX50E", "FTSE 100": "^FTSE",
    "CAC 40": "^FCHI", "IBEX 35": "^IBEX", "AEX": "^AEX", "SMI": "^SSMI",
    # DAX Werte
    "Adidas": "ADS.DE", "Airbus": "AIR.DE", "Allianz": "ALV.DE",
    "BASF": "BAS.DE", "Bayer": "BAYN.DE", "Beiersdorf": "BEI.DE",
    "BMW": "BMW.DE", "Brenntag": "BNR.DE", "Continental": "CON.DE",
    "Covestro": "1COV.DE", "Deutsche Post": "DHL.DE", "Telekom": "DTE.DE",
    "EON": "EOAN.DE", "Fresenius Med": "FME.DE", "Fresenius": "FRE.DE",
    "Heidelberg Mat": "HEI.DE", "Henkel": "HEN3.DE", "Infineon": "IFX.DE",
    "Linde": "LIN.DE", "Mercedes": "MBG.DE", "Merck": "MRK.DE",
    "MTU Aero": "MTX.DE", "Munich Re": "MUV2.DE", "Porsche AG": "P911.DE",
    "Qiagen": "QIA.DE", "Rheinmetall": "RHM.DE", "RWE": "RWE.DE",
    "SAP": "SAP.DE", "Siemens Healthin": "SHL.DE", "Siemens": "SIE.DE",
    "Symrise": "SY1.DE", "VW": "VOW3.DE", "Vonovia": "VNA.DE", "Zalando": "ZAL.DE",
    # Euro Stoxx weitere
    "ASML": "ASML.AS", "ING": "INGA.AS", "Philips": "PHIA.AS",
    "Ahold": "AD.AS", "Wolters Kluwer": "WKL.AS",
    "LVMH": "MC.PA", "LOreal": "OR.PA", "TotalEnergies": "TTE.PA",
    "Sanofi": "SAN.PA", "BNP Paribas": "BNP.PA", "AXA": "CS.PA",
    "Kering": "KER.PA", "Pernod Ricard": "RI.PA", "Dassault": "DSY.PA",
    "Santander": "SAN.MC", "BBVA": "BBVA.MC", "Inditex": "ITX.MC",
    "Repsol": "REP.MC", "Nestle": "NESN.SW", "Roche": "ROG.SW",
    "Novartis": "NOVN.SW", "ABB": "ABBN.SW",
    "AstraZeneca": "AZN.L", "HSBC": "HSBA.L", "BP": "BP.L",
    "Shell": "SHEL.L", "GSK": "GSK.L", "Unilever": "ULVR.L",
    "Enel": "ENEL.MI", "ENI": "ENI.MI", "UniCredit": "UCG.MI", "STMicro": "STM.MI",
}

PORTFOLIO_FILE = "/tmp/portfolio.json"
SETTINGS_FILE = "/tmp/settings.json"

# ── Global State mit Lock ─────────────────────────────────────────────────────
_lock = Lock()
_state = {
    "status": "idle",
    "progress": 0,
    "total": len(ALL_TICKERS),
    "results": [],
    "timestamp": None,
    "min_strength": 60
}

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
    return {"cash": 10000.0, "start_capital": 10000.0, "positions": [],
            "closed_trades": [], "created": datetime.now().isoformat()}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f)

# ── Indikatoren ───────────────────────────────────────────────────────────────
def calc_score(ticker, name, min_strength):
    try:
        df = yf.download(ticker, period="3mo", interval="1d",
                        progress=False, auto_adjust=True, timeout=10)
        if df is None or df.empty or len(df) < 30:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        r = float((100 - 100/(1 + gain/loss.replace(0,np.nan))).iloc[-1])

        # MACD
        e12 = c.ewm(span=12,adjust=False).mean()
        e26 = c.ewm(span=26,adjust=False).mean()
        m = e12-e26; s = m.ewm(span=9,adjust=False).mean(); hist = m-s
        mk,ms,mh,mhp = float(m.iloc[-1]),float(s.iloc[-1]),float(hist.iloc[-1]),float(hist.iloc[-2])

        # Bollinger
        sma = c.rolling(20).mean(); std = c.rolling(20).std()
        pb = float(((c-(sma-2*std))/(4*std)).iloc[-1])

        # Stochastic
        ll=l.rolling(14).min(); hh=h.rolling(14).max()
        sk_s = 100*(c-ll)/(hh-ll).replace(0,np.nan)
        sk,sd = float(sk_s.iloc[-1]),float(sk_s.rolling(3).mean().iloc[-1])

        # EMA trend
        e20,e50 = float(c.ewm(span=20).mean().iloc[-1]),float(c.ewm(span=50).mean().iloc[-1])
        price = float(c.iloc[-1])

        # ATR
        tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        score = 0; signals = []
        if r<30: score+=20; signals.append(f"RSI überverkauft ({r:.0f})")
        elif r<40: score+=10; signals.append(f"RSI schwach ({r:.0f})")
        elif r>70: score-=20; signals.append(f"RSI überkauft ({r:.0f})")
        elif r>60: score-=10; signals.append(f"RSI stark ({r:.0f})")
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

        if abs(score) < min_strength:
            return None

        d = "BUY" if score>0 else "SELL"
        sl = round(price-1.5*atr,2) if d=="BUY" else round(price+1.5*atr,2)
        tp = round(price+3*atr,2) if d=="BUY" else round(price-3*atr,2)
        return {"ticker":ticker,"name":name,"price":round(price,2),"direction":d,
                "score":int(score),"strength":min(100,abs(int(score))),"signals":signals,
                "stop_loss":sl,"take_profit":tp,"rsi":round(r,1),
                "timestamp":datetime.now().isoformat()}
    except:
        return None

def run_analysis(min_strength):
    global _state
    with _lock:
        if _state["status"] == "running":
            return
        _state["status"] = "running"
        _state["progress"] = 0
        _state["results"] = []

    items = list(ALL_TICKERS.items())
    total = len(items)
    results = []

    for i, (name, ticker) in enumerate(items):
        sig = calc_score(ticker, name, min_strength)
        if sig:
            results.append(sig)
        results_sorted = sorted(results, key=lambda x: x["strength"], reverse=True)
        with _lock:
            _state["progress"] = round((i+1)/total*100)
            _state["results"] = results_sorted[:10]

    with _lock:
        _state["status"] = "done"
        _state["progress"] = 100
        _state["results"] = results_sorted[:10] if results else []
        _state["all_results"] = results_sorted
        _state["signals_found"] = len(results)
        _state["total_analyzed"] = total
        _state["timestamp"] = datetime.now().isoformat()
        _state["min_strength"] = min_strength

# ── API ───────────────────────────────────────────────────────────────────────
@app.get("/api/signals")
def get_signals():
    s = load_settings()
    min_str = s.get("min_strength", 60)
    with _lock:
        status = _state["status"]
        progress = _state["progress"]
        results = _state.get("results", [])
        ts = _state.get("timestamp")
        found = _state.get("signals_found", len(results))
        analyzed = _state.get("total_analyzed", 0)

    if status == "idle":
        Thread(target=run_analysis, args=(min_str,), daemon=True).start()
        return {"status":"loading","progress":0,"top_signals":[],
                "total_analyzed":0,"signals_found":0,"message":"Analyse wird gestartet…"}

    return {"status":status,"progress":progress,"top_signals":results,
            "total_analyzed":analyzed,"signals_found":found,
            "timestamp":ts,"min_strength":min_str}

@app.post("/api/signals/refresh")
def refresh_signals():
    global _state
    s = load_settings()
    min_str = s.get("min_strength", 60)
    with _lock:
        if _state["status"] == "running":
            return {"status":"running","message":"Analyse läuft bereits"}
        _state = {"status":"idle","progress":0,"results":[],
                  "total":len(ALL_TICKERS),"timestamp":None,"min_strength":min_str}
    Thread(target=run_analysis, args=(min_str,), daemon=True).start()
    return {"status":"loading","message":"Neue Analyse gestartet"}

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
    global _state
    with _lock:
        _state["status"] = "idle"
        _state["results"] = []
        _state["progress"] = 0
    return s

@app.get("/api/portfolio")
def get_portfolio():
    p = load_portfolio()
    closed = p["closed_trades"]
    open_val = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total = round(p["cash"] + open_val, 2)
    pnl = round(total - p["start_capital"], 2)
    wins = [t for t in closed if t.get("status") == "WIN"]
    stats = {"start_capital":p["start_capital"],"total_value":total,"cash":p["cash"],
             "open_value":round(open_val,2),"total_pnl":pnl,
             "total_pnl_pct":round(pnl/p["start_capital"]*100,2),
             "total_trades":len(closed),"open_positions":len(p["positions"]),
             "win_rate":round(len(wins)/len(closed)*100,1) if closed else 0}
    return {"portfolio":p,"stats":stats}

class TradeRequest(BaseModel):
    ticker:str; name:str; direction:str; price:float
    stop_loss:float; take_profit:float; score:int
    signals:list; leverage:int=1; invest_amount:float=0

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
        units = round((p["cash"]*0.05)/distance, 4)
        cost = round(req.price*units, 2)
    if cost > p["cash"]:
        raise HTTPException(400, f"Nicht genug Cash ({p['cash']:.2f}€)")
    trade_id = f"T{len(p['closed_trades'])+len(p['positions'])+1:04d}"
    pos = {"id":trade_id,"ticker":req.ticker,"name":req.name,"direction":req.direction,
           "entry_price":req.price,"current_price":req.price,"units":units,"cost":cost,
           "stop_loss":req.stop_loss,"take_profit":req.take_profit,"score":req.score,
           "signals":req.signals,"unrealized_pnl":0.0,"unrealized_pnl_pct":0.0,
           "current_value":cost,"opened":datetime.now().isoformat()}
    p["cash"] = round(p["cash"]-cost, 2)
    p["positions"].append(pos)
    save_portfolio(p)
    return {"success":True,"trade":pos}

class CloseRequest(BaseModel):
    trade_id:str; close_price:float

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p = load_portfolio()
    pos = next((x for x in p["positions"] if x["id"]==req.trade_id), None)
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    pnl = (req.close_price-pos["entry_price"])*pos["units"] if pos["direction"]=="BUY" else (pos["entry_price"]-req.close_price)*pos["units"]
    proceeds = round(pos["cost"]+pnl, 2)
    closed = {**pos,"close_price":req.close_price,"pnl":round(pnl,2),
              "pnl_pct":round(pnl/pos["cost"]*100,2),"proceeds":proceeds,
              "closed":datetime.now().isoformat(),"status":"WIN" if pnl>0 else "LOSS"}
    p["positions"] = [x for x in p["positions"] if x["id"]!=req.trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"]+proceeds, 2)
    save_portfolio(p)
    return {"success":True,"trade":closed}

@app.get("/api/exit-signals")
def get_exit_signals():
    p = load_portfolio()
    positions = p.get("positions", [])
    if not positions:
        return {"exit_signals":[],"checked":0}
    signals = []
    for pos in positions:
        try:
            ticker = pos["ticker"]
            df = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True, timeout=8)
            if df is None or df.empty or len(df)<10:
                continue
            df.columns = [c[0] if isinstance(c,tuple) else c for c in df.columns]
            c = df["Close"].squeeze()
            h = df["High"].squeeze()
            l = df["Low"].squeeze()
            price = float(c.iloc[-1])
            delta = c.diff()
            r = float((100-100/(1+(delta.clip(lower=0).rolling(14).mean()/(-delta.clip(upper=0)).rolling(14).mean().replace(0,np.nan)))).iloc[-1])
            e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
            m=e12-e26; s=m.ewm(span=9,adjust=False).mean(); hist=m-s
            mk,ms,mh,mhp = float(m.iloc[-1]),float(s.iloc[-1]),float(hist.iloc[-1]),float(hist.iloc[-2])
            ll=l.rolling(14).min(); hh=h.rolling(14).max()
            sk_s=100*(c-ll)/(hh-ll).replace(0,np.nan)
            sk,sd = float(sk_s.iloc[-1]),float(sk_s.rolling(3).mean().iloc[-1])

            entry=pos["entry_price"]; sl=pos["stop_loss"]; tp=pos["take_profit"]
            direction=pos["direction"]
            if direction=="BUY":
                pnl_pct=(price-entry)/entry*100
                sl_dist=(price-sl)/entry*100
                tp_dist=(tp-price)/entry*100
            else:
                pnl_pct=(entry-price)/entry*100
                sl_dist=(sl-price)/entry*100
                tp_dist=(price-tp)/entry*100

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
        except:
            continue
    signals.sort(key=lambda x:{"urgent":0,"warn":1,"normal":2}.get(x["urgency"],2))
    return {"exit_signals":signals,"checked":len(positions)}

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
Thread(target=run_analysis, args=(60,), daemon=True).start()
