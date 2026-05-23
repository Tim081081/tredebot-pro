"""
Trading Signal Analyzer
Fetches market data, calculates technical indicators, generates buy/sell signals
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── European Indices & their top components ──────────────────────────────────
WATCHLIST = {
    "DAX":        "^GDAXI",
    "Euro Stoxx 50": "^STOXX50E",
    "FTSE 100":   "^FTSE",
    "CAC 40":     "^FCHI",
    "IBEX 35":    "^IBEX",
    "AEX":        "^AEX",
    "SMI":        "^SSMI",
    "ATX":        "^ATX",
}

# Top DAX & EuroStoxx single stocks (Yahoo Finance tickers)
SINGLE_STOCKS = [
    "SAP.DE","SIE.DE","ALV.DE","MUV2.DE","DTE.DE","BAYN.DE","BMW.DE","MBG.DE",
    "ASML.AS","MC.PA","TTE.FP","SAN.MC","NESN.SW","ROG.SW","NOVN.SW",
    "AZN.L","HSBA.L","BP.L","SHEL.L","RIO.L","GSK.L","ULVR.L",
    "AIR.PA","BNP.PA","SU.PA","OR.PA","KER.PA",
    "ENEL.MI","ENI.MI","ISP.MI","UCG.MI",
]


def fetch_data(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    """Download OHLCV data for a ticker."""
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 30:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.warning(f"Could not fetch {ticker}: {e}")
        return None


# ── Technical Indicators ─────────────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist


def calc_bollinger(close: pd.Series, period: int = 20):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    pct_b = (close - lower) / (upper - lower)
    return upper, sma, lower, pct_b


def calc_stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_adx(high, low, close, period=14):
    """Average Directional Index"""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = calc_atr(high, low, close, period)
    plus_di = 100 * pd.Series(plus_dm, index=close.index).rolling(period).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=close.index).rolling(period).mean() / tr
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di


def calc_ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"]
    return (tp * vol).cumsum() / vol.cumsum()


# ── Signal Scoring ────────────────────────────────────────────────────────────

def score_ticker(df: pd.DataFrame, name: str, ticker: str) -> dict | None:
    """
    Returns a signal dict with score -100..+100.
    Positive = bullish (BUY), Negative = bearish (SELL).
    Only returns a result if |score| >= 60 (strong signal).
    """
    try:
        c = df["Close"].squeeze()
        h = df["High"].squeeze()
        l = df["Low"].squeeze()
        v = df["Volume"].squeeze() if "Volume" in df.columns else None

        # ── Indicators ────────────────────────────────────────────────────
        rsi = calc_rsi(c)
        macd_line, macd_sig, macd_hist = calc_macd(c)
        bb_upper, bb_mid, bb_lower, pct_b = calc_bollinger(c)
        stoch_k, stoch_d = calc_stochastic(h, l, c)
        ema20 = calc_ema(c, 20)
        ema50 = calc_ema(c, 50)
        ema200 = calc_ema(c, 200)
        adx, plus_di, minus_di = calc_adx(h, l, c)
        atr = calc_atr(h, l, c)

        # Latest values
        r = rsi.iloc[-1]
        mk = macd_line.iloc[-1]
        ms = macd_sig.iloc[-1]
        mh = macd_hist.iloc[-1]
        mh_prev = macd_hist.iloc[-2]
        pb = pct_b.iloc[-1]
        sk = stoch_k.iloc[-1]
        sd = stoch_d.iloc[-1]
        price = c.iloc[-1]
        e20 = ema20.iloc[-1]
        e50 = ema50.iloc[-1]
        e200 = ema200.iloc[-1] if len(c) >= 200 else None
        adx_val = adx.iloc[-1]
        plus = plus_di.iloc[-1]
        minus_d = minus_di.iloc[-1]
        atr_val = atr.iloc[-1]
        price_prev = c.iloc[-2]

        # ── Scoring ───────────────────────────────────────────────────────
        score = 0
        signals = []

        # RSI
        if r < 30:
            score += 20
            signals.append(f"RSI überverkauft ({r:.1f})")
        elif r < 40:
            score += 10
            signals.append(f"RSI schwach ({r:.1f})")
        elif r > 70:
            score -= 20
            signals.append(f"RSI überkauft ({r:.1f})")
        elif r > 60:
            score -= 10
            signals.append(f"RSI stark ({r:.1f})")

        # MACD crossover
        if mk > ms and mh > 0 and mh > mh_prev:
            score += 20
            signals.append("MACD bullisches Crossover")
        elif mk < ms and mh < 0 and mh < mh_prev:
            score -= 20
            signals.append("MACD bärisches Crossover")
        elif mk > ms:
            score += 10
            signals.append("MACD positiv")
        elif mk < ms:
            score -= 10
            signals.append("MACD negativ")

        # Bollinger Bands
        if pb < 0.05:
            score += 20
            signals.append("Preis an unterem Bollinger Band")
        elif pb < 0.2:
            score += 10
            signals.append("Preis nahe unterem Bollinger Band")
        elif pb > 0.95:
            score -= 20
            signals.append("Preis an oberem Bollinger Band")
        elif pb > 0.8:
            score -= 10
            signals.append("Preis nahe oberem Bollinger Band")

        # Stochastic
        if sk < 20 and sd < 20 and sk > sd:
            score += 15
            signals.append(f"Stochastik überverkauft & dreht ({sk:.1f})")
        elif sk > 80 and sd > 80 and sk < sd:
            score -= 15
            signals.append(f"Stochastik überkauft & dreht ({sk:.1f})")

        # EMA Trend
        if price > e20 > e50:
            score += 10
            signals.append("Preis > EMA20 > EMA50 (Auftrend)")
        elif price < e20 < e50:
            score -= 10
            signals.append("Preis < EMA20 < EMA50 (Abtrend)")
        if e200 is not None:
            if price > e200:
                score += 5
                signals.append("Über EMA200")
            else:
                score -= 5
                signals.append("Unter EMA200")

        # ADX Trend Strength
        if adx_val > 25:
            if plus > minus_d:
                score += 10
                signals.append(f"ADX starker Auftrend ({adx_val:.1f})")
            else:
                score -= 10
                signals.append(f"ADX starker Abtrend ({adx_val:.1f})")

        # ── Filter: only strong signals ───────────────────────────────────
        if abs(score) < 60:
            return None

        direction = "BUY" if score > 0 else "SELL"

        # Risk/Reward
        atr_multiplier = 1.5
        if direction == "BUY":
            stop_loss = round(price - atr_multiplier * atr_val, 2)
            take_profit = round(price + 2 * atr_multiplier * atr_val, 2)
        else:
            stop_loss = round(price + atr_multiplier * atr_val, 2)
            take_profit = round(price - 2 * atr_multiplier * atr_val, 2)

        change_1d = round((price / price_prev - 1) * 100, 2) if price_prev else 0

        return {
            "ticker": ticker,
            "name": name,
            "price": round(float(price), 2),
            "change_1d": change_1d,
            "direction": direction,
            "score": int(score),
            "strength": min(100, abs(int(score))),
            "signals": signals,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rsi": round(float(r), 1),
            "macd": round(float(mk), 4),
            "atr": round(float(atr_val), 2),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.warning(f"Score error for {ticker}: {e}")
        return None


def run_analysis() -> dict:
    """
    Full market scan. Returns top signals sorted by strength.
    """
    results = []
    all_tickers = list(WATCHLIST.items()) + [(t, t) for t in SINGLE_STOCKS]

    for name, ticker in all_tickers:
        logger.info(f"Analysiere {name} ({ticker})...")
        df = fetch_data(ticker)
        if df is None:
            continue
        sig = score_ticker(df, name, ticker)
        if sig:
            results.append(sig)

    # Sort by strength descending
    results.sort(key=lambda x: x["strength"], reverse=True)

    # Keep only top signals (max 5 per run to avoid overtrading)
    top = results[:5]

    return {
        "timestamp": datetime.now().isoformat(),
        "total_analyzed": len(all_tickers),
        "signals_found": len(results),
        "top_signals": top,
    }


if __name__ == "__main__":
    result = run_analysis()
    print(json.dumps(result, indent=2, ensure_ascii=False))
