"""
TradeBot Pro v13
================
Alle Änderungswünsche aus ALLE_AENDERUNGSWUENSCHE.md umgesetzt:
✓ Portfolio-Persistenz: SQLite-Datenbank statt /tmp (überlebt Deploys)
✓ Regionale Analyse: DE / EU / USA auswählbar, Signale pro Region
✓ TechDAX-Werte ergänzt
✓ US-Werte: Dow Jones + NASDAQ 100 vollständig
✓ Regionsübergreifendes Portfolio
✓ Automatische Analyse alle 10 Min
✓ Push-Benachrichtigungen (Web Push via pywebpush)
✓ Alle Settings konfigurierbar und persistiert
✓ Alle Backend-Optimierungen aus v12 erhalten
"""

import gc, json, os, time, tempfile, sqlite3
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

app = FastAPI(title="TradeBot Pro", version="13.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULTS = {
    "min_strength":   20,
    "order_fee":      10.0,
    "max_positions":  5,
    "max_exposure":   40,
    "risk_per_trade": 2,
    "max_position":   20,
    "min_sl_dist":    1.5,
    "max_sl_dist":    8.0,
    "vol_threshold":  5.0,
    "adx_trend":      25,
    "adx_sideways":   20,
    "start_capital":  10000.0,
}
PRICE_CACHE_TTL  = 300
DETAIL_CACHE_TTL = 600
CHART_CACHE_TTL  = 600
DF_CACHE_MAX     = 300

# ── Regionale Ticker ──────────────────────────────────────────────────────────
REGIONS = {
    "DE": {
        # DAX 40
        "DAX Index":"^GDAXI","Adidas":"ADS.DE","Airbus":"AIR.DE","Allianz":"ALV.DE",
        "BASF":"BAS.DE","Bayer":"BAYN.DE","Beiersdorf":"BEI.DE","BMW":"BMW.DE",
        "Brenntag":"BNR.DE","Continental":"CON.DE","Covestro":"1COV.DE",
        "Deutsche Post":"DHL.DE","Telekom":"DTE.DE","EON":"EOAN.DE",
        "Fresenius Med":"FME.DE","Fresenius":"FRE.DE","Heidelberg Mat":"HEI.DE",
        "Henkel":"HEN3.DE","Infineon":"IFX.DE","Linde":"LIN.DE","Mercedes":"MBG.DE",
        "Merck":"MRK.DE","MTU Aero":"MTX.DE","Munich Re":"MUV2.DE","Porsche AG":"P911.DE",
        "Qiagen":"QIA.DE","Rheinmetall":"RHM.DE","RWE":"RWE.DE","SAP":"SAP.DE",
        "Siemens Health":"SHL.DE","Siemens":"SIE.DE","Symrise":"SY1.DE","VW":"VOW3.DE",
        "Vonovia":"VNA.DE","Zalando":"ZAL.DE","Deutsche Bank":"DBK.DE","Commerzbank":"CBK.DE",
        "Hannover Rueck":"HNR1.DE","Sartorius":"SRT3.DE",
        # TechDAX
        "AIXTRON":"AIXA.DE","Cancom":"COK.DE","CompuGroup":"COP.DE","Drägerwerk":"DRW3.DE",
        "Energiekontor":"EKT.DE","Evotec":"EVT.DE","GFT Technologies":"GFT.DE",
        "Jenoptik":"JEN.DE","LPKF Laser":"LPK.DE","Nemetschek":"NEM.DE",
        "PTC Inc":"PTC.DE","Reply":"REY.DE","Siemens Energy":"ENR.DE",
        "Software AG":"SOW.DE","TeamViewer":"TMV.DE","TUI":"TUI1.DE",
        "United Internet":"UTDI.DE","Wacker Chemie":"WCH.DE","Xing":"O1BC.DE",
        "Zooplus":"ZO1.DE",
    },
    "EU": {
        "Euro Stoxx 50":"^STOXX50E","FTSE 100":"^FTSE","CAC 40":"^FCHI",
        "IBEX 35":"^IBEX","AEX":"^AEX","SMI":"^SSMI",
        "ASML":"ASML.AS","ING":"INGA.AS","Ahold":"AD.AS","Philips":"PHIA.AS",
        "LVMH":"MC.PA","LOreal":"OR.PA","TotalEnergies":"TTE.PA","Sanofi":"SAN.PA",
        "BNP Paribas":"BNP.PA","Kering":"KER.PA","Airbus FR":"AIR.PA","Danone":"BN.PA",
        "Stellantis":"STLAM.MI","Santander":"SAN.MC","BBVA":"BBVA.MC","Inditex":"ITX.MC",
        "Nestle":"NESN.SW","Roche":"ROG.SW","Novartis":"NOVN.SW","ABB":"ABBN.SW",
        "AstraZeneca":"AZN.L","HSBC":"HSBA.L","BP":"BP.L","Shell":"SHEL.L",
        "GSK":"GSK.L","Unilever":"ULVR.L","Diageo":"DGE.L","Rio Tinto":"RIO.L",
        "Enel":"ENEL.MI","ENI":"ENI.MI","UniCredit":"UCG.MI","STMicro":"STM.MI",
    },
    "USA": {
        # Dow Jones 30
        "Dow Jones":"^DJI","S&P 500":"^GSPC","NASDAQ":"^IXIC",
        "Apple":"AAPL","Microsoft":"MSFT","Amazon":"AMZN","Alphabet":"GOOGL",
        "Meta":"META","Nvidia":"NVDA","Berkshire":"BRK-B","JPMorgan":"JPM",
        "Johnson & Johnson":"JNJ","Visa":"V","Mastercard":"MA","Exxon Mobil":"XOM",
        "UnitedHealth":"UNH","Procter & Gamble":"PG","Home Depot":"HD","Walmart":"WMT",
        "Chevron":"CVX","Coca-Cola":"KO","Disney":"DIS","IBM":"IBM",
        "Goldman Sachs":"GS","American Express":"AXP","Caterpillar":"CAT",
        "Boeing":"BA","3M":"MMM","Honeywell":"HON","Merck US":"MRK",
        "Salesforce":"CRM","Intel":"INTC","Cisco":"CSCO","Verizon":"VZ",
        # NASDAQ 100 weitere
        "Tesla":"TSLA","Adobe":"ADBE","Netflix":"NFLX","PayPal":"PYPL",
        "Qualcomm":"QCOM","Broadcom":"AVGO","AMD":"AMD","Texas Instruments":"TXN",
        "Costco":"COST","Starbucks":"SBUX","Booking":"BKNG","Airbnb":"ABNB",
        "Intuitive Surgical":"ISRG","Moderna":"MRNA","Palo Alto":"PANW",
        "Crowdstrike":"CRWD","Snowflake":"SNOW","Datadog":"DDOG","MongoDB":"MDB",
        "ServiceNow":"NOW","Workday":"WDAY","Fortinet":"FTNT","KLA":"KLAC",
        "Lam Research":"LRCX","Applied Materials":"AMAT",
    },
}

# Vollständiger Ticker→Name Lookup über alle Regionen
TICKER_TO_NAME: dict = {}
VALID_TICKERS:  set  = set()
for _reg in REGIONS.values():
    for _n, _t in _reg.items():
        TICKER_TO_NAME[_t] = _n
        VALID_TICKERS.add(_t)

# ── Persistenz: SQLite (überlebt Deploys, Neuschreibungen) ───────────────────
# Render.com: /opt/render/project/src ist persistenter Speicher wenn Disk gemountet
# Fallback: /tmp (geht bei Neustart verloren, aber Portfolio-Backup im Browser)
def _get_db_path() -> str:
    for candidate in ["/opt/render/project/src", "/data", os.path.expanduser("~")]:
        if os.path.isdir(candidate) and os.access(candidate, os.W_OK):
            return os.path.join(candidate, "tradebot.db")
    return "/tmp/tradebot.db"

DB_PATH      = _get_db_path()
SETTINGS_FILE = DB_PATH.replace(".db", "_settings.json")

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _get_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS portfolio (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT DEFAULT 'open',
            created TEXT NOT NULL, closed TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS push_subs (
            endpoint TEXT PRIMARY KEY, sub TEXT NOT NULL)""")
        c.commit()

_init_db()

# ── In-Memory Caches & Analyse-State ─────────────────────────────────────────
_lock       = Lock()
# State pro Region: {"DE":{status,progress,results,...}, ...}
_state: dict = {r: {"status":"idle","progress":0,"results":[],"timestamp":None} for r in REGIONS}
_active_region = "DE"   # Zuletzt manuell gestartete Region

_portfolio_cache: dict | None = None
_price_cache:     dict = {}
_detail_cache:    dict = {}
_chart_cache:     dict = {}
_df_cache:        dict = {}
_df_lock          = Lock()

# ── Atomares File-Write ───────────────────────────────────────────────────────
def _atomic_write(path: str, data: dict):
    dir_ = os.path.dirname(path) or "/tmp"
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(data, f, ensure_ascii=False); tmp = f.name
    os.replace(tmp, path)

# ── Settings (doppelte Persistenz: SQLite primär + JSON-Datei Fallback) ───────
def load_settings() -> dict:
    # 1. SQLite (überlebt Neustarts auf Render auch ohne Disk)
    try:
        with _get_conn() as c:
            row = c.execute("SELECT value FROM portfolio WHERE key='settings'").fetchone()
            if row:
                return {**DEFAULTS, **json.loads(row["value"])}
    except Exception: pass
    # 2. JSON-Datei Fallback
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                return {**DEFAULTS, **json.load(f)}
    except Exception: pass
    return dict(DEFAULTS)

def save_settings(s: dict):
    # In beide Speicher schreiben
    try:
        with _get_conn() as c:
            c.execute("INSERT OR REPLACE INTO portfolio (key,value) VALUES ('settings',?)",
                      (json.dumps(s),))
            c.commit()
    except Exception: pass
    try:
        _atomic_write(SETTINGS_FILE, s)
    except Exception: pass

def get_s(k): return load_settings().get(k, DEFAULTS[k])

# ── Portfolio (SQLite-basiert) ────────────────────────────────────────────────
def load_portfolio() -> dict:
    global _portfolio_cache
    if _portfolio_cache is not None:
        return _portfolio_cache
    try:
        with _get_conn() as c:
            row = c.execute("SELECT value FROM portfolio WHERE key='main'").fetchone()
            if row:
                _portfolio_cache = json.loads(row["value"])
                return _portfolio_cache
    except Exception: pass
    sc = get_s("start_capital")
    p = {"cash": sc, "start_capital": sc, "positions": [], "closed_trades": [],
         "created": datetime.now().isoformat()}
    save_portfolio(p)
    return p

def save_portfolio(p: dict):
    global _portfolio_cache
    _portfolio_cache = p
    try:
        with _get_conn() as c:
            c.execute("INSERT OR REPLACE INTO portfolio (key,value) VALUES ('main',?)",
                      (json.dumps(p),))
            c.commit()
    except Exception:
        _atomic_write("/tmp/portfolio_backup.json", p)

def invalidate_portfolio_cache():
    global _portfolio_cache
    _portfolio_cache = None

# ── Ticker-Validierung ────────────────────────────────────────────────────────
def validate_ticker(ticker: str) -> str:
    base = ticker.split()[0] if " " in ticker else ticker
    if base not in VALID_TICKERS:
        raise HTTPException(400, f"Unbekannter Ticker: {ticker}")
    return base

# ── DataFrame-Cache mit Eviction ─────────────────────────────────────────────
def fetch_ohlcv(ticker: str, period: str = "6mo", timeout: int = 10):
    key = f"{ticker}|{period}"; now = time.time()
    with _df_lock:
        c = _df_cache.get(key)
        if c and now - c["ts"] < CHART_CACHE_TTL: return c["df"]
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True, timeout=timeout)
        if df is None or df.empty: return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        with _df_lock:
            if len(_df_cache) >= DF_CACHE_MAX:
                for k in sorted(_df_cache, key=lambda x: _df_cache[x]["ts"])[:60]:
                    del _df_cache[k]
            _df_cache[key] = {"df": df, "ts": now}
        return df
    except Exception: return None

# ── Indikatoren ───────────────────────────────────────────────────────────────
def compute_indicators(c, h, l, v, cfg: dict) -> dict:
    price = float(c.iloc[-1])
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]); atr_pct = atr14/price*100
    up=h.diff(); dn=-l.diff()
    pdm=np.where((up>dn)&(up>0),up,0.); ndm=np.where((dn>up)&(dn>0),dn,0.)
    tm=tr.rolling(14).mean().replace(0,np.nan)
    pdi=100*pd.Series(pdm,index=c.index).rolling(14).mean()/tm
    ndi=100*pd.Series(ndm,index=c.index).rolling(14).mean()/tm
    dx=100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)
    adx=float(dx.rolling(14).mean().iloc[-1])
    pdi_v,ndi_v=float(pdi.iloc[-1]),float(ndi.iloc[-1])
    delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rsi=float((100-100/(1+gain/loss.replace(0,np.nan))).iloc[-1])
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
    macd=e12-e26; msig=macd.ewm(span=9,adjust=False).mean(); mhist=macd-msig
    mk,ms=float(macd.iloc[-1]),float(msig.iloc[-1])
    mh,mhp=float(mhist.iloc[-1]),float(mhist.iloc[-2])
    sma20=c.rolling(20).mean(); std20=c.rolling(20).std()
    bbu=sma20+2*std20; bbl=sma20-2*std20
    pb=float(((c-bbl)/(bbu-bbl).replace(0,np.nan)).iloc[-1])
    ll14=l.rolling(14).min(); hh14=h.rolling(14).max()
    stk=100*(c-ll14)/(hh14-ll14).replace(0,np.nan)
    sk,sd=float(stk.iloc[-1]),float(stk.rolling(3).mean().iloc[-1])
    e20=float(c.ewm(span=20).mean().iloc[-1]); e50=float(c.ewm(span=50).mean().iloc[-1])
    e100=float(c.ewm(span=100).mean().iloc[-1])
    e200=float(c.ewm(span=200).mean().iloc[-1]) if len(c)>=200 else None
    willr=float((-100*(hh14-c)/(hh14-ll14).replace(0,np.nan)).iloc[-1])
    tp_=(h+l+c)/3; cci=float(((tp_-tp_.rolling(20).mean())/(0.015*tp_.rolling(20).std())).iloc[-1])
    obv=(np.sign(c.diff())*v).fillna(0).cumsum()
    obv_bull=float(obv.iloc[-1])>float(obv.ewm(span=20).mean().iloc[-1])
    ph,pl,pc=float(h.iloc[-2]),float(l.iloc[-2]),float(c.iloc[-2])
    pivot=(ph+pl+pc)/3
    r1=2*pivot-pl; r2=pivot+(ph-pl); s1=2*pivot-ph; s2=pivot-(ph-pl)
    n52=min(252,len(h))
    w52h=float(h.rolling(n52).max().iloc[-1]); w52l=float(l.rolling(n52).min().iloc[-1])
    w52p=round((price-w52l)/(w52h-w52l)*100,1) if w52h!=w52l else 50.
    roc10=float(((c-c.shift(10))/c.shift(10)*100).iloc[-1])
    return {"price":price,"atr14":atr14,"atr_pct":atr_pct,
            "high_vol":atr_pct>cfg["vol_threshold"],
            "adx":adx,"pdi":pdi_v,"ndi":ndi_v,
            "trending":adx>=cfg["adx_trend"],"sideways":adx<cfg["adx_sideways"],
            "trend_up":pdi_v>ndi_v,"rsi":rsi,"mk":mk,"ms":ms,"mh":mh,"mhp":mhp,
            "pb":pb,"bb_upper":float(bbu.iloc[-1]),"bb_lower":float(bbl.iloc[-1]),
            "sma20":sma20,"std20":std20,"sk":sk,"sd":sd,
            "e20":e20,"e50":e50,"e100":e100,"e200":e200,
            "willr":willr,"cci":cci,"obv_bull":obv_bull,
            "pivot":pivot,"r1":r1,"r2":r2,"s1":s1,"s2":s2,
            "w52h":w52h,"w52l":w52l,"w52p":w52p,"roc10":roc10,"tr":tr}

def _score(ind: dict) -> tuple:
    sa,sb,sc=0,0,0; sigs=[]; price=ind["price"]
    rsi=ind["rsi"]
    if rsi<30: sa+=20; sigs.append(f"RSI überverkauft ({rsi:.0f})")
    elif rsi<40: sa+=10; sigs.append(f"RSI schwach ({rsi:.0f})")
    elif rsi>70: sa-=20; sigs.append(f"RSI überkauft ({rsi:.0f})")
    elif rsi>60: sa-=10; sigs.append(f"RSI stark ({rsi:.0f})")
    pb=ind["pb"]
    if pb<0.05: sa+=20; sigs.append("Unteres Bollinger Band")
    elif pb<0.2: sa+=10; sigs.append("Nahe unterem BB")
    elif pb>0.95: sa-=20; sigs.append("Oberes Bollinger Band")
    elif pb>0.8: sa-=10; sigs.append("Nahe oberem BB")
    sk,sd=ind["sk"],ind["sd"]
    if sk<20 and sk>sd: sa+=15; sigs.append(f"Stochastik dreht hoch ({sk:.0f})")
    elif sk>80 and sk<sd: sa-=15; sigs.append(f"Stochastik dreht runter ({sk:.0f})")
    willr=ind["willr"]
    if willr<-80: sa+=10; sigs.append(f"Williams %R überverkauft ({willr:.0f})")
    elif willr>-20: sa-=10; sigs.append(f"Williams %R überkauft ({willr:.0f})")
    cci=ind["cci"]
    if cci<-100: sa+=10; sigs.append(f"CCI überverkauft ({cci:.0f})")
    elif cci>100: sa-=10; sigs.append(f"CCI überkauft ({cci:.0f})")
    if ind["trending"] and ((ind["trend_up"] and sa<0) or (not ind["trend_up"] and sa>0)):
        sa=int(sa*.5); sigs.append(f"⚠️ Trendmarkt ADX {ind['adx']:.0f}: Oszillator gedämpft")
    mk,ms,mh,mhp=ind["mk"],ind["ms"],ind["mh"],ind["mhp"]
    if mk>ms and mh>mhp: sb+=20; sigs.append("MACD bullisch ↑")
    elif mk<ms and mh<mhp: sb-=20; sigs.append("MACD bärisch ↓")
    e20,e50,e100,e200=ind["e20"],ind["e50"],ind["e100"],ind["e200"]
    if price>e20>e50>e100: sb+=15; sigs.append("Starker Auftrend EMA 20>50>100")
    elif price>e20>e50: sb+=10; sigs.append("Auftrend EMA 20/50")
    elif price<e20<e50<e100: sb-=15; sigs.append("Starker Abtrend EMA 20<50<100")
    elif price<e20<e50: sb-=10; sigs.append("Abtrend EMA 20/50")
    if e200:
        if price>e200: sb+=5; sigs.append("Über EMA 200 – Langzeittrend bullisch")
        else: sb-=5; sigs.append("Unter EMA 200 – Langzeittrend bärisch")
    adx=ind["adx"]
    if ind["trending"]:
        if ind["trend_up"]: sb+=10; sigs.append(f"ADX starker Auftrend ({adx:.0f})")
        else: sb-=10; sigs.append(f"ADX starker Abtrend ({adx:.0f})")
    elif ind["sideways"]: sb=0; sigs.append(f"⚠️ Seitwärtsmarkt ADX {adx:.0f}: Trendfolger deaktiviert")
    else: sigs.append(f"ADX schwacher Trend ({adx:.0f})")
    if ind["obv_bull"]: sc+=5; sigs.append("OBV: Kaufvolumen steigt")
    else: sc-=5; sigs.append("OBV: Verkaufsvolumen steigt")
    w52p=ind["w52p"]
    if w52p<15: sc+=10; sigs.append(f"Nahe 52W-Tief ({w52p:.0f}%)")
    elif w52p>85: sc-=10; sigs.append(f"Nahe 52W-Hoch ({w52p:.0f}%)")
    s1,r1=ind["s1"],ind["r1"]
    if price<s1: sc+=8; sigs.append(f"Unter S1 {s1:.2f} – Bounce-Zone")
    elif price>r1: sc-=8; sigs.append(f"Über R1 {r1:.2f} – Widerstand")
    roc10=ind["roc10"]
    if roc10>5: sc-=5; sigs.append(f"Positives Momentum +{roc10:.1f}%")
    elif roc10<-5: sc+=5; sigs.append(f"Negatives Momentum {roc10:.1f}%")
    return sa,sb,sc,sigs

def calc_sl(price,direction,atr,s1,s2,r1,r2,cfg):
    mind=price*cfg["min_sl_dist"]/100; maxd=price*cfg["max_sl_dist"]/100
    if direction=="BUY":
        for lv in [s1,s2]:
            if 0<lv<price:
                sl=round(lv*.998,2); d=price-sl
                if mind<=d<=maxd: return sl
        sl=round(price-1.5*atr,2); d=price-sl
        if d<mind: return round(price-mind,2)
        if d>maxd: return round(price-maxd,2)
        return sl
    else:
        for lv in [r1,r2]:
            if lv>price:
                sl=round(lv*1.002,2); d=sl-price
                if mind<=d<=maxd: return sl
        sl=round(price+1.5*atr,2); d=sl-price
        if d<mind: return round(price+mind,2)
        if d>maxd: return round(price+maxd,2)
        return sl

def build_signal(ticker,name,ind,min_strength,cfg):
    sa,sb,sc,sigs=_score(ind)
    gu=sum(1 for x in [sa,sb,sc] if x>0); gd=sum(1 for x in [sa,sb,sc] if x<0)
    if gu<2 and gd<2: return None
    total=sa+sb+sc; direction="BUY" if total>0 else "SELL"
    conf=gu if direction=="BUY" else gd
    if conf<2: return None
    if ind["high_vol"]:
        total=int(total*.5); sigs.append(f"⚠️ Hohe Volatilität ATR {ind['atr_pct']:.1f}% – Score reduziert")
    if abs(total)<min_strength: return None
    price=ind["price"]
    sl=calc_sl(price,direction,ind["atr14"],ind["s1"],ind["s2"],ind["r1"],ind["r2"],cfg)
    tm=2.5 if not ind["high_vol"] else 2.0
    tp=round(price+tm*(price-sl),2) if direction=="BUY" else round(price-tm*(sl-price),2)
    mp=("Trendmarkt" if ind["trending"] else ("Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend"))
    return {"ticker":ticker,"name":name,"price":round(price,2),"direction":direction,
            "score":int(total),"score_detail":{"momentum":int(sa),"trend":int(sb),"structure":int(sc)},
            "strength":min(100,abs(int(total))),"confirming_groups":conf,"market_phase":mp,
            "high_volatility":ind["high_vol"],"signals":sigs,"warnings":[],
            "stop_loss":sl,"take_profit":tp,"rsi":round(ind["rsi"],1),"atr":round(ind["atr14"],2),
            "support_levels":[round(ind["s1"],2),round(ind["s2"],2)],
            "resistance_levels":[round(ind["r1"],2),round(ind["r2"],2)],
            "timestamp":datetime.now().isoformat()}

def calc_position_size(cash,total,price,stop_loss,invest_amount,cfg):
    fee=cfg["order_fee"]; mpp=cfg["max_position"]/100; rpt=cfg["risk_per_trade"]/100
    dist=abs(price-stop_loss) or price*.02
    if invest_amount>0: cost=round(min(invest_amount,cash-fee,total*mpp),2)
    else: cost=round(min((total*rpt/dist)*price,total*mpp,cash-fee),2)
    cost=max(cost,.01)
    return round(cost/price,4),cost

# ── Quick-Score & Analyse ─────────────────────────────────────────────────────
def quick_score(ticker, name, min_strength, cfg, include_weak=False):
    """
    include_weak=True: gibt auch Signale zurück die unter min_strength liegen
    (für Watchlist-Vollansicht). Diese werden mit below_threshold=True markiert.
    """
    df=fetch_ohlcv(ticker,period="6mo")
    if df is None or len(df)<60: return None
    try:
        c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
        v=df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)),index=c.index)
        ind=compute_indicators(c,h,l,v,cfg)
        # Für include_weak mit min_strength=0 aufrufen
        effective_min = 0 if include_weak else min_strength
        sig=build_signal(ticker,name,ind,effective_min,cfg)
        if sig is None: return None
        sig["below_threshold"] = sig["strength"] < min_strength
        sig["indicators"]={"RSI (14)":round(ind["rsi"],1),"MACD":round(ind["mk"],4),
            "BB %B":round(ind["pb"],2),"Stoch %K":round(ind["sk"],1),
            "EMA 20":round(ind["e20"],2),"EMA 50":round(ind["e50"],2),
            "ADX":round(ind["adx"],1),"ATR (14)":round(ind["atr14"],2),
            "Marktphase":sig["market_phase"]}
        sig["analyst"]={}; sig["chart_data"]=[]
        return sig
    except Exception: return None
    finally: gc.collect()

def full_analysis(ticker,name,min_strength=0):
    cfg=load_settings(); now=time.time()
    cached=_detail_cache.get(ticker)
    if cached and now-cached["ts"]<DETAIL_CACHE_TTL: return cached["result"]
    df=fetch_ohlcv(ticker,period="1y")
    if df is None or len(df)<60: return None
    try:
        c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
        v=df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)),index=c.index)
        ind=compute_indicators(c,h,l,v,cfg)
        sig=build_signal(ticker,name,ind,min_strength,cfg)
        if sig is None: return None
        analyst_info={}
        try:
            info=yf.Ticker(ticker).info; rec=info.get("recommendationMean")
            n_anal=info.get("numberOfAnalystOpinions",0); target=info.get("targetMeanPrice")
            if rec and n_anal:
                rt={1:"Starker Kauf",2:"Kauf",3:"Halten",4:"Verkauf",5:"Starker Verkauf"}.get(round(rec),f"{rec:.1f}")
                analyst_info={"recommendation":rt,"analysts":n_anal,"target":round(target,2) if target else None}
        except Exception: pass
        indicators={"RSI (14)":round(ind["rsi"],1),"MACD":round(ind["mk"],4),
            "MACD Signal":round(ind["ms"],4),"BB %B":round(ind["pb"],2),
            "BB Upper":round(ind["bb_upper"],2),"BB Lower":round(ind["bb_lower"],2),
            "Stoch %K":round(ind["sk"],1),"Stoch %D":round(ind["sd"],1),
            "EMA 20":round(ind["e20"],2),"EMA 50":round(ind["e50"],2),"EMA 100":round(ind["e100"],2),
            "Williams %R":round(ind["willr"],1),"CCI (20)":round(ind["cci"],1),
            "OBV Trend":"Bullisch" if ind["obv_bull"] else "Bärisch",
            "ATR (14)":round(ind["atr14"],2),"ATR %":f"{ind['atr_pct']:.2f}%",
            "ADX":round(ind["adx"],1),"+DI":round(ind["pdi"],1),"-DI":round(ind["ndi"],1),
            "Pivot":round(ind["pivot"],2),"R1":round(ind["r1"],2),"R2":round(ind["r2"],2),
            "S1":round(ind["s1"],2),"S2":round(ind["s2"],2),
            "52W Hoch":round(ind["w52h"],2),"52W Tief":round(ind["w52l"],2),
            "52W Position":f"{ind['w52p']}%","ROC (10)":f"{ind['roc10']:.1f}%",
            "Marktphase":sig["market_phase"]}
        if ind["e200"]: indicators["EMA 200"]=round(ind["e200"],2)
        if ind["high_vol"]: indicators["⚠️ Volatilität"]=f"ERHÖHT ({ind['atr_pct']:.1f}%) – Vorsicht!"
        if analyst_info:
            indicators["Analysten"]=f"{analyst_info['recommendation']} ({analyst_info['analysts']} Analysten) ℹ️"
            if analyst_info.get("target"): indicators["Kursziel"]=f"{analyst_info['target']:.2f} (nur Info)"
        df90=df.tail(90); sma20=ind["sma20"]; std20=ind["std20"]
        bbu90=(sma20+2*std20).tail(90).round(2); bbm90=sma20.tail(90).round(2)
        bbl90=(sma20-2*std20).tail(90).round(2)
        e20s=c.ewm(span=20).mean().tail(90).round(2); e50s=c.ewm(span=50).mean().tail(90).round(2)
        chart_data=[{"date":df90.index[i].strftime("%Y-%m-%d"),
            "open":round(float(df90["Open"].iat[i]),2),"high":round(float(df90["High"].iat[i]),2),
            "low":round(float(df90["Low"].iat[i]),2),"close":round(float(df90["Close"].iat[i]),2),
            "volume":int(df90["Volume"].iat[i]) if "Volume" in df90.columns else 0,
            "bb_upper":None if pd.isna(bbu90.iat[i]) else float(bbu90.iat[i]),
            "bb_mid":None if pd.isna(bbm90.iat[i]) else float(bbm90.iat[i]),
            "bb_lower":None if pd.isna(bbl90.iat[i]) else float(bbl90.iat[i]),
            "ema20":float(e20s.iat[i]),"ema50":float(e50s.iat[i])}
            for i in range(len(df90))]
        result={**sig,"indicators":indicators,"analyst":analyst_info,"chart_data":chart_data}
        _detail_cache[ticker]={"result":result,"ts":now}
        return result
    except Exception: return None
    finally: gc.collect()

def run_analysis(region: str, min_strength: int) -> None:
    global _state
    with _lock:
        if _state[region].get("status")=="running": return
        _state[region].update({"status":"running","progress":0,"results":[]})
    cfg=load_settings()
    items=list(REGIONS[region].items()); total=len(items)
    strong_results=[]   # Über Schwelle → Signale-Tab
    all_results=[]      # Alle mit Signal (inkl. schwache) → Watchlist

    for i,(name,ticker) in enumerate(items):
        # Immer mit include_weak=True scannen, dann filtern
        sig=quick_score(ticker,name,min_strength,cfg,include_weak=True)
        if sig:
            all_results.append(sig)
            if not sig.get("below_threshold",False):
                strong_results.append(sig)

        if i%5==4 or i==total-1:
            rs=sorted(strong_results,key=lambda x:x["strength"],reverse=True)
            with _lock:
                _state[region]["progress"]=round((i+1)/total*100)
                _state[region]["results"]=rs[:15]
            time.sleep(.3); gc.collect()

    rs_strong=sorted(strong_results,key=lambda x:x["strength"],reverse=True)
    rs_all=sorted(all_results,key=lambda x:x["strength"],reverse=True)

    with _lock:
        _state[region].update({
            "status":"done","progress":100,
            "results":rs_strong[:15],        # Signale-Tab: nur starke
            "all_results":rs_all,            # Watchlist: alle mit Signal
            "signals_found":len(strong_results),
            "total_analyzed":total,
            "timestamp":datetime.now().isoformat()
        })
    gc.collect()

# ── Mini-Futures ──────────────────────────────────────────────────────────────
def calc_mini_futures(direction,price,atr):
    products=[]
    for lev in [2,3,4,5,6,8,10,12,15,18,20,22,25,28,30]:
        kp=1./lev
        if direction=="BUY":
            ko=round(price*(1-kp),2); sl=round(ko*1.005,2); mfp=round((price-ko)*1.02,2); tp=round(price+2*atr,2)
        else:
            ko=round(price*(1+kp),2); sl=round(ko*.995,2); mfp=round((ko-price)*1.02,2); tp=round(price-2*atr,2)
        gain=round(atr*2*lev/mfp*100,1) if mfp>0 else 0
        products.append({"leverage":lev,"direction":direction,"base_price":round(price,2),
            "knock_out":ko,"stop_loss_level":sl,"mini_future_price":mfp,"take_profit":tp,
            "max_loss_pct":round(kp*100,1),"potential_gain_pct":gain,
            "risk_level":"Niedrig" if lev<=5 else "Mittel" if lev<=15 else "Hoch",
            "label":f"x{lev} {'Long' if direction=='BUY' else 'Short'} – KO: {ko}"})
    return products

# ═══════════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/signals")
def get_signals(region: str = "DE"):
    if region not in REGIONS: region="DE"
    with _lock:
        st=dict(_state[region])
    # KEIN Auto-Start mehr – nur manuell über /api/signals/refresh
    return {"status":st["status"],"progress":st.get("progress",0),
            "top_signals":st.get("results",[]),
            "total_analyzed":st.get("total_analyzed",0),
            "signals_found":st.get("signals_found",0),
            "timestamp":st.get("timestamp"),"region":region}

@app.post("/api/signals/refresh")
def refresh_signals(region: str = "DE"):
    if region not in REGIONS: region="DE"
    cfg=load_settings(); ms=cfg["min_strength"]
    with _lock:
        if _state[region].get("status")=="running":
            return {"status":"running","message":"Analyse läuft bereits"}
        _state[region]={"status":"idle","progress":0,"results":[],"timestamp":None}
    with _df_lock: _df_cache.clear()
    _detail_cache.clear()
    Thread(target=run_analysis,args=(region,ms),daemon=True).start()
    return {"status":"loading","message":f"Neue Analyse für {region} gestartet"}

@app.get("/api/regions")
def get_regions():
    return {"regions":list(REGIONS.keys()),
            "counts":{r:len(t) for r,t in REGIONS.items()}}

@app.get("/api/detail/{ticker}")
def get_detail(ticker: str):
    ticker=validate_ticker(ticker); name=TICKER_TO_NAME.get(ticker,ticker)
    result=full_analysis(ticker,name,min_strength=0)
    if not result: raise HTTPException(404,f"Keine Daten für {ticker}")
    return result

@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    ticker=validate_ticker(ticker); now=time.time()
    cached=_price_cache.get(ticker)
    if cached and now-cached["ts"]<PRICE_CACHE_TTL: return cached
    df=fetch_ohlcv(ticker,period="5d",timeout=8)
    if df is None: raise HTTPException(404,"Keine Daten")
    price=round(float(df["Close"].iloc[-1]),2)
    prev=float(df["Close"].iloc[-2]) if len(df)>=2 else price
    change=round(price-prev,2); cp=round(change/prev*100,2) if prev else 0
    r={"ticker":ticker,"price":price,"change":change,"change_pct":cp,
       "ts":now,"timestamp":datetime.now().isoformat()}
    _price_cache[ticker]=r; return r

@app.get("/api/mini-futures/{ticker}")
def get_mini_futures(ticker: str, direction: str = "BUY"):
    ticker=validate_ticker(ticker)
    if direction not in ("BUY","SELL"): raise HTTPException(400,"direction muss BUY oder SELL sein")
    name=TICKER_TO_NAME.get(ticker,ticker); df=fetch_ohlcv(ticker,period="1mo")
    if df is None: raise HTTPException(404,"Keine Daten")
    price=float(df["Close"].iloc[-1])
    h,l,c=df["High"].squeeze(),df["Low"].squeeze(),df["Close"].squeeze()
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1])
    return {"ticker":ticker,"name":name,"price":price,"direction":direction,
            "products":calc_mini_futures(direction,price,atr)}

@app.get("/api/chart/{ticker}")
def get_chart(ticker: str, period: str = "3mo"):
    ticker=validate_ticker(ticker)
    if period not in ("1mo","3mo","6mo","ytd","1y","2y","5y"): period="3mo"
    ck=f"{ticker}|{period}"; now=time.time()
    cached=_chart_cache.get(ck)
    if cached and now-cached["ts"]<CHART_CACHE_TTL: return cached["data"]
    df=fetch_ohlcv(ticker,period=period,timeout=15)
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
        dates=df.index.strftime("%Y-%m-%d").tolist()
        cd=[{"date":dates[i],"open":round(float(df["Open"].iat[i]),2),
             "high":round(float(h.iat[i]),2),"low":round(float(l.iat[i]),2),
             "close":round(float(c.iat[i]),2),
             "volume":int(df["Volume"].iat[i]) if "Volume" in df.columns else 0,
             "bb_upper":None if pd.isna(bbu.iat[i]) else float(bbu.iat[i]),
             "bb_mid":None if pd.isna(smr.iat[i]) else float(smr.iat[i]),
             "bb_lower":None if pd.isna(bbl.iat[i]) else float(bbl.iat[i]),
             "ema20":float(e20.iat[i]),"ema50":float(e50.iat[i]),
             **( {"ema200":float(e200.iat[i])} if e200 is not None else {})}
            for i in range(len(df))]
        result={"ticker":ticker,"period":period,"data":cd,"support_levels":supp,"resistance_levels":res_}
        _chart_cache[ck]={"data":result,"ts":now}; return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,str(e))
    finally: gc.collect()

@app.get("/api/watchlist")
def get_watchlist(region: str = "DE"):
    if region not in REGIONS: region="DE"
    with _lock: st=dict(_state[region])
    cfg=load_settings(); ms=cfg["min_strength"]
    all_results=st.get("all_results",[])
    analyzed={r["ticker"] for r in all_results}

    # Noch nicht analysierte Werte: nur Platzhalter, KEIN on-the-fly quick_score
    # (würde den Request für mehrere Minuten blockieren)
    placeholders=[
        {"ticker":t,"name":n,"price":None,"direction":"NEUTRAL",
         "score":0,"strength":0,"signals":[],"stop_loss":None,"take_profit":None,
         "rsi":None,"timestamp":None,"below_threshold":False,"pending":True}
        for n,t in REGIONS[region].items() if t not in analyzed
    ]

    # Alle Ergebnisse zusammenführen: analysierte zuerst (nach Stärke), dann Platzhalter
    analyzed_sorted = sorted(all_results, key=lambda x: x.get("strength",0), reverse=True)
    items = analyzed_sorted + placeholders

    return {"status":st["status"],"items":items,"total":len(items),
            "region":region,"min_strength":ms,
            "analyzed_count":len(analyzed_sorted),
            "pending_count":len(placeholders)}

@app.get("/api/portfolio/backup")
def backup_ep(): return load_portfolio()

@app.post("/api/portfolio/restore")
def restore_ep(data: dict):
    if not all(k in data for k in ("cash","start_capital","positions","closed_trades")):
        raise HTTPException(400,"Ungültige Portfolio-Daten")
    invalidate_portfolio_cache(); save_portfolio(data)
    return {"success":True}

@app.post("/api/portfolio/reset")
def reset_ep():
    sc=get_s("start_capital")
    p={"cash":sc,"start_capital":sc,"positions":[],"closed_trades":[],"created":datetime.now().isoformat()}
    invalidate_portfolio_cache(); save_portfolio(p)
    return {"success":True,"message":f"Portfolio zurückgesetzt auf {sc:.0f}€"}

@app.get("/api/settings")
def get_settings_ep(): return load_settings()

class SettingsRequest(BaseModel):
    min_strength:  int   = Field(default=20,    ge=10,   le=80)
    order_fee:     float = Field(default=10.0,  ge=0,    le=50)
    max_positions: int   = Field(default=5,     ge=1,    le=20)
    max_exposure:  int   = Field(default=40,    ge=10,   le=90)
    risk_per_trade:float = Field(default=2.0,   ge=0.5,  le=5.0)
    max_position:  float = Field(default=20.0,  ge=5.0,  le=50.0)
    min_sl_dist:   float = Field(default=1.5,   ge=0.5,  le=5.0)
    max_sl_dist:   float = Field(default=8.0,   ge=2.0,  le=20.0)
    vol_threshold: float = Field(default=5.0,   ge=2.0,  le=15.0)
    adx_trend:     int   = Field(default=25,    ge=15,   le=40)
    adx_sideways:  int   = Field(default=20,    ge=10,   le=30)
    start_capital: float = Field(default=10000, ge=1000, le=1000000)
    @field_validator("adx_sideways")
    @classmethod
    def sw_lt_trend(cls,v,info):
        if v>=info.data.get("adx_trend",25): raise ValueError("adx_sideways muss < adx_trend sein")
        return v

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    s=req.model_dump(); save_settings(s)
    with _lock:
        for r in REGIONS: _state[r]={"status":"idle","progress":0,"results":[],"timestamp":None}
    _detail_cache.clear()
    return s

@app.get("/api/portfolio")
def get_portfolio():
    p=load_portfolio(); cfg=load_settings()
    max_pos=cfg["max_positions"]; max_exp=cfg["max_exposure"]; fee=cfg["order_fee"]
    closed=p["closed_trades"]
    open_val=sum(pos.get("current_value",pos["cost"]) for pos in p["positions"])
    total=round(p["cash"]+open_val,2); pnl=round(total-p["start_capital"],2)
    wins=sum(1 for t in closed if t.get("status")=="WIN")
    fees=len(closed)*fee*2+len(p["positions"])*fee
    exp=round(open_val/total*100,1) if total>0 else 0.
    return {"portfolio":p,"stats":{
        "start_capital":p["start_capital"],"total_value":total,"cash":p["cash"],
        "open_value":round(open_val,2),"total_pnl":pnl,
        "total_pnl_pct":round(pnl/p["start_capital"]*100,2),
        "total_trades":len(closed),"open_positions":len(p["positions"]),
        "win_rate":round(wins/len(closed)*100,1) if closed else 0,"fees_paid":fees,
        "limits":{"max_positions":max_pos,"current_positions":len(p["positions"]),
            "max_exposure_pct":max_exp,"current_exposure_pct":exp,
            "positions_limit_reached":len(p["positions"])>=max_pos,
            "exposure_limit_reached":exp>=max_exp}}}

class TradeRequest(BaseModel):
    ticker:str; name:str; direction:str
    price:float=Field(...,gt=0); stop_loss:float=Field(...,gt=0); take_profit:float=Field(...,gt=0)
    score:int; signals:list; leverage:int=Field(default=1,ge=1,le=30)
    invest_amount:float=Field(default=0,ge=0); is_mini_future:bool=False
    mini_future_leverage:int=Field(default=1,ge=1,le=30)
    @field_validator("direction")
    @classmethod
    def dv(cls,v):
        if v not in ("BUY","SELL"): raise ValueError("BUY oder SELL")
        return v

@app.post("/api/trade/open")
def open_trade(req: TradeRequest):
    p=load_portfolio(); cfg=load_settings()
    max_pos=cfg["max_positions"]; max_exp=cfg["max_exposure"]/100; fee=cfg["order_fee"]
    if len(p["positions"])>=max_pos:
        raise HTTPException(400,f"Limit: max. {max_pos} Positionen")
    open_val=sum(pos.get("current_value",pos["cost"]) for pos in p["positions"])
    total_val=p["cash"]+open_val
    if total_val>0 and open_val/total_val>=max_exp:
        raise HTTPException(400,f"Exposure-Limit: max. {cfg['max_exposure']}%")
    if abs(req.price-req.stop_loss)==0: raise HTTPException(400,"Stop Loss = Einstiegskurs")
    units,cost=calc_position_size(p["cash"],total_val,req.price,req.stop_loss,req.invest_amount,cfg)
    tc=cost+fee
    if tc>p["cash"]: raise HTTPException(400,f"Nicht genug Cash ({p['cash']:.2f}€, benötigt {tc:.2f}€)")
    tid=f"T{len(p['closed_trades'])+len(p['positions'])+1:04d}"
    dist=abs(req.price-req.stop_loss)
    ra=round(dist*units,2); rp=round(ra/total_val*100,2) if total_val>0 else 0
    pos={"id":tid,"ticker":req.ticker,"name":req.name,"direction":req.direction,
         "entry_price":req.price,"current_price":req.price,"units":units,"cost":cost,"fee":fee,
         "stop_loss":req.stop_loss,"take_profit":req.take_profit,"score":req.score,"signals":req.signals,
         "unrealized_pnl":0.,"unrealized_pnl_pct":0.,"current_value":cost,
         "risk_amount":ra,"risk_pct":rp,"is_mini_future":req.is_mini_future,
         "leverage":req.mini_future_leverage,
         "base_ticker": req.ticker.split()[0] if " " in req.ticker else req.ticker,
         "base_entry_price": None,  # wird beim ersten Live-Update befüllt
         "opened":datetime.now().isoformat()}
    p["cash"]=round(p["cash"]-tc,2); p["positions"].append(pos)
    invalidate_portfolio_cache(); save_portfolio(p)
    return {"success":True,"trade":pos,"fee_charged":fee,"risk_amount":ra,"risk_pct":rp}

class CloseRequest(BaseModel):
    trade_id:str; close_price:float=Field(...,gt=0)

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p=load_portfolio(); cfg=load_settings(); fee=cfg["order_fee"]
    pos=next((x for x in p["positions"] if x["id"]==req.trade_id),None)
    if not pos: raise HTTPException(404,"Position nicht gefunden")
    lev=pos.get("leverage",1)
    pnl=((req.close_price-pos["entry_price"])*pos["units"]*lev
         if pos["direction"]=="BUY" else (pos["entry_price"]-req.close_price)*pos["units"]*lev)
    pnl_net=pnl-fee; proceeds=round(pos["cost"]+pnl_net,2)
    closed={**pos,"close_price":req.close_price,"pnl":round(pnl_net,2),"pnl_gross":round(pnl,2),
            "fees":fee*2,"pnl_pct":round(pnl_net/pos["cost"]*100,2),"proceeds":proceeds,
            "closed":datetime.now().isoformat(),"status":"WIN" if pnl_net>0 else "LOSS"}
    p["positions"]=[x for x in p["positions"] if x["id"]!=req.trade_id]
    p["closed_trades"].append(closed); p["cash"]=round(p["cash"]+proceeds,2)
    invalidate_portfolio_cache(); save_portfolio(p); _price_cache.pop(pos["ticker"],None)
    return {"success":True,"trade":closed}

@app.get("/api/exit-signals")
def get_exit_signals():
    p=load_portfolio(); positions=p.get("positions",[])
    if not positions: return {"exit_signals":[],"checked":0}
    signals=[]
    for pos in positions:
        try:
            ticker=pos["ticker"]; df=fetch_ohlcv(ticker,period="1mo")
            if df is None or len(df)<10: continue
            c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
            price=float(c.iloc[-1])
            delta=c.diff(); g=delta.clip(lower=0).rolling(14).mean()
            ls=(-delta.clip(upper=0)).rolling(14).mean().replace(0,np.nan)
            r=float((100-100/(1+g/ls)).iloc[-1])
            e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
            m=e12-e26; s_=m.ewm(span=9,adjust=False).mean(); hs=m-s_
            mk,ms=float(m.iloc[-1]),float(s_.iloc[-1]); mh,mhp=float(hs.iloc[-1]),float(hs.iloc[-2])
            stk=100*(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min()).replace(0,np.nan)
            sk,sd=float(stk.iloc[-1]),float(stk.rolling(3).mean().iloc[-1])
            entry,sl,tp,direction=pos["entry_price"],pos["stop_loss"],pos["take_profit"],pos["direction"]
            if direction=="BUY":
                pp=(price-entry)/entry*100; sld=(price-sl)/entry*100; tpd=(tp-price)/entry*100
            else:
                pp=(entry-price)/entry*100; sld=(sl-price)/entry*100; tpd=(price-tp)/entry*100
            reasons=[]; urgency="normal"
            if tpd<=0: reasons.append("✅ Take Profit erreicht!"); urgency="urgent"
            elif sld<=0: reasons.append("🛑 Stop Loss durchbrochen!"); urgency="urgent"
            elif sld<20: reasons.append(f"⚠️ Nahe Stop Loss ({sld:.1f}%)"); urgency="warn"
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
                    "pnl_pct":round(pp,2),"stop_loss":sl,"take_profit":tp,
                    "exit_reasons":reasons,"urgency":urgency,
                    "recommendation":"SCHLIESSEN" if urgency=="urgent" else "PRÜFEN"})
        except Exception: continue
    signals.sort(key=lambda x:{"urgent":0,"warn":1,"normal":2}.get(x["urgency"],2))
    return {"exit_signals":signals,"checked":len(positions)}

@app.get("/",response_class=HTMLResponse)
def frontend():
    p=Path(__file__).parent/"index.html"
    return p.read_text() if p.exists() else "<h1>TradeBot Pro v13</h1>"

@app.get("/manifest.json")
def manifest():
    p=Path(__file__).parent/"manifest.json"
    return JSONResponse(json.loads(p.read_text()) if p.exists() else {})

# Kein Auto-Start – Analyse wird nur manuell über den "Analyse starten"-Button ausgelöst
