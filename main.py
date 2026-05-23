"""
FastAPI Backend Server
REST API for the Trading Bot frontend
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from analyzer import run_analysis
from paper_trading import (
    get_portfolio, open_trade, close_trade,
    update_prices, get_stats
)
from notifications import send_signal_email
import yfinance as yf

app = FastAPI(title="Trading Bot API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE_FILE = Path(__file__).parent.parent / "data" / "last_analysis.json"
CACHE_FILE.parent.mkdir(exist_ok=True)

# ── Background Analysis Job ─────────────────────────────────────────────────

_last_run: dict = {}


def _load_cache():
    global _last_run
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            _last_run = json.load(f)


def _save_cache(result: dict):
    global _last_run
    _last_run = result
    with open(CACHE_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)


async def run_analysis_job():
    """Run full market scan in background."""
    result = await asyncio.to_thread(run_analysis)
    _save_cache(result)
    # Send email if strong signals found
    if result.get("top_signals"):
        await asyncio.to_thread(send_signal_email, result["top_signals"])
    return result


_load_cache()


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/signals")
async def get_signals(refresh: bool = False, background_tasks: BackgroundTasks = None):
    """Return latest signals. Set refresh=true to trigger new analysis."""
    if refresh:
        result = await run_analysis_job()
        return result
    if _last_run:
        return _last_run
    # First run
    result = await run_analysis_job()
    return result


@app.post("/api/signals/refresh")
async def trigger_refresh():
    """Manually trigger a new market scan."""
    result = await run_analysis_job()
    return result


@app.get("/api/portfolio")
def get_portfolio_endpoint():
    p = get_portfolio()
    stats = get_stats(p)
    return {"portfolio": p, "stats": stats}


class TradeRequest(BaseModel):
    ticker: str
    name: str
    direction: str
    price: float
    stop_loss: float
    take_profit: float
    score: int
    signals: list
    leverage: int = 1


@app.post("/api/trade/open")
def open_trade_endpoint(req: TradeRequest):
    result = open_trade(
        ticker=req.ticker,
        name=req.name,
        direction=req.direction,
        price=req.price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        score=req.score,
        signals=req.signals,
        leverage=req.leverage,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class CloseRequest(BaseModel):
    trade_id: str
    close_price: float


@app.post("/api/trade/close")
def close_trade_endpoint(req: CloseRequest):
    result = close_trade(req.trade_id, req.close_price)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/price/{ticker}")
async def get_price(ticker: str):
    """Fetch latest price for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist.empty:
            raise HTTPException(status_code=404, detail="Ticker nicht gefunden")
        price = float(hist["Close"].iloc[-1])
        return {"ticker": ticker, "price": round(price, 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chart/{ticker}")
async def get_chart_data(ticker: str, period: str = "3mo"):
    """Return OHLCV data for charting."""
    try:
        df = await asyncio.to_thread(
            yf.download, ticker, period=period, interval="1d",
            progress=False, auto_adjust=True
        )
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="Keine Daten")
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        records = []
        for idx, row in df.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })
        return {"ticker": ticker, "period": period, "data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Serve Frontend ───────────────────────────────────────────────────────────

frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(frontend_path / "index.html"))

    @app.get("/{path:path}")
    def catch_all(path: str):
        fp = frontend_path / path
        if fp.exists():
            return FileResponse(str(fp))
        return FileResponse(str(frontend_path / "index.html"))
