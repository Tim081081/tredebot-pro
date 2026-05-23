"""
Paper Trading Engine
Manages virtual portfolio: open/close positions, track P&L, history
"""

import json
import os
from datetime import datetime
from typing import Optional

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "../data/portfolio.json")


def _load() -> dict:
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    return {
        "cash": 10000.0,
        "start_capital": 10000.0,
        "positions": [],
        "closed_trades": [],
        "created": datetime.now().isoformat(),
    }


def _save(portfolio: dict):
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)


def get_portfolio() -> dict:
    p = _load()
    # Calculate open P&L
    for pos in p["positions"]:
        # Will be updated with live price when fetched
        pass
    return p


def open_trade(
    ticker: str,
    name: str,
    direction: str,        # "BUY" or "SELL"
    price: float,
    stop_loss: float,
    take_profit: float,
    score: int,
    signals: list,
    leverage: int = 1,
    risk_pct: float = 5.0,  # risk x% of portfolio per trade
) -> dict:
    p = _load()
    portfolio_value = p["cash"] + sum(
        pos.get("current_value", pos["entry_price"] * pos["units"]) for pos in p["positions"]
    )

    # Position sizing: risk_pct of portfolio / distance to stop loss
    distance = abs(price - stop_loss)
    if distance == 0:
        return {"error": "Stop loss identisch mit Einstiegspreis"}

    risk_amount = portfolio_value * (risk_pct / 100)
    units = round(risk_amount / distance, 4)
    cost = round(price * units / leverage, 2)

    if cost > p["cash"]:
        return {"error": f"Nicht genug Cash. Verfügbar: {p['cash']:.2f}€, benötigt: {cost:.2f}€"}

    trade_id = f"T{len(p['closed_trades']) + len(p['positions']) + 1:04d}"
    position = {
        "id": trade_id,
        "ticker": ticker,
        "name": name,
        "direction": direction,
        "entry_price": price,
        "current_price": price,
        "units": units,
        "leverage": leverage,
        "cost": cost,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "score": score,
        "signals": signals,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_pct": 0.0,
        "current_value": cost,
        "opened": datetime.now().isoformat(),
    }

    p["cash"] = round(p["cash"] - cost, 2)
    p["positions"].append(position)
    _save(p)
    return {"success": True, "trade": position}


def close_trade(trade_id: str, close_price: float) -> dict:
    p = _load()
    pos = next((x for x in p["positions"] if x["id"] == trade_id), None)
    if not pos:
        return {"error": f"Position {trade_id} nicht gefunden"}

    entry = pos["entry_price"]
    units = pos["units"]
    leverage = pos.get("leverage", 1)
    cost = pos["cost"]

    if pos["direction"] == "BUY":
        pnl = (close_price - entry) * units * leverage
    else:
        pnl = (entry - close_price) * units * leverage

    pnl_pct = round(pnl / cost * 100, 2)
    proceeds = round(cost + pnl, 2)

    closed = {
        **pos,
        "close_price": close_price,
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
        "proceeds": proceeds,
        "closed": datetime.now().isoformat(),
        "status": "WIN" if pnl > 0 else "LOSS",
    }

    p["positions"] = [x for x in p["positions"] if x["id"] != trade_id]
    p["closed_trades"].append(closed)
    p["cash"] = round(p["cash"] + proceeds, 2)
    _save(p)
    return {"success": True, "trade": closed}


def update_prices(price_map: dict) -> dict:
    """Update open positions with latest prices."""
    p = _load()
    for pos in p["positions"]:
        ticker = pos["ticker"]
        if ticker in price_map:
            cp = price_map[ticker]
            pos["current_price"] = cp
            units = pos["units"]
            leverage = pos.get("leverage", 1)
            cost = pos["cost"]
            entry = pos["entry_price"]
            if pos["direction"] == "BUY":
                pnl = (cp - entry) * units * leverage
            else:
                pnl = (entry - cp) * units * leverage
            pos["unrealized_pnl"] = round(pnl, 2)
            pos["unrealized_pnl_pct"] = round(pnl / cost * 100, 2)
            pos["current_value"] = round(cost + pnl, 2)
    _save(p)
    return p


def get_stats(p: Optional[dict] = None) -> dict:
    if p is None:
        p = _load()
    closed = p["closed_trades"]
    open_value = sum(pos.get("current_value", pos["cost"]) for pos in p["positions"])
    total_value = round(p["cash"] + open_value, 2)
    total_pnl = round(total_value - p["start_capital"], 2)
    total_pnl_pct = round(total_pnl / p["start_capital"] * 100, 2)

    wins = [t for t in closed if t.get("status") == "WIN"]
    losses = [t for t in closed if t.get("status") == "LOSS"]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
    avg_win = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0

    return {
        "start_capital": p["start_capital"],
        "total_value": total_value,
        "cash": p["cash"],
        "open_value": round(open_value, 2),
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "total_trades": len(closed),
        "open_positions": len(p["positions"]),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }
