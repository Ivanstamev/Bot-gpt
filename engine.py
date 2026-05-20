"""
engine.py — NEXUS BOT PRO
Stable TradingBot + BacktestEngine
"""

from __future__ import annotations

import os
import logging

import pandas as pd

from risk_management import RiskManager, RiskConfig
from strategy_manager import StrategyManager
from logic import AIBrain

logger = logging.getLogger(__name__)


# ============================================================
# STRATEGY DEFAULTS
# ============================================================

STRATEGY_RISK_DEFAULTS = {

    "Scalp Fast": {
        "risk_pct": 3.0,
        "leverage": 15,
    },

    "Trend Pro": {
        "risk_pct": 2.0,
        "leverage": 10,
    },

    "Safe Mode": {
        "risk_pct": 1.0,
        "leverage": 5,
    }
}


# ============================================================
# BOT CONFIG
# ============================================================

class BotConfig:

    def __init__(self):

        self.exchange_id = os.getenv(
            "DEFAULT_EXCHANGE",
            "mexc"
        )

        self.symbol = os.getenv(
            "DEFAULT_SYMBOL",
            "BTC/USDT"
        )

        self.mode = os.getenv(
            "DEFAULT_MODE",
            "futures"
        )

        self.leverage = int(
            os.getenv(
                "DEFAULT_LEVERAGE",
                10
            )
        )

        self.timeframe = "15m"

        self.demo_mode = True

        self.demo_balance = 1000.0

        self.use_ai = False


# ============================================================
# EXCHANGE CONNECTOR
# ============================================================

class ExchangeConnector:

    def __init__(
        self,
        exchange_id="mexc",
        mode="futures"
    ):

        self.exchange_id = exchange_id
        self.mode = mode

        self._ex = None

    # --------------------------------------------------------

    def connect(
        self,
        api_key="",
        api_secret=""
    ):

        try:

            import ccxt

            cls_map = {
                "mexc": ccxt.mexc,
                "bingx": ccxt.bingx,
            }

            cls = cls_map.get(
                self.exchange_id.lower()
            )

            if not cls:
                return False

            self._ex = cls({

                "apiKey": api_key,

                "secret": api_secret,

                "enableRateLimit": True,

                "options": {
                    "defaultType": "swap"
                }
            })

            self._ex.load_markets()

            return True

        except Exception as e:

            logger.error(
                f"Exchange error: {e}"
            )

            return False

    # --------------------------------------------------------

    def get_ohlcv(
        self,
        symbol,
        timeframe="15m",
        limit=200
    ):

        if not self._ex:
            return None

        try:

            data = self._ex.fetch_ohlcv(
                symbol,
                timeframe,
                limit=limit
            )

            df = pd.DataFrame(
                data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume"
                ]
            )

            return df

        except Exception as e:

            logger.error(
                f"OHLCV error: {e}"
            )

            return None

    # --------------------------------------------------------

    @property
    def connected(self):

        return self._ex is not None


# ============================================================
# BACKTEST ENGINE
# ============================================================

class BacktestEngine:

    def __init__(
        self,
        strategy_manager,
        risk_manager
    ):

        self.sm = strategy_manager
        self.rm = risk_manager

    # --------------------------------------------------------

    def run(
        self,
        df,
        initial_bal=1000.0
    ):

        if df is None or len(df) < 20:

            return {
                "error": "No data"
            }

        return {

            "trades": [],

            "final_balance": initial_bal,

            "return_pct": 0
        }


# ============================================================
# TRADING BOT
# ============================================================

class TradingBot:

    def __init__(
        self,
        config=None
    ):

        self.cfg = config or BotConfig()

        self.strategy = StrategyManager()

        self.risk = RiskManager(
            RiskConfig(
                leverage=self.cfg.leverage
            )
        )

        self.brain = AIBrain(
            use_ai=self.cfg.use_ai
        )

        self.exchange = ExchangeConnector(
            self.cfg.exchange_id,
            self.cfg.mode
        )

        self.backtest = BacktestEngine(
            self.strategy,
            self.risk
        )

        self._latest_signal = {}

    # --------------------------------------------------------

    def setup(
        self,
        api_key="",
        api_secret=""
    ):

        return self.exchange.connect(
            api_key,
            api_secret
        )

    # --------------------------------------------------------

    def tick(self):

        df = self.exchange.get_ohlcv(
            self.cfg.symbol,
            self.cfg.timeframe,
            200
        )

        if df is None:

            return {
                "error": "No market data"
            }

        df = self.strategy.compute(df)

        sig = self.strategy.signal(df)

        self._latest_signal = sig

        return sig

    # --------------------------------------------------------

    def run_backtest(
        self,
        days=7
    ):

        df = self.exchange.get_ohlcv(
            self.cfg.symbol,
            self.cfg.timeframe,
            limit=days * 96
        )

        return self.backtest.run(df)

    # --------------------------------------------------------

    @property
    def connected(self):

        return self.exchange.connected
