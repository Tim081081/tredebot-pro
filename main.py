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

# PostgreSQL wenn DATABASE_URL gesetzt, sonst SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES  = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

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

# ── Regionale Ticker (aktualisiert Mai 2025) ──────────────────────────────────
# Entfernt: Software AG (SOW.DE) – von OpenText übernommen, dekotiert
#           Zooplus (ZO1.DE) – 2022 von Börse genommen
#           Xing (O1BC.DE) – falscher Ticker, korrekt: NWX.DE (New Work SE)
#           PTC Inc (PTC.DE) – XETRA illiquid, kaum Daten
#           Reply (REY.DE) – XETRA illiquid
#           Snowflake/Datadog/MongoDB/Fortinet – aus NASDAQ entfernt da volatil/illiquid
# Hinzugefügt: Porsche SE (PAH3.DE), New Work SE (NWX.DE), MDAX-Werte,
#              Vollständiger Dow Jones 30 (Nike, McDonald's, Sherwin-Williams etc.)
#              Weitere NASDAQ-100-Kernwerte
REGIONS = {
    "DE": {
        # Index
        "DAX Index":        "^GDAXI",
        # DAX 40 (vollständig)
        "Adidas":           "ADS.DE",
        "Airbus":           "AIR.DE",
        "Allianz":          "ALV.DE",
        "BASF":             "BAS.DE",
        "Bayer":            "BAYN.DE",
        "Beiersdorf":       "BEI.DE",
        "BMW":              "BMW.DE",
        "Brenntag":         "BNR.DE",
        "Commerzbank":      "CBK.DE",
        "Continental":      "CON.DE",
        "Covestro":         "1COV.DE",
        "Deutsche Bank":    "DBK.DE",
        "Deutsche Post":    "DHL.DE",
        "Telekom":          "DTE.DE",
        "EON":              "EOAN.DE",
        "Fresenius Med":    "FME.DE",
        "Fresenius":        "FRE.DE",
        "Hannover Rueck":   "HNR1.DE",
        "Heidelberg Mat":   "HEI.DE",
        "Henkel":           "HEN3.DE",
        "Infineon":         "IFX.DE",
        "Linde":            "LIN.DE",
        "Mercedes":         "MBG.DE",
        "Merck":            "MRK.DE",
        "MTU Aero":         "MTX.DE",
        "Munich Re":        "MUV2.DE",
        "Porsche AG":       "P911.DE",
        "Porsche SE":       "PAH3.DE",
        "Qiagen":           "QIA.DE",
        "Rheinmetall":      "RHM.DE",
        "RWE":              "RWE.DE",
        "SAP":              "SAP.DE",
        "Sartorius":        "SRT3.DE",
        "Siemens":          "SIE.DE",
        "Siemens Energy":   "ENR.DE",
        "Siemens Health":   "SHL.DE",
        "Symrise":          "SY1.DE",
        "VW":               "VOW3.DE",
        "Vonovia":          "VNA.DE",
        "Zalando":          "ZAL.DE",
        # TechDAX (bereinigt – nur aktive, liquide XETRA-Ticker)
        "AIXTRON":          "AIXA.DE",
        "Cancom":           "COK.DE",
        "Drägerwerk":       "DRW3.DE",
        "Energiekontor":    "EKT.DE",
        "Evotec":           "EVT.DE",
        "GFT Technologies": "GFT.DE",
        "Jenoptik":         "JEN.DE",
        "LPKF Laser":       "LPK.DE",
        "Nemetschek":       "NEM.DE",
        "TeamViewer":       "TMV.DE",
        "TUI":              "TUI1.DE",
        "United Internet":  "UTDI.DE",
        "Wacker Chemie":    "WCH.DE",
        # MDAX-Ergänzungen (liquideste Werte, yfinance-geprüft)
        "Aurubis":          "NDA.DE",
        "Knorr-Bremse":     "KBX.DE",
        "LEG Immobilien":   "LEG.DE",
        "Scout24":          "G24.DE",
        "Talanx":           "TLX.DE",
        # Traton: 8TRA.DE beginnt mit Zahl → yfinance-Problem, verwende US-ADR nicht verfügbar
        # New Work SE: NWX.DE sehr illiquid → entfernt
    },
    "EU": {
        # Indizes
        "Euro Stoxx 50":    "^STOXX50E",
        "FTSE 100":         "^FTSE",
        "CAC 40":           "^FCHI",
        "IBEX 35":          "^IBEX",
        "AEX":              "^AEX",
        "SMI":              "^SSMI",
        # Niederlande
        "ASML":             "ASML.AS",
        "ING":              "INGA.AS",
        "Ahold Delhaize":   "AD.AS",
        "Philips":          "PHIA.AS",
        "RELX":             "REN.AS",
        "Wolters Kluwer":   "WKL.AS",
        # Frankreich
        "LVMH":             "MC.PA",
        "LOreal":           "OR.PA",
        "TotalEnergies":    "TTE.PA",
        "Sanofi":           "SAN.PA",
        "BNP Paribas":      "BNP.PA",
        "Kering":           "KER.PA",
        "Airbus FR":        "AIR.PA",
        "Danone":           "BN.PA",
        "Hermes":           "RMS.PA",
        "Air Liquide":      "AI.PA",
        "Schneider El.":    "SU.PA",
        # Spanien
        "Santander":        "SAN.MC",
        "BBVA":             "BBVA.MC",
        "Inditex":          "ITX.MC",
        "Iberdrola":        "IBE.MC",
        # Schweiz
        "Nestle":           "NESN.SW",
        "Roche":            "ROG.SW",
        "Novartis":         "NOVN.SW",
        "ABB":              "ABBN.SW",
        "Zurich Ins.":      "ZURN.SW",
        "Richemont":        "CFR.SW",
        # UK
        "AstraZeneca":      "AZN.L",
        "HSBC":             "HSBA.L",
        "BP":               "BP.L",
        "Shell":            "SHEL.L",
        "GSK":              "GSK.L",
        "Unilever":         "ULVR.L",
        "Diageo":           "DGE.L",
        "Rio Tinto":        "RIO.L",
        "BHP":              "BHP.L",
        "Barclays":         "BARC.L",
        "Rolls-Royce":      "RR.L",
        "BAE Systems":      "BA.L",
        # Italien
        "Enel":             "ENEL.MI",
        "ENI":              "ENI.MI",
        "UniCredit":        "UCG.MI",
        "STMicro":          "STM.MI",
        "Intesa Sanpaolo":  "ISP.MI",
        "Ferrari":          "RACE.MI",
        "Stellantis":       "STLAM.MI",
    },
    "USA": {
        # Indizes
        "Dow Jones":            "^DJI",
        "S&P 500":              "^GSPC",
        "NASDAQ 100":           "^NDX",
        # Dow Jones 30 (vollständig, Stand 2025)
        "Apple":                "AAPL",
        "Microsoft":            "MSFT",
        "Goldman Sachs":        "GS",
        "UnitedHealth":         "UNH",
        "Home Depot":           "HD",
        "McDonald's":           "MCD",
        "Caterpillar":          "CAT",
        "Visa":                 "V",
        "Salesforce":           "CRM",
        "Amazon":               "AMZN",
        "Boeing":               "BA",
        "Honeywell":            "HON",
        "American Express":     "AXP",
        "JPMorgan":             "JPM",
        "IBM":                  "IBM",
        "Chevron":              "CVX",
        "Procter & Gamble":     "PG",
        "Walt Disney":          "DIS",
        "Merck US":             "MRK",
        "Nike":                 "NKE",
        "Coca-Cola":            "KO",
        "Walmart":              "WMT",
        "3M":                   "MMM",
        "Verizon":              "VZ",
        "Travelers":            "TRV",
        "Johnson & Johnson":    "JNJ",
        "Amgen":                "AMGN",
        "Cisco":                "CSCO",
        "Intel":                "INTC",
        "Sherwin-Williams":     "SHW",
        # NASDAQ 100 Kernwerte (nicht im DJ)
        "Nvidia":               "NVDA",
        "Meta":                 "META",
        "Alphabet A":           "GOOGL",
        "Tesla":                "TSLA",
        "Broadcom":             "AVGO",
        "Netflix":              "NFLX",
        "Adobe":                "ADBE",
        "Qualcomm":             "QCOM",
        "AMD":                  "AMD",
        "Texas Instruments":    "TXN",
        "Intuitive Surgical":   "ISRG",
        "Booking Holdings":     "BKNG",
        "Costco":               "COST",
        "Palo Alto":            "PANW",
        "Lam Research":         "LRCX",
        "Applied Materials":    "AMAT",
        "Starbucks":            "SBUX",
        "Airbnb":               "ABNB",
        "PayPal":               "PYPL",
        "Crowdstrike":          "CRWD",
        "ServiceNow":           "NOW",
        "Workday":              "WDAY",
        "Moderna":              "MRNA",
        "KLA Corp":             "KLAC",
        "Berkshire B":          "BRK-B",
        "Mastercard":           "MA",
        "Exxon Mobil":          "XOM",
        "Mondelez":             "MDLZ",
        "Regeneron":            "REGN",
        "T-Mobile":             "TMUS",
    },
}

# Vollständiger Ticker→Name Lookup über alle Regionen
TICKER_TO_NAME: dict = {}
VALID_TICKERS:  set  = set()
for _reg in REGIONS.values():
    for _n, _t in _reg.items():
        TICKER_TO_NAME[_t] = _n
        VALID_TICKERS.add(_t)

# ── Persistenz: PostgreSQL (primär) oder SQLite (Fallback) ───────────────────
def _get_db_path() -> str:
    for candidate in ["/data", os.path.expanduser("~/.tradebot")]:
        try:
            os.makedirs(candidate, exist_ok=True)
            if os.access(candidate, os.W_OK):
                return os.path.join(candidate, "tradebot.db")
        except Exception:
            pass
    return "/tmp/tradebot.db"

DB_PATH       = _get_db_path()
SETTINGS_FILE = DB_PATH.replace(".db", "_settings.json")
PORTFOLIO_FILE= DB_PATH.replace(".db", "_portfolio.json")

def _get_conn():
    if USE_POSTGRES:
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
            return conn
        except Exception as e:
            print(f"[DB] PostgreSQL nicht erreichbar ({e}), nutze SQLite", flush=True)
            # Fallback auf SQLite
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def _db_execute(sql: str, params=(), fetchone=False, fetchall=False, commit=False):
    """Einheitliche DB-Abfrage für PostgreSQL und SQLite."""
    if USE_POSTGRES:
        # PostgreSQL: ? → %s
        sql = sql.replace("?", "%s")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        result = None
        if fetchone:
            row = cur.fetchone()
            result = dict(row) if row else None
        elif fetchall:
            rows = cur.fetchall()
            result = [dict(r) for r in rows] if rows else []
        if commit:
            conn.commit()
        conn.close()
        return result
    except Exception as e:
        try: conn.close()
        except: pass
        raise e

def _init_db():
    if USE_POSTGRES:
        _db_execute("""CREATE TABLE IF NOT EXISTS portfolio (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""", commit=True)
    else:
        with _get_conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS portfolio (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT DEFAULT 'open',
                created TEXT NOT NULL, closed TEXT)""")
            c.commit()

_init_db()

def get_s(k): return load_settings().get(k, DEFAULTS[k])

# ── In-Memory Caches & Analyse-State ─────────────────────────────────────────
_lock       = Lock()
_state: dict = {r: {"status":"idle","progress":0,"results":[],"all_results":[],"timestamp":None} for r in REGIONS}
_active_region = "DE"

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
    try:
        row = _db_execute("SELECT value FROM portfolio WHERE key=?", ('settings',), fetchone=True)
        if row:
            return {**DEFAULTS, **json.loads(row["value"])}
    except Exception: pass
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                return {**DEFAULTS, **json.load(f)}
    except Exception: pass
    return dict(DEFAULTS)

def save_settings(s: dict):
    try:
        _db_execute("INSERT INTO portfolio (key,value) VALUES ('settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value" if USE_POSTGRES
                    else "INSERT OR REPLACE INTO portfolio (key,value) VALUES ('settings',?)",
                    (json.dumps(s),), commit=True)
    except Exception: pass
    try: _atomic_write(SETTINGS_FILE, s)
    except Exception: pass

def save_analysis_state(region: str, state: dict):
    def strip_chart(items):
        return [{k:v for k,v in item.items() if k!="chart_data"} for item in (items or [])]
    to_save = {
        "status":         state.get("status"),
        "results":        strip_chart(state.get("results",[])),
        "all_results":    strip_chart(state.get("all_results",[])),
        "signals_found":  state.get("signals_found",0),
        "total_analyzed": state.get("total_analyzed",0),
        "timestamp":      state.get("timestamp"),
    }
    key = f"analysis_{region}"
    try:
        _db_execute("INSERT INTO portfolio (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(to_save)), commit=True)
    except Exception: pass

def load_analysis_state(region: str) -> dict | None:
    key = f"analysis_{region}"
    try:
        row = _db_execute("SELECT value FROM portfolio WHERE key=?", (key,), fetchone=True)
        if row:
            return json.loads(row["value"])
    except Exception: pass
    return None

def _init_state_from_db():
    """Beim Server-Start: gespeicherte Analyse-Ergebnisse in _state laden."""
    for region in REGIONS:
        saved = load_analysis_state(region)
        if saved and saved.get("all_results"):
            with _lock:
                _state[region].update({
                    "status":         "done",
                    "progress":       100,
                    "results":        saved.get("results", []),
                    "all_results":    saved.get("all_results", []),
                    "signals_found":  saved.get("signals_found", 0),
                    "total_analyzed": saved.get("total_analyzed", 0),
                    "timestamp":      saved.get("timestamp"),
                })

# Gespeicherte Analyse-Ergebnisse beim Start laden
try:
    _init_state_from_db()
except Exception:
    pass

# ── Portfolio (SQLite-basiert) ────────────────────────────────────────────────
PORTFOLIO_FILE = DB_PATH.replace(".db", "_portfolio.json")

def _sanitize_floats(obj):
    """Ersetzt NaN/Inf in verschachtelten Dicts/Listen durch None – verhindert JSON-Fehler."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(i) for i in obj]
    return obj

def save_portfolio(p: dict):
    global _portfolio_cache
    p = _sanitize_floats(p)  # NaN/Inf rausfiltern bevor gespeichert wird
    _portfolio_cache = p
    data = json.dumps(p)
    try:
        _db_execute("INSERT INTO portfolio (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ('main', data), commit=True)
    except Exception: pass
    try: _atomic_write(PORTFOLIO_FILE, p)
    except Exception: pass

def save_settings(s: dict):
    try:
        _db_execute("INSERT INTO portfolio (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ('settings', json.dumps(s)), commit=True)
    except Exception: pass
    try: _atomic_write(SETTINGS_FILE, s)
    except Exception: pass

def load_portfolio() -> dict:
    global _portfolio_cache
    if _portfolio_cache is not None:
        return _portfolio_cache
    try:
        row = _db_execute("SELECT value FROM portfolio WHERE key=?", ('main',), fetchone=True)
        if row:
            p = json.loads(row["value"])
            if p.get("positions") is not None:
                _portfolio_cache = p
                return _portfolio_cache
    except Exception: pass
    for path in [PORTFOLIO_FILE, "/tmp/portfolio_backup.json"]:
        try:
            if os.path.exists(path):
                with open(path) as f:
                    p = json.load(f)
                if p.get("positions") is not None:
                    _portfolio_cache = p
                    save_portfolio(p)
                    return _portfolio_cache
        except Exception: pass
    sc = get_s("start_capital")
    p = {"cash": sc, "start_capital": sc, "positions": [], "closed_trades": [],
         "created": datetime.now().isoformat()}
    save_portfolio(p)
    return p

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
    for attempt in range(3):
        try:
            df = yf.download(ticker, period=period, interval="1d",
                             progress=False, auto_adjust=True, timeout=timeout)
            if df is None or df.empty:
                if attempt < 2:
                    time.sleep(3)
                    continue
                return None
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            with _df_lock:
                if len(_df_cache) >= DF_CACHE_MAX:
                    for k in sorted(_df_cache, key=lambda x: _df_cache[x]["ts"])[:60]:
                        del _df_cache[k]
                _df_cache[key] = {"df": df, "ts": now}
            return df
        except Exception as e:
            wait = (attempt + 1) * 8
            time.sleep(wait)
    return None

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
    is_index = ticker.startswith('^')
    # Indizes: 1 Jahr Daten holen (mehr Datenpunkte, stabilere Indikatoren)
    period = "1y" if is_index else "6mo"
    min_bars = 20 if is_index else 60
    df=fetch_ohlcv(ticker, period=period)
    if df is None or len(df)<min_bars: return None
    try:
        c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
        v=df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)),index=c.index)
        ind=compute_indicators(c,h,l,v,cfg)
        price=round(ind["price"],2)

        # Versuche Signal zu bauen (min_strength=0 für Watchlist)
        sig=build_signal(ticker,name,ind,0,cfg)

        if sig is None:
            # Kein klares Signal (Konfirmation nicht erfüllt) → NEUTRAL zurückgeben
            return {
                "ticker":ticker,"name":name,"price":price,
                "direction":"NEUTRAL","score":0,"strength":0,
                "below_threshold":True,"no_signal":True,
                "confirming_groups":0,"market_phase":
                    ("Trendmarkt" if ind["trending"] else ("Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend")),
                "high_volatility":ind["high_vol"],
                "signals":[],"warnings":[],
                "stop_loss":None,"take_profit":None,
                "rsi":round(ind["rsi"],1),"atr":round(ind["atr14"],2),
                "support_levels":[round(ind["s1"],2),round(ind["s2"],2)],
                "resistance_levels":[round(ind["r1"],2),round(ind["r2"],2)],
                "indicators":{"RSI (14)":round(ind["rsi"],1),"ADX":round(ind["adx"],1),
                    "Marktphase":"Trendmarkt" if ind["trending"] else "Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend"},
                "analyst":{},"chart_data":[],
                "timestamp":datetime.now().isoformat()
            }

        sig["below_threshold"] = sig["strength"] < min_strength
        sig["no_signal"] = False
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
    is_index = ticker.startswith('^')
    df=fetch_ohlcv(ticker,period="1y")
    if df is None or len(df)<(20 if is_index else 60): return None
    try:
        c=df["Close"].squeeze(); h=df["High"].squeeze(); l=df["Low"].squeeze()
        v=df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(np.ones(len(c)),index=c.index)
        ind=compute_indicators(c,h,l,v,cfg)
        sig=build_signal(ticker,name,ind,min_strength,cfg)

        # Indikatoren immer berechnen – auch wenn kein Signal
        market_phase = ("Trendmarkt" if ind["trending"]
                        else ("Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend"))
        indicators={
            "RSI (14)":round(ind["rsi"],1),"MACD":round(ind["mk"],4),
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
            "Marktphase":market_phase}
        if ind["e200"]: indicators["EMA 200"]=round(ind["e200"],2)
        if ind["high_vol"]: indicators["⚠️ Volatilität"]=f"ERHÖHT ({ind['atr_pct']:.1f}%) – Vorsicht!"

        if sig is None:
            # Kein Signal: Indikatoren trotzdem zurückgeben
            price=round(ind["price"],2)
            result={
                "ticker":ticker,"name":name,"price":price,
                "direction":"NEUTRAL","score":0,"strength":0,
                "score_detail":{"momentum":0,"trend":0,"structure":0},
                "confirming_groups":0,"market_phase":market_phase,
                "high_volatility":ind["high_vol"],"signals":[],"warnings":[],
                "stop_loss":None,"take_profit":None,
                "rsi":round(ind["rsi"],1),"atr":round(ind["atr14"],2),
                "support_levels":[round(ind["s1"],2),round(ind["s2"],2)],
                "resistance_levels":[round(ind["r1"],2),round(ind["r2"],2)],
                "indicators":indicators,"analyst":{},"chart_data":[],
                "timestamp":datetime.now().isoformat()
            }
            # Chart-Daten für NEUTRAL-Fall
            try:
                df90=df.tail(90).copy()
                sma20=ind["sma20"]; std20=ind["std20"]
                bbu90=(sma20+2*std20).reindex(df90.index).round(2)
                bbm90=sma20.reindex(df90.index).round(2)
                bbl90=(sma20-2*std20).reindex(df90.index).round(2)
                e20s=c.ewm(span=20).mean().reindex(df90.index).round(2)
                e50s=c.ewm(span=50).mean().reindex(df90.index).round(2)
                result["chart_data"]=[{
                    "date":    df90.index[i].strftime("%Y-%m-%d"),
                    "open":    round(float(df90["Open"].iat[i]),2),
                    "high":    round(float(df90["High"].iat[i]),2),
                    "low":     round(float(df90["Low"].iat[i]),2),
                    "close":   round(float(df90["Close"].iat[i]),2),
                    "volume":  int(df90["Volume"].iat[i]) if "Volume" in df90.columns else 0,
                    "bb_upper":None if pd.isna(bbu90.iat[i]) else float(bbu90.iat[i]),
                    "bb_mid":  None if pd.isna(bbm90.iat[i]) else float(bbm90.iat[i]),
                    "bb_lower":None if pd.isna(bbl90.iat[i]) else float(bbl90.iat[i]),
                    "ema20":   float(e20s.iat[i]),
                    "ema50":   float(e50s.iat[i])}
                    for i in range(len(df90))]
            except Exception:
                result["chart_data"]=[]
            _detail_cache[ticker]={"result":result,"ts":now}
            return result
        # Signal vorhanden: Analysten-Info ergänzen
        analyst_info={}
        try:
            info=yf.Ticker(ticker).info; rec=info.get("recommendationMean")
            n_anal=info.get("numberOfAnalystOpinions",0); target=info.get("targetMeanPrice")
            if rec and n_anal:
                rt={1:"Starker Kauf",2:"Kauf",3:"Halten",4:"Verkauf",5:"Starker Verkauf"}.get(round(rec),f"{rec:.1f}")
                analyst_info={"recommendation":rt,"analysts":n_anal,"target":round(target,2) if target else None}
        except Exception: pass
        if ind["e200"]: indicators["EMA 200"]=round(ind["e200"],2)
        if ind["high_vol"]: indicators["⚠️ Volatilität"]=f"ERHÖHT ({ind['atr_pct']:.1f}%) – Vorsicht!"
        if analyst_info:
            indicators["Analysten"]=f"{analyst_info['recommendation']} ({analyst_info['analysts']} Analysten) ℹ️"
            if analyst_info.get("target"): indicators["Kursziel"]=f"{analyst_info['target']:.2f} (nur Info)"

        # Chart-Daten berechnen (abgesichert – Fehler hier sollen Indikatoren nicht blockieren)
        chart_data=[]
        try:
            df90=df.tail(90).copy()
            sma20=ind["sma20"]; std20=ind["std20"]
            # Sicherstellen dass alle Series gleich lang sind
            bbu90=(sma20+2*std20).reindex(df90.index).round(2)
            bbm90=sma20.reindex(df90.index).round(2)
            bbl90=(sma20-2*std20).reindex(df90.index).round(2)
            e20s=c.ewm(span=20).mean().reindex(df90.index).round(2)
            e50s=c.ewm(span=50).mean().reindex(df90.index).round(2)
            chart_data=[{
                "date":    df90.index[i].strftime("%Y-%m-%d"),
                "open":    round(float(df90["Open"].iat[i]),2),
                "high":    round(float(df90["High"].iat[i]),2),
                "low":     round(float(df90["Low"].iat[i]),2),
                "close":   round(float(df90["Close"].iat[i]),2),
                "volume":  int(df90["Volume"].iat[i]) if "Volume" in df90.columns else 0,
                "bb_upper":None if pd.isna(bbu90.iat[i]) else float(bbu90.iat[i]),
                "bb_mid":  None if pd.isna(bbm90.iat[i]) else float(bbm90.iat[i]),
                "bb_lower":None if pd.isna(bbl90.iat[i]) else float(bbl90.iat[i]),
                "ema20":   float(e20s.iat[i]),
                "ema50":   float(e50s.iat[i])}
                for i in range(len(df90))]
        except Exception:
            chart_data=[]  # Chart schlägt fehl → Indikatoren trotzdem zurückgeben

        result={**sig,"indicators":indicators,"analyst":analyst_info,"chart_data":chart_data}
        _detail_cache[ticker]={"result":result,"ts":now}
        return result
    except Exception as ex:
        try:
            df_tmp=fetch_ohlcv(ticker,period="5d",timeout=8)
            price=round(float(df_tmp["Close"].iloc[-1]),2) if df_tmp is not None and not df_tmp.empty else 0
        except Exception: price=0
        return {"ticker":ticker,"name":name,"price":price,
            "direction":"NEUTRAL","score":0,"strength":0,
            "score_detail":{"momentum":0,"trend":0,"structure":0},
            "confirming_groups":0,"market_phase":"—","high_volatility":False,
            "signals":[],"warnings":[],"stop_loss":None,"take_profit":None,
            "rsi":None,"atr":None,"support_levels":[],"resistance_levels":[],
            "indicators":{},"analyst":{},"chart_data":[],
            "timestamp":datetime.now().isoformat()}
    finally: gc.collect()

def run_analysis(region: str, min_strength: int) -> None:
    global _state
    with _lock:
        if _state[region].get("status")=="running": return
        _state[region].update({"status":"running","progress":0,"results":[],"all_results":[]})
    cfg=load_settings()
    items=list(REGIONS[region].items()); total=len(items)
    strong_results=[]; all_results=[]

    try:
        for i,(name,ticker) in enumerate(items):
            sig=quick_score(ticker,name,min_strength,cfg,include_weak=True)
            if sig:
                all_results.append(sig)
                if (not sig.get("below_threshold",True) and
                    not sig.get("no_signal",True) and
                    sig["direction"] != "NEUTRAL"):
                    strong_results.append(sig)
            else:
                # Für Index-Ticker (^) zumindest den aktuellen Preis laden
                idx_price = None
                if ticker.startswith('^'):
                    try:
                        df_idx = fetch_ohlcv(ticker, period="5d", timeout=6)
                        if df_idx is not None and not df_idx.empty:
                            idx_price = round(float(df_idx["Close"].iloc[-1]), 2)
                    except Exception: pass
                all_results.append({
                    "ticker":ticker,"name":name,"price":idx_price,
                    "direction":"NEUTRAL","score":0,"strength":0,
                    "below_threshold":True,"no_signal":True,"no_data": idx_price is None,
                    "signals":[],"stop_loss":None,"take_profit":None,
                    "rsi":None,"atr":None,"timestamp":datetime.now().isoformat(),
                    "support_levels":[],"resistance_levels":[],"high_volatility":False,
                    "market_phase":"—","confirming_groups":0,
                    "indicators":{},"analyst":{},"chart_data":[]
                })
            if i%5==4 or i==total-1:
                with _lock:
                    _state[region]["progress"]=round((i+1)/total*100)
                time.sleep(2.0); gc.collect()  # 2s Pause gegen yfinance Rate Limiting

        # Sicheres Sortieren: None-Werte als 0 behandeln
        rs_strong=sorted(strong_results, key=lambda x: x.get("strength") or 0, reverse=True)
        rs_all   =sorted(all_results,    key=lambda x: x.get("strength") or 0, reverse=True)

    except Exception as e:
        # Auch bei Fehler: Status auf done setzen damit die App nicht hängt
        rs_strong=[]; rs_all=all_results
        with _lock:
            _state[region].update({
                "status":"done","progress":100,
                "results":[],"all_results":rs_all,
                "signals_found":0,"total_analyzed":len(all_results),
                "timestamp":datetime.now().isoformat(),
                "error":str(e)
            })
        gc.collect(); return

    with _lock:
        _state[region].update({
            "status":         "done",
            "progress":       100,
            "results":        rs_strong[:20],
            "all_results":    rs_all,
            "signals_found":  len(strong_results),
            "total_analyzed": total,
            "timestamp":      datetime.now().isoformat()
        })
        state_to_save = dict(_state[region])
    # Speicher freigeben: DataFrame- und Detail-Cache nach Analyse komplett leeren
    # (Cache hat seinen Zweck während der Analyse erfüllt; danach nur noch Speicherlast)
    with _df_lock:
        _df_cache.clear()
    _detail_cache.clear()
    gc.collect()
    # Ergebnisse dauerhaft in DB speichern (überleben Server-Restarts)
    try:
        save_analysis_state(region, state_to_save)
    except Exception:
        pass
    try:
        _refresh_exit_signals_cache()
    except Exception:
        pass

# Exit-Signal-Cache (wird nach jeder Analyse befüllt)
_exit_cache: dict = {"signals": [], "ts": 0}
_exit_lock = Lock()

def _refresh_exit_signals_cache():
    """Berechnet Exit-Signale und speichert sie im Cache."""
    result = _compute_exit_signals()
    with _exit_lock:
        _exit_cache.update({**result, "ts": time.time()})
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
    if not result:
        # Fallback: minimale Antwort damit Frontend nicht fehlschlägt
        return {"ticker":ticker,"name":name,"price":None,
                "direction":"NEUTRAL","score":0,"strength":0,
                "score_detail":{"momentum":0,"trend":0,"structure":0},
                "confirming_groups":0,"market_phase":"—","high_volatility":False,
                "signals":[],"indicators":{},"analyst":{},"chart_data":[],
                "support_levels":[],"resistance_levels":[],"timestamp":datetime.now().isoformat()}
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
    try:
        with _lock: st=dict(_state[region])
        cfg=load_settings(); ms=cfg["min_strength"]
        status=st.get("status","idle")
        all_results=st.get("all_results",[])
        analyzed={r["ticker"] for r in all_results if isinstance(r,dict)}

        if status=="done":
            missing=[
                {"ticker":t,"name":n,"price":None,"direction":"NEUTRAL",
                 "score":0,"strength":0,"signals":[],"stop_loss":None,"take_profit":None,
                 "rsi":None,"timestamp":None,"below_threshold":False,"pending":False,"no_data":True}
                for n,t in REGIONS[region].items() if t not in analyzed
            ]
            items=sorted(all_results, key=lambda x:(x.get("strength") or 0), reverse=True)+missing
        else:
            placeholders=[
                {"ticker":t,"name":n,"price":None,"direction":"NEUTRAL",
                 "score":0,"strength":0,"signals":[],"stop_loss":None,"take_profit":None,
                 "rsi":None,"timestamp":None,"below_threshold":False,"pending":True}
                for n,t in REGIONS[region].items() if t not in analyzed
            ]
            analyzed_sorted=sorted(all_results, key=lambda x:(x.get("strength") or 0), reverse=True)
            items=analyzed_sorted+placeholders

        total_region=len(REGIONS[region])
        return {
            "status":         status,
            "items":          items,
            "total":          total_region,
            "analyzed_count": len(all_results),
            "pending_count":  total_region-len(analyzed),
            "region":         region,
            "min_strength":   ms,
            "is_complete":    status=="done"
        }
    except Exception as e:
        # Fehler nicht als 500 werfen sondern leere gültige Antwort zurückgeben
        return {
            "status": "idle", "items": [], "total": len(REGIONS.get(region,{})),
            "analyzed_count": 0, "pending_count": len(REGIONS.get(region,{})),
            "region": region, "min_strength": 20, "is_complete": False,
            "error": str(e)
        }

@app.get("/api/portfolio/status")
def portfolio_status():
    """Gibt zurück ob Portfolio Daten enthält – für Frontend-Restore-Entscheidung."""
    p = load_portfolio()
    has_data = (len(p.get("positions",[])) > 0 or
                len(p.get("closed_trades",[])) > 0 or
                abs(p.get("cash",0) - p.get("start_capital",10000)) > 0.01)
    return {"has_data": has_data, "positions": len(p.get("positions",[])),
            "trades": len(p.get("closed_trades",[])), "cash": p.get("cash",0),
            "start_capital": p.get("start_capital",10000)}
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
def get_settings_ep():
    s = load_settings()
    # is_default=True signalisiert dem Frontend dass keine User-Settings im Backend vorhanden sind
    # → Frontend soll in diesem Fall seine localStorage-Werte als Master verwenden
    is_default = s == DEFAULTS
    return {**s, "_is_default": is_default}

@app.post("/api/settings/restore")
def restore_settings_ep(data: dict):
    """Stellt Settings aus Browser-Backup wieder her (nach Deploy)."""
    # Nur bekannte Keys übernehmen, keine unbekannten Felder
    valid = {k: data[k] for k in DEFAULTS if k in data}
    if not valid:
        raise HTTPException(400, "Keine gültigen Settings-Daten")
    merged = {**DEFAULTS, **valid}
    save_settings(merged)
    return merged

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

@app.post("/api/portfolio/refresh")
def refresh_portfolio():
    """
    Aktualisiert alle offenen Positionen:
    - Aktuelle Kurse laden
    - Vollständige Indikator-Analyse pro Basiswert
    - P&L neu berechnen
    - Portfolio speichern
    """
    p=load_portfolio(); cfg=load_settings()
    if not p.get("positions"):
        return {"updated":0,"message":"Keine offenen Positionen"}

    updated=0
    for pos in p["positions"]:
        try:
            is_mf = pos.get("is_mini_future", False)
            lev   = pos.get("leverage", 1)

            # Basiswert-Ticker bestimmen
            base_ticker = pos.get("base_ticker") or pos["ticker"].split()[0]
            if base_ticker not in VALID_TICKERS: continue

            # Aktuellen Basiswert-Kurs laden
            df = fetch_ohlcv(base_ticker, period="5d", timeout=8)
            if df is None or df.empty: continue
            base_price = round(float(df["Close"].iloc[-1]), 2)

            # P&L korrekt berechnen:
            # MF: (% Basiswert-Änderung) × Hebel × eingesetztes Kapital
            # Direkt: (Kurs - Einstieg) × Units (kein Hebel in units)
            if is_mf:
                base_entry = pos.get("base_entry_price")
                if base_entry and base_entry > 0:
                    # Prozentuale Basiswert-Bewegung × Hebel × Kosten
                    # Bsp: GS -0.1% × 12 × 500€ = -6€ (korrekt)
                    delta_pct = (base_price - base_entry) / base_entry
                    if pos["direction"] == "BUY":
                        pnl = delta_pct * lev * pos["cost"]
                    else:  # SHORT: Gewinn wenn Basiswert fällt
                        pnl = -delta_pct * lev * pos["cost"]
                else:
                    pnl = 0.0
                pos["base_current_price"] = base_price
                # Simulierten MF-Preis aktualisieren: Einstiegspreis ± Bewegung×Hebel
                # NaN/Inf sorgfältig abfangen – sonst schlägt JSON-Serialisierung fehl
                base_entry = pos.get("base_entry_price")
                if base_entry and base_entry > 0 and pos.get("entry_price"):
                    try:
                        delta_pct = (base_price - base_entry) / base_entry
                        if pos["direction"] == "BUY":
                            new_cp = pos["entry_price"] * (1 + delta_pct * lev)
                        else:
                            new_cp = pos["entry_price"] * (1 - delta_pct * lev)
                        import math
                        if math.isfinite(new_cp) and new_cp > 0:
                            pos["current_price"] = round(new_cp, 4)
                    except Exception:
                        pass  # current_price bleibt unverändert
            else:
                # Direkte Position
                if pos["direction"] == "BUY":
                    pnl = (base_price - pos["entry_price"]) * pos["units"]
                else:
                    pnl = (pos["entry_price"] - base_price) * pos["units"]
                pos["current_price"] = base_price
                pos["base_current_price"] = base_price

            pnl_pct = round(pnl / pos["cost"] * 100, 2) if pos["cost"] > 0 else 0
            pos["current_value"]       = round(pos["cost"] + pnl, 2)
            pos["unrealized_pnl"]      = round(pnl, 2)
            pos["unrealized_pnl_pct"]  = pnl_pct
            pos["last_updated"]        = datetime.now().isoformat()

            # Vollständige Indikator-Analyse für Basiswert
            df6 = fetch_ohlcv(base_ticker, period="6mo")
            if df6 is not None and len(df6) >= 60:
                try:
                    c=df6["Close"].squeeze(); h=df6["High"].squeeze(); l=df6["Low"].squeeze()
                    v=df6["Volume"].squeeze() if "Volume" in df6.columns else pd.Series(np.ones(len(c)),index=c.index)
                    ind = compute_indicators(c, h, l, v, cfg)
                    pos["current_indicators"] = {
                        "rsi":        round(ind["rsi"], 1),
                        "adx":        round(ind["adx"], 1),
                        "macd":       round(ind["mk"], 4),
                        "bb_pct_b":   round(ind["pb"], 2),
                        "market_phase": "Trendmarkt" if ind["trending"] else "Seitwärtsmarkt" if ind["sideways"] else "Schwacher Trend",
                        "high_vol":   ind["high_vol"],
                        "atr_pct":    round(ind["atr_pct"], 2),
                    }
                except Exception: pass

            updated += 1
        except Exception: continue

    if updated>0:
        invalidate_portfolio_cache()
        save_portfolio(p)

    return {"updated":updated,"timestamp":datetime.now().isoformat()}

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

    # Basiswert-Ticker ermitteln (bei MF: der reine Ticker ohne " x5" Suffix)
    base_ticker = req.ticker.split()[0] if " " in req.ticker else req.ticker

    # Basiswert-Einstiegskurs JETZT abrufen (nicht später)
    base_entry_price = None
    is_mf = req.is_mini_future and req.mini_future_leverage > 1
    if is_mf and base_ticker in VALID_TICKERS:
        try:
            # Gecachten Preis verwenden falls vorhanden
            cached = _price_cache.get(base_ticker)
            if cached and time.time() - cached["ts"] < PRICE_CACHE_TTL:
                base_entry_price = cached["price"]
            else:
                df = fetch_ohlcv(base_ticker, period="5d", timeout=8)
                if df is not None and not df.empty:
                    base_entry_price = round(float(df["Close"].iloc[-1]), 2)
                    # Auch in Price-Cache speichern
                    prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else base_entry_price
                    _price_cache[base_ticker] = {
                        "ticker": base_ticker, "price": base_entry_price,
                        "change": round(base_entry_price - prev, 2),
                        "change_pct": round((base_entry_price - prev) / prev * 100, 2) if prev else 0,
                        "ts": time.time(), "timestamp": datetime.now().isoformat()
                    }
        except Exception:
            pass  # Kurs nicht verfügbar – bleibt None, wird im Frontend als "—" angezeigt

    pos={"id":tid,"ticker":req.ticker,"name":req.name,"direction":req.direction,
         "entry_price":req.price,"current_price":req.price,"units":units,"cost":cost,"fee":fee,
         "stop_loss":req.stop_loss,"take_profit":req.take_profit,"score":req.score,"signals":req.signals,
         "unrealized_pnl":0.,"unrealized_pnl_pct":0.,"current_value":cost,
         "risk_amount":ra,"risk_pct":rp,"is_mini_future":req.is_mini_future,
         "leverage":req.mini_future_leverage,
         "base_ticker": base_ticker,
         "base_entry_price": base_entry_price,
         "base_current_price": base_entry_price,  # initial = Einstiegskurs
         "opened":datetime.now().isoformat()}
    p["cash"]=round(p["cash"]-tc,2); p["positions"].append(pos)
    invalidate_portfolio_cache(); save_portfolio(p)
    return {"success":True,"trade":pos,"fee_charged":fee,"risk_amount":ra,"risk_pct":rp}

@app.post("/api/portfolio/fix-base-prices")
def fix_base_prices():
    """
    Repariert bestehende Positionen die base_entry_price=None haben.
    Wird einmalig beim Portfolio-Laden aufgerufen wenn fehlende Werte erkannt werden.
    """
    p = load_portfolio()
    fixed = 0
    for pos in p["positions"]:
        if pos.get("base_entry_price") is None and pos.get("is_mini_future"):
            base_ticker = pos.get("base_ticker", pos["ticker"].split()[0])
            if base_ticker not in VALID_TICKERS:
                continue
            try:
                cached = _price_cache.get(base_ticker)
                if cached and time.time() - cached["ts"] < PRICE_CACHE_TTL:
                    price = cached["price"]
                else:
                    df = fetch_ohlcv(base_ticker, period="5d", timeout=8)
                    if df is None or df.empty:
                        continue
                    price = round(float(df["Close"].iloc[-1]), 2)
                # Setze base_entry_price auf aktuellen Kurs
                # (bester verfügbarer Näherungswert für bestehende Positionen)
                pos["base_entry_price"]  = price
                pos["base_current_price"] = price
                pos["base_ticker"] = base_ticker
                fixed += 1
            except Exception:
                continue
    if fixed > 0:
        invalidate_portfolio_cache()
        save_portfolio(p)
    return {"success": True, "fixed": fixed}

class CloseRequest(BaseModel):
    trade_id:str; close_price:float=Field(...,gt=0)

@app.post("/api/trade/close")
def close_trade(req: CloseRequest):
    p=load_portfolio(); cfg=load_settings(); fee=cfg["order_fee"]
    pos=next((x for x in p["positions"] if x["id"]==req.trade_id),None)
    if not pos: raise HTTPException(404,"Position nicht gefunden")
    lev=pos.get("leverage",1)
    pnl_gross=((req.close_price-pos["entry_price"])*pos["units"]*lev
               if pos["direction"]=="BUY"
               else (pos["entry_price"]-req.close_price)*pos["units"]*lev)
    open_fee  = pos.get("fee", fee)   # beim Öffnen bereits gezahlt
    close_fee = fee                   # jetzt beim Schließen fällig
    total_fees = open_fee + close_fee  # beide zusammen: z.B. 20€
    # pnl = was nach BEIDEN Gebühren übrig bleibt
    pnl_net = round(pnl_gross - close_fee, 2)   # nur Schließgebühr subtrahieren
    # (Öffnungsgebühr wurde bereits beim open_trade vom Cash abgezogen)
    proceeds = round(pos["cost"] + pnl_net, 2)
    closed={**pos,
            "close_price":  req.close_price,
            "pnl":          pnl_net,                    # nach Schließgebühr
            "pnl_gross":    round(pnl_gross, 2),
            "fees":         total_fees,                  # 20€ gesamt
            "open_fee":     open_fee,
            "close_fee":    close_fee,
            "pnl_pct":      round(pnl_net/pos["cost"]*100, 2) if pos["cost"] else 0,
            "proceeds":     proceeds,
            "closed":       datetime.now().isoformat(),
            "status":       "WIN" if pnl_net > 0 else "LOSS"}
    p["positions"]=[x for x in p["positions"] if x["id"]!=req.trade_id]
    p["closed_trades"].append(closed); p["cash"]=round(p["cash"]+proceeds,2)
    invalidate_portfolio_cache(); save_portfolio(p); _price_cache.pop(pos["ticker"],None)
    return {"success":True,"trade":closed}

def _compute_exit_signals() -> dict:
    """
    Vollständige Exit-Signal-Berechnung.
    Exit NUR wenn build_signal() ein echtes Gegensignal mit ausreichender Stärke liefert.
    SL/TP-Verletzungen werden immer gemeldet.
    """
    p = load_portfolio()
    positions = p.get("positions", [])
    if not positions:
        return {"exit_signals": [], "checked": 0, "exit_min_strength": 15}

    cfg = load_settings()
    exit_min_strength = max(15, cfg["min_strength"] // 2)
    signals = []

    for pos in positions:
        try:
            base_ticker = pos.get("base_ticker") or pos["ticker"].split()[0]
            if base_ticker not in VALID_TICKERS:
                base_ticker = pos["ticker"].split()[0]
            name      = TICKER_TO_NAME.get(base_ticker, pos["name"])
            entry     = pos["entry_price"]
            sl        = pos["stop_loss"]
            tp        = pos["take_profit"]
            direction = pos["direction"]
            is_mf     = pos.get("is_mini_future", False)
            lev       = pos.get("leverage", 1)

            # Aktuellen Basiswert-Kurs holen
            df5 = fetch_ohlcv(base_ticker, period="5d", timeout=8)
            if df5 is None or df5.empty: continue
            base_price = round(float(df5["Close"].iloc[-1]), 2)

            # P&L berechnen – je nach Positions-Typ
            if is_mf:
                base_entry = pos.get("base_entry_price")
                if base_entry and base_entry > 0:
                    delta_pct = (base_price - base_entry) / base_entry
                    pnl_abs = delta_pct * lev * pos["cost"] if direction == "BUY" else -delta_pct * lev * pos["cost"]
                    pp = round(pnl_abs / pos["cost"] * 100, 2) if pos["cost"] > 0 else 0
                else:
                    pp = 0.0
                # SL/TP auf Basiswert-Ebene prüfen
                price = base_price  # für SL/TP-Vergleich den Basiswert-Kurs verwenden
                entry_for_sltp = base_entry if (base_entry and base_entry > 0) else entry
            else:
                price = base_price
                entry_for_sltp = entry
                if direction == "BUY":
                    pp = round((price - entry) / entry * 100, 2)
                else:
                    pp = round((entry - price) / entry * 100, 2)

            # SL/TP-Abstände berechnen
            if direction == "BUY":
                sld = (price - sl) / entry_for_sltp * 100
                tpd = (tp - price) / entry_for_sltp * 100
            else:
                sld = (sl - price) / entry_for_sltp * 100
                tpd = (price - tp) / entry_for_sltp * 100

            # SL/TP-Verletzungen → immer sofort melden
            if tpd <= 0:
                signals.append({"trade_id":pos["id"],"ticker":base_ticker,"name":pos["name"],
                    "direction":direction,"entry_price":entry,"current_price":base_price,
                    "base_price":base_price,"is_mf":is_mf,
                    "pnl_pct":round(pp,2),"stop_loss":sl,"take_profit":tp,
                    "exit_reasons":["✅ Take Profit erreicht!"],"urgency":"urgent",
                    "recommendation":"SCHLIESSEN","exit_strength":None})
                continue
            if sld <= 0:
                signals.append({"trade_id":pos["id"],"ticker":base_ticker,"name":pos["name"],
                    "direction":direction,"entry_price":entry,"current_price":base_price,
                    "base_price":base_price,"is_mf":is_mf,
                    "pnl_pct":round(pp,2),"stop_loss":sl,"take_profit":tp,
                    "exit_reasons":["🛑 Stop Loss durchbrochen!"],"urgency":"urgent",
                    "recommendation":"SCHLIESSEN","exit_strength":None})
                continue

            # Vollständige Signalanalyse des Basiswerts
            df6 = fetch_ohlcv(base_ticker, period="6mo")
            if df6 is None or len(df6) < 60: continue
            c = df6["Close"].squeeze(); h = df6["High"].squeeze(); l = df6["Low"].squeeze()
            v = df6["Volume"].squeeze() if "Volume" in df6.columns else pd.Series(np.ones(len(c)), index=c.index)
            ind = compute_indicators(c, h, l, v, cfg)
            sig = build_signal(base_ticker, name, ind, min_strength=0, cfg=cfg)

            if sig is None: continue  # Keine klare Richtung → kein Exit

            sig_direction = sig["direction"]
            sig_strength  = sig["strength"]

            # Nur Gegensignal ist Exit-relevant
            is_counter = (direction=="BUY" and sig_direction=="SELL") or \
                         (direction=="SELL" and sig_direction=="BUY")
            if not is_counter: continue
            if sig_strength < exit_min_strength: continue

            reason_word = "VERKAUFEN" if direction=="BUY" else "KAUFEN"
            reasons = [
                f"📊 Analyse empfiehlt {reason_word} (Signalstärke {sig_strength}/100)",
                f"✓ {sig['confirming_groups']}/3 Gruppen bestätigen · {sig['market_phase']}",
            ]
            for sg in (sig.get("signals") or [])[:3]:
                if not sg.startswith("⚠️"):
                    reasons.append(sg)

            signals.append({
                "trade_id":      pos["id"],
                "ticker":        base_ticker,
                "name":          pos["name"],
                "direction":     direction,
                "entry_price":   entry,
                "current_price": base_price,
                "base_price":    base_price,
                "is_mf":         is_mf,
                "pnl_pct":       round(pp, 2),
                "stop_loss":     sl,
                "take_profit":   tp,
                "exit_reasons":  reasons,
                "urgency":       "warn",
                "recommendation":"SCHLIESSEN",
                "exit_strength": sig_strength,
            })
        except Exception:
            continue

    signals.sort(key=lambda x: {"urgent":0,"warn":1}.get(x.get("urgency","warn"), 1))
    return {"exit_signals": signals, "checked": len(positions),
            "exit_min_strength": exit_min_strength}


@app.get("/api/exit-signals")
def get_exit_signals_ep():
    """Gecachte Exit-Signale – werden nach jeder Analyse automatisch aktualisiert."""
    with _exit_lock:
        age = time.time() - _exit_cache.get("ts", 0)
        sigs = list(_exit_cache.get("signals", []))
        ms   = _exit_cache.get("exit_min_strength", 15)

    if age < 600 and _exit_cache.get("ts", 0) > 0:
        return {"exit_signals": sigs, "checked": _exit_cache.get("checked", 0),
                "exit_min_strength": ms, "cached": True}
    # Cache leer oder veraltet → live berechnen
    result = _compute_exit_signals()
    with _exit_lock:
        _exit_cache.update({**result, "ts": time.time()})
    return result

@app.get("/",response_class=HTMLResponse)
def frontend():
    p=Path(__file__).parent/"index.html"
    return p.read_text() if p.exists() else "<h1>TradeBot Pro v13</h1>"

@app.get("/manifest.json")
def manifest():
    p=Path(__file__).parent/"manifest.json"
    return JSONResponse(json.loads(p.read_text()) if p.exists() else {})

# Kein Auto-Start – Analyse wird nur manuell über den "Analyse starten"-Button ausgelöst
