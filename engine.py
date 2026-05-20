"""
engine.py — NEXUS BOT PRO (CLEAN VERSION)
Stable TradingBot + BacktestEngine
"""
from __future__ import annotations

import os
import math
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from risk_management import RiskManager, RiskConfig
from strategy_manager import StrategyManager
from logic import AIBrain

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

class BotConfig:
    def __init__(self):
        self.exchange_id: str = os.getenv("DEFAULT_EXCHANGE", "mexc")
        self.symbol: str = os.getenv("DEFAULT_SYMBOL", "BTC/USDT")
        self.mode: str = os.getenv("DEFAULT_MODE", "futures")
        self.leverage: int = int(os.getenv("DEFAULT_LEVERAGE", 10))
        self.timeframe: str = "15m"

        self.demo_mode: bool = True
        self.demo_balance: float = 1000.0
        self.use_ai: bool = False


# ─────────────────────────────────────────────
# EXCHANGE CONNECTOR
# ─────────────────────────────────────────────

class ExchangeConnector:
    def __init__(self, exchange_id="mexc", mode="futures"):
        self.exchange_id = exchange_id
        self.mode = mode
        self._ex = None

    def connect(self, api_key="", api_secret="") -> bool:
        try:
            import ccxt

            cls_map = {
                "mexc": ccxt.mexc,
                "bingx": ccxt.bingx,
            }

            cls = cls_map.get(self.exchange_id.lower())
            if not cls:
                return False

            self._ex = cls({
                "apiKey": api_key or os.getenv(f"{self.exchange_id.upper()}_API_KEY", ""),
                "secret": api_secret or os.getenv(f"{self.exchange_id.upper()}_API_SECRET", ""),
                "enableRateLimit": True,
                "options": {"defaultType": "swap"} if self.mode == "futures" else {},
            })

            self._ex.load_markets()
            return True

        except Exception as e:
            logger.error(f"Exchange connect error: {e}")
            return False

    def get_ohlcv(self, symbol, timeframe="1h", limit=200):
        if not self._ex:
            return None
        try:
            data = self._ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df.astype(float)
        except Exception as e:
            logger.error(f"OHLCV error: {e}")
            return None

    def set_leverage(self, symbol, leverage):
        try:
            if self._ex:
                self._ex.set_leverage(leverage, symbol)
        except Exception as e:
            logger.error(f"Leverage error: {e}")

    @property
    def connected(self):
        return self._ex is not None


# ─────────────────────────────────────────────
# DEMO ACCOUNT
# ─────────────────────────────────────────────

class DemoAccount:
    def __init__(self, balance=1000.0):
        self.initial = balance
        self.balance = balance
        self.position = None
        self.trades = []

    def reset(self, balance):
        self.__init__(balance)

    def open_position(self, direction, entry, qty, tp, sl, strategy):
        self.position = {
            "direction": direction,
            "entry": entry,
            "qty": qty,
            "tp": tp,
            "sl": sl,
            "strategy": strategy,
            "opened_at": datetime.utcnow().isoformat(),
            "margin": entry * qty,
        }

    def update_position(self, price):
        if not self.position:
            return None

        p = self.position

        hit_tp = (p["direction"] == "LONG" and price >= p["tp"]) or \
                 (p["direction"] == "SHORT" and price <= p["tp"])

        hit_sl = (p["direction"] == "LONG" and price <= p["sl"]) or \
                 (p["direction"] == "SHORT" and price >= p["sl"])

        if hit_tp:
            return self._close(price, "TP")
        if hit_sl:
            return self._close(price, "SL")

        return None

    def _close(self, price, reason):
        p = self.position

        if p["direction"] == "LONG":
            pnl_pct = (price - p["entry"]) / p["entry"] * 100
        else:
            pnl_pct = (p["entry"] - price) / p["entry"] * 100

        pnl = pnl_pct / 100 * p["margin"]
        self.balance += pnl

        trade = {
            **p,
            "exit": price,
            "reason": reason,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 3),
            "balance": round(self.balance, 2),
            "closed_at": datetime.utcnow().isoformat(),
        }

        self.trades.append(trade)
        self.position = None
        return trade

    @property
    def pnl(self):
        return round(self.balance - self.initial, 2)


# ─────────────────────────────────────────────
# BACKTEST ENGINE
# ─────────────────────────────────────────────

class BacktestEngine:
    def __init__(self, strategy_manager: StrategyManager, risk_manager: RiskManager):
        self.sm = strategy_manager
        self.rm = risk_manager

    def run(self, df: pd.DataFrame, initial_bal=1000.0) -> dict:
        if df is None or len(df) < 60:
            return {"error": "Not enough data"}

        df = df.copy()

        try:
            df = self.sm.compute(df)
        except Exception as e:
            return {"error": f"Strategy compute error: {e}"}

        balance = initial_bal
        trades = []
        position = None
        equity = [balance]

        for i in range(30, len(df)):
            row = df.iloc[i]
            price = float(row["close"])

            try:
                sig = self.sm.signal(df.iloc[:i])
            except:
                continue

            if position:
                if (position["dir"] == "LONG" and price >= position["tp"]) or \
                   (position["dir"] == "SHORT" and price <= position["tp"]) or \
                   (position["dir"] == "LONG" and price <= position["sl"]) or \
                   (position["dir"] == "SHORT" and price >= position["sl"]):

                    pnl = (price - position["entry"]) / position["entry"] * 100
                    if position["dir"] == "SHORT":
                        pnl = -pnl

                    cash = pnl / 100 * position["margin"]
                    balance += cash

                    trades.append({
                        **position,
                        "exit": price,
                        "pnl": round(cash, 2),
                        "balance": round(balance, 2),
                    })

                    equity.append(balance)
                    position = None

            if not position and sig.get("signal") in ("LONG", "SHORT"):
                price = float(row["close"])

                tp = price * 1.02
                sl = price * 0.01

                position = {
                    "dir": sig["signal"],
                    "entry": price,
                    "tp": tp,
                    "sl": sl,
                    "margin": balance * 0.1,
                }

        return {
            "trades": trades,
            "final_balance": balance,
            "return_pct": round((balance - initial_bal) / initial_bal * 100, 2),
        }


# ─────────────────────────────────────────────
# TRADING BOT
# ─────────────────────────────────────────────

class TradingBot:
    def __init__(self, config: Optional[BotConfig] = None):
        self.cfg = config or BotConfig()

        self.strategy = StrategyManager()
        self.risk = RiskManager(RiskConfig(leverage=self.cfg.leverage))
        self.brain = AIBrain(use_ai=self.cfg.use_ai)

        self.exchange = ExchangeConnector(self.cfg.exchange_id, self.cfg.mode)
        self.demo = DemoAccount(self.cfg.demo_balance)

        self.backtest = BacktestEngine(self.strategy, self.risk)

        self._latest_signal = {}

    def setup(self, api_key="", api_secret=""):
        ok = self.exchange.connect(api_key, api_secret)

        if ok and self.cfg.mode == "futures":
            self.exchange.set_leverage(self.cfg.symbol, self.cfg.leverage)

        return ok

    def tick(self):
        df = self.exchange.get_ohlcv(self.cfg.symbol, self.cfg.timeframe, 200)

        if df is None or len(df) < 50:
            return {"error": "No data"}

        df = self.strategy.compute(df)
        sig = self.strategy.signal(df)

        price = float(df["close"].iloc[-1])

        if self.demo.position:
            closed = self.demo.update_position(price)
            if closed:
                self.risk.close_position(closed["pnl"])

        if sig.get("signal") in ("LONG", "SHORT") and not self.demo.position:
            self.demo.open_position(
                sig["signal"],
                price,
                qty=1,
                tp=price * 1.02,
                sl=price * 0.99,
                strategy=self.strategy._active_name,
            )

        self._latest_signal = {
            "signal": sig,
            "price": price,
            "balance": self.demo.balance,
            "pnl": self.demo.pnl,
        }

        return self._latest_signal

    def run_backtest(self, days=7):
        df = self.exchange.get_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=days * 96)

        if df is None:
            return {"error": "No data"}

        return self.backtest.run(df, self.demo.initial)

    @property
    def connected(self):
        return self.exchange.connected
