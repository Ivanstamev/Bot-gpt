"""
engine.py — NEXUS BOT PRO
TradingBot + BacktestEngine с реални данни и маркиране на сделки
"""
from __future__ import annotations
import logging, os, time, math
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np

from risk_management  import RiskManager, RiskConfig
from strategy_manager import StrategyManager
from logic            import AIBrain

logger = logging.getLogger(__name__)


class BotConfig:
    def __init__(self):
        self.exchange_id:  str   = os.getenv("DEFAULT_EXCHANGE", "mexc")
        self.symbol:       str   = os.getenv("DEFAULT_SYMBOL",   "BTC/USDT")
        self.mode:         str   = os.getenv("DEFAULT_MODE",     "futures")
        self.leverage:     int   = int(os.getenv("DEFAULT_LEVERAGE", 10))
        self.timeframe:    str   = "15m"
        self.demo_mode:    bool  = True
        self.demo_balance: float = 1_000.0
        self.use_ai:       bool  = False


class ExchangeConnector:
    def __init__(self, exchange_id="mexc", mode="futures"):
        self.exchange_id = exchange_id
        self.mode        = mode
        self._ex         = None

    def connect(self, api_key="", api_secret="") -> bool:
        try:
            import ccxt
            cls_map = {"mexc": ccxt.mexc, "bingx": ccxt.bingx}
            cls = cls_map.get(self.exchange_id.lower())
            if cls is None: return False
            params = {
                "apiKey": api_key or os.getenv(f"{self.exchange_id.upper()}_API_KEY", ""),
                "secret": api_secret or os.getenv(f"{self.exchange_id.upper()}_API_SECRET", ""),
                "options": {},
            }
            if self.mode == "futures":
                params["options"]["defaultType"] = "swap"
            self._ex = cls(params)
            self._ex.load_markets()
            return True
        except Exception as e:
            logger.error(f"Connect error: {e}")
            return False

    def get_ohlcv(self, symbol, timeframe="1h", limit=200) -> Optional[pd.DataFrame]:
        if self._ex is None: return None
        try:
            raw = self._ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            df  = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            df = df.astype(float).dropna()
            return df
        except Exception as e:
            logger.error(f"OHLCV error: {e}")
            return None

    def get_balance(self) -> dict:
        if self._ex is None: return {}
        try: return self._ex.fetch_balance().get("USDT", {})
        except: return {}

    def place_order(self, symbol, side, qty, order_type="market", price=None, params=None):
        if self._ex is None: return None
        try: return self._ex.create_order(symbol, order_type, side, qty, price, params or {})
        except Exception as e:
            logger.error(f"Order error: {e}")
            return None

    def set_leverage(self, symbol, leverage) -> bool:
        if self._ex is None: return False
        try:
            self._ex.set_leverage(leverage, symbol)
            return True
        except: return False

    @property
    def connected(self): return self._ex is not None


class DemoAccount:
    def __init__(self, initial_balance=1_000.0):
        self.initial  = initial_balance
        self.balance  = initial_balance
        self.position: Optional[dict] = None
        self.trades:   list           = []

    def reset(self, new_balance):
        self.__init__(new_balance)

    def open_position(self, direction, entry, qty, tp, sl, strategy):
        self.position = {
            "direction": direction, "entry": entry, "qty": qty,
            "tp": tp, "sl": sl, "strategy": strategy,
            "opened_at": datetime.utcnow().isoformat(),
            "margin": entry * qty,
        }

    def update_position(self, current_price, trailing_stop=None):
        if self.position is None: return None
        p  = self.position
        tp = p["tp"]
        sl = p["sl"] if trailing_stop is None else trailing_stop
        hit_tp = (p["direction"]=="LONG"  and current_price >= tp) or \
                 (p["direction"]=="SHORT" and current_price <= tp)
        hit_sl = (p["direction"]=="LONG"  and current_price <= sl) or \
                 (p["direction"]=="SHORT" and current_price >= sl)
        if hit_tp: return self._close(current_price, "✅ Take-Profit")
        if hit_sl: return self._close(current_price, "⛔ Stop-Loss" if trailing_stop is None else "🔄 Trailing SL")
        return None

    def _close(self, exit_price, reason):
        p = self.position
        if p["direction"] == "LONG":
            pnl_pct = (exit_price - p["entry"]) / p["entry"] * 100
        else:
            pnl_pct = (p["entry"] - exit_price) / p["entry"] * 100
        pnl_usdt = pnl_pct / 100 * p["margin"]
        self.balance += pnl_usdt
        trade = {**p, "exit": exit_price, "exit_reason": reason,
                 "pnl_pct": round(pnl_pct, 3), "pnl_usdt": round(pnl_usdt, 2),
                 "closed_at": datetime.utcnow().isoformat(), "balance": round(self.balance, 2)}
        self.trades.append(trade)
        self.position = None
        return trade

    def force_close(self, current_price):
        if self.position:
            return self._close(current_price, "🖐 Ръчно затваряне")
        return None

    @property
    def pnl(self): return round(self.balance - self.initial, 2)

    @property
    def win_rate(self):
        if not self.trades: return 0.0
        wins = sum(1 for t in self.trades if t["pnl_usdt"] > 0)
        return round(wins / len(self.trades) * 100, 1)

    @property
    def equity_curve(self):
        curve = [{"time": "Старт", "balance": self.initial}]
        running = self.initial
        for t in self.trades:
            running += t["pnl_usdt"]
            curve.append({"time": t.get("closed_at",""), "balance": round(running,2),
                          "trade": f"{t['direction']} {t['exit_reason']} {t['pnl_pct']:+.2f}%"})
        return curve


# Risk defaults per strategy — оптимизирани за удвояване на малки сметки
# R:R минимум 3:1, SL тесен (ATR x0.7), TP широк (ATR x3-5)
STRATEGY_RISK_DEFAULTS = {
    # Цел: 2x за 7-10 дни — агресивен скалп, много сделки
    "Quantum Scalper": {
        "risk_pct": 8.0, "leverage": 25, "use_atr": True,
        "atr_tp_mult": 3.0, "atr_sl_mult": 0.7,
        "tp_pct": 5.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_pct": 0.8,
        "trailing_atr_mult": 1.2, "trailing_activation_pct": 1.0,
        "break_even_enabled": True, "break_even_trigger_pct": 0.8,
        "partial_tp_enabled": False,
        "daily_loss_limit_pct": 20.0, "max_consecutive_losses": 10,
        "max_position_pct": 40.0,
    },
    # Цел: 2x за 10-15 дни — SMC с висок леверидж
    "NEXUS SMC Elite": {
        "risk_pct": 7.0, "leverage": 25, "use_atr": True,
        "atr_tp_mult": 3.5, "atr_sl_mult": 0.8,
        "tp_pct": 6.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 1.5, "trailing_activation_pct": 1.2,
        "break_even_enabled": True, "break_even_trigger_pct": 1.0,
        "partial_tp_enabled": False,
        "daily_loss_limit_pct": 18.0, "max_consecutive_losses": 8,
        "max_position_pct": 40.0,
    },
    # Цел: 2x за 15-20 дни — trend следене
    "Titan Trend": {
        "risk_pct": 5.0, "leverage": 20, "use_atr": True,
        "atr_tp_mult": 4.5, "atr_sl_mult": 1.0,
        "tp_pct": 7.0, "sl_pct": 1.5,
        "trailing_stop": True, "trailing_pct": 1.2,
        "trailing_atr_mult": 2.0, "trailing_activation_pct": 1.5,
        "break_even_enabled": True, "break_even_trigger_pct": 1.2,
        "partial_tp_enabled": False,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 7,
        "max_position_pct": 35.0,
    },
    # Цел: 2x за 20-25 дни — обрати
    "Phoenix Reversal": {
        "risk_pct": 4.5, "leverage": 15, "use_atr": True,
        "atr_tp_mult": 4.0, "atr_sl_mult": 0.9,
        "tp_pct": 6.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 1.8, "trailing_activation_pct": 1.2,
        "break_even_enabled": True, "break_even_trigger_pct": 1.0,
        "partial_tp_enabled": False,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 6,
        "max_position_pct": 35.0,
    },
    # Цел: 2x за 25-30 дни — безопасна
    "Iron Shield": {
        "risk_pct": 3.5, "leverage": 12, "use_atr": True,
        "atr_tp_mult": 4.5, "atr_sl_mult": 1.0,
        "tp_pct": 5.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 2.2, "trailing_activation_pct": 1.5,
        "break_even_enabled": True, "break_even_trigger_pct": 1.2,
        "partial_tp_enabled": False,
        "daily_loss_limit_pct": 12.0, "max_consecutive_losses": 5,
        "max_position_pct": 30.0,
    },
}


# ─────────────────────────────────────────────────────────────
#  BACKTEST ENGINE — реални данни + маркиране на сделки
# ─────────────────────────────────────────────────────────────

class BacktestEngine:
    def __init__(self, strategy_manager: StrategyManager, risk_manager: RiskManager):
        self.sm = strategy_manager
        self.rm = risk_manager

    def run(self, df: pd.DataFrame, initial_bal=1_000.0) -> dict:
        if df is None or len(df) < 60:
            return {"error": "Недостатъчно данни за бектест"}

        try:
            df_ind = self.sm.compute(df.copy())
        except Exception as e:
            return {"error": f"Грешка при индикатори: {e}"}

        if df_ind is None or len(df_ind) < 30:
            return {"error": "Индикаторите не върнаха данни"}

        # Запази реалните timestamp-ове
        if hasattr(df_ind.index, 'to_pydatetime'):
            timestamps = [str(t) for t in df_ind.index]
        else:
            timestamps = [str(i) for i in range(len(df_ind))]

        df_ohlcv = df.copy()  # оригинален df за свещна графика
        df_ind   = df_ind.reset_index(drop=True)
        balance  = initial_bal
        trades   = []
        equity   = [{"time": timestamps[0] if timestamps else "0", "balance": round(initial_bal, 2)}]
        position = None
        min_conf = self.sm.active.min_confidence
        cfg      = self.rm.cfg

        # Взимаме TP/SL multipliers от risk defaults за активната стратегия
        strat_name = self.sm._active_name
        rdef = STRATEGY_RISK_DEFAULTS.get(strat_name, {})
        tp_mult_cfg = rdef.get("atr_tp_mult", cfg.atr_tp_mult)
        sl_mult_cfg = rdef.get("atr_sl_mult", cfg.atr_sl_mult)
        risk_pct_cfg = rdef.get("risk_pct", cfg.risk_pct)
        leverage_cfg = rdef.get("leverage", cfg.leverage)
        max_pos_cfg  = rdef.get("max_position_pct", cfg.max_position_pct)

        for i in range(30, len(df_ind)):
            window = df_ind.iloc[:i].copy()
            row    = df_ind.iloc[i]
            ts     = timestamps[i] if i < len(timestamps) else str(i)

            try:
                price = float(row["close"])
                high  = float(row["high"])
                low   = float(row["low"])
                atr   = float(row["atr"]) if "atr" in df_ind.columns and pd.notna(row.get("atr")) else price * 0.008
            except:
                continue

            # Управление на позиция
            if position is not None:
                dir_   = position["dir"]
                # Break-even: ако цената е достигнала 60% от пътя към TP — местим SL на entry
                be_price = position["entry"] + (position["tp"] - position["entry"]) * 0.6 if dir_=="LONG"                       else position["entry"] - (position["entry"] - position["tp"]) * 0.6
                if dir_=="LONG" and high >= be_price and position["sl"] < position["entry"]:
                    position["sl"] = position["entry"] + price * 0.0005  # SL на entry+spread
                elif dir_=="SHORT" and low <= be_price and position["sl"] > position["entry"]:
                    position["sl"] = position["entry"] - price * 0.0005

                hit_tp = (dir_=="LONG"  and high >= position["tp"]) or                          (dir_=="SHORT" and low  <= position["tp"])
                hit_sl = (dir_=="LONG"  and low  <= position["sl"]) or                          (dir_=="SHORT" and high >= position["sl"])

                if hit_tp or hit_sl:
                    exit_p = position["tp"] if hit_tp else position["sl"]
                    reason = "TP" if hit_tp else "SL"
                    if dir_ == "LONG":
                        pnl_pct = (exit_p - position["entry"]) / position["entry"] * 100
                    else:
                        pnl_pct = (position["entry"] - exit_p) / position["entry"] * 100

                    # Леверидж усилва P&L
                    pnl_usdt = pnl_pct / 100 * position["margin"] * position["leverage"]
                    # Ограничаваме загубата до margin-а
                    pnl_usdt = max(pnl_usdt, -position["margin"])
                    balance  = max(balance + pnl_usdt, 0.01)

                    rr = round(abs(position["tp"]-position["entry"]) / max(abs(position["sl_orig"]-position["entry"]),0.0001), 2)
                    trades.append({
                        "direction": dir_,
                        "entry":     round(position["entry"], 2),
                        "exit":      round(exit_p, 2),
                        "tp":        round(position["tp"], 2),
                        "sl":        round(position["sl_orig"], 2),
                        "pnl_pct":   round(pnl_pct * position["leverage"], 3),
                        "pnl_usdt":  round(pnl_usdt, 2),
                        "reason":    reason,
                        "opened_ts": position["opened_ts"],
                        "closed_ts": ts,
                        "opened_i":  position["opened_i"],
                        "closed_i":  i,
                        "balance":   round(balance, 2),
                        "rr":        rr,
                    })
                    equity.append({"time": ts, "balance": round(balance, 2)})
                    position = None
                    continue

            # Нов сигнал
            if position is None and balance > 1:
                try:
                    sig_data = self.sm.signal(window)
                except:
                    continue

                sig  = sig_data.get("signal", "HOLD")
                conf = sig_data.get("confidence", 0)

                if sig in ("LONG", "SHORT") and conf >= min_conf:
                    try:
                        # ATR-базиран TP/SL — тесен SL, широк TP
                        sl_dist = atr * sl_mult_cfg
                        tp_dist = atr * tp_mult_cfg

                        # Минимален R:R = 3:1
                        min_rr = 3.0
                        if tp_dist / max(sl_dist, 0.0001) < min_rr:
                            tp_dist = sl_dist * min_rr

                        # Максимален SL = 1.5% от цената (предпазва от прекалено голям SL)
                        max_sl_pct = 0.015
                        if sl_dist / price > max_sl_pct:
                            sl_dist = price * max_sl_pct
                            tp_dist = sl_dist * min_rr

                        if sig == "LONG":
                            tp = price + tp_dist
                            sl = price - sl_dist
                        else:
                            tp = price - tp_dist
                            sl = price + sl_dist

                        # Размер: рискуваме risk_pct% от баланса
                        risk_amount = balance * risk_pct_cfg / 100
                        margin      = min(risk_amount, balance * max_pos_cfg / 100)
                        if margin <= 0:
                            margin = balance * 0.05

                        if tp > 0 and sl > 0 and margin > 0:
                            position = {
                                "dir":       sig,
                                "entry":     price,
                                "tp":        tp,
                                "sl":        sl,
                                "sl_orig":   sl,
                                "margin":    margin,
                                "leverage":  leverage_cfg,
                                "opened_ts": ts,
                                "opened_i":  i,
                            }
                    except Exception as e:
                        logger.error(f"Position build error: {e}")

        # Затвори отворена позиция в края
        if position is not None and len(df_ind) > 0:
            try:
                price = float(df_ind.iloc[-1]["close"])
                ts    = timestamps[-1] if timestamps else str(len(df_ind)-1)
                if position["dir"] == "LONG":
                    pnl_pct = (price - position["entry"]) / position["entry"] * 100
                else:
                    pnl_pct = (position["entry"] - price) / position["entry"] * 100
                pnl_usdt = pnl_pct / 100 * position["margin"]
                balance += pnl_usdt
                trades.append({
                    "direction": position["dir"], "entry": round(position["entry"],2),
                    "exit": round(price,2), "tp": round(position["tp"],2), "sl": round(position["sl"],2),
                    "pnl_pct": round(pnl_pct,3), "pnl_usdt": round(pnl_usdt,2),
                    "reason": "Край", "opened_ts": position["opened_ts"], "closed_ts": ts,
                    "opened_i": position["opened_i"], "closed_i": len(df_ind)-1,
                    "balance": round(balance,2),
                    "rr": round(abs(position["tp"]-position["entry"]) / max(abs(position["sl"]-position["entry"]),0.0001), 2),
                })
                equity.append({"time": ts, "balance": round(balance,2)})
            except Exception as e:
                logger.error(f"Final close: {e}")

        wins   = [t for t in trades if t["pnl_usdt"] > 0]
        losses = [t for t in trades if t["pnl_usdt"] <= 0]
        total  = len(trades)
        pnl    = balance - initial_bal

        gross_profit  = sum(t["pnl_usdt"] for t in wins)
        gross_loss    = abs(sum(t["pnl_usdt"] for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2)
        avg_rr        = round(sum(t.get("rr",0) for t in trades) / max(total,1), 2)

        # Max drawdown
        max_dd, peak = 0.0, initial_bal
        for e in equity:
            b = e["balance"]
            if b > peak: peak = b
            dd = (peak - b) / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd

        return {
            "trades":       trades,
            "equity_curve": equity,
            "ohlcv":        df.reset_index().to_dict(orient="records") if hasattr(df, 'reset_index') else [],
            "stats": {
                "initial":       initial_bal,
                "final":         round(balance, 2),
                "pnl":           round(pnl, 2),
                "return_pct":    round(pnl / initial_bal * 100, 2),
                "total_trades":  total,
                "wins":          len(wins),
                "losses":        len(losses),
                "win_rate":      round(len(wins) / total * 100, 1) if total else 0,
                "avg_win":       round(gross_profit / len(wins), 2) if wins else 0,
                "avg_loss":      round(-gross_loss / len(losses), 2) if losses else 0,
                "max_drawdown":  round(max_dd, 2),
                "profit_factor": profit_factor,
                "avg_rr":        avg_rr,
            }
        }


# ─────────────────────────────────────────────────────────────
#  TRADING BOT
# ─────────────────────────────────────────────────────────────

class TradingBot:
    def __init__(self, config: Optional[BotConfig] = None):
        self.cfg       = config or BotConfig()
        self.strategy  = StrategyManager()
        self.risk      = RiskManager(RiskConfig(leverage=self.cfg.leverage, mode=self.cfg.mode))
        self.brain     = AIBrain(use_ai=self.cfg.use_ai)
        self.exchange  = ExchangeConnector(self.cfg.exchange_id, self.cfg.mode)
        self.demo      = DemoAccount(self.cfg.demo_balance)
        self.backtest  = BacktestEngine(self.strategy, self.risk)
        self._latest_signal: dict = {}
        self._signals_log:   list = []
        self._mtf_cache:     dict = {}
        self._ohlcv_cache:   dict = {}  # 30-секунден кеш за OHLCV

    def setup(self, exchange="mexc", api_key="", api_secret="", mode="futures", leverage=10) -> bool:
        self.cfg.exchange_id = exchange
        self.cfg.mode        = mode
        self.cfg.leverage    = leverage
        self.exchange        = ExchangeConnector(exchange, mode)
        ok = self.exchange.connect(api_key, api_secret)
        if ok and mode == "futures":
            self.exchange.set_leverage(self.cfg.symbol, leverage)
        self.risk.update_config(leverage=leverage, mode=mode)
        return ok

    def set_demo(self, enabled: bool, balance: Optional[float] = None):
        self.cfg.demo_mode = enabled
        if balance:
            self.demo.reset(balance)
            self.cfg.demo_balance = balance

    def select_strategy(self, name: str):
        self.strategy.select(name)

    def apply_strategy_risk_defaults(self, name: str):
        """Прилага препоръчаните risk параметри за стратегията."""
        defaults = STRATEGY_RISK_DEFAULTS.get(name, {})
        if defaults:
            self.risk.update_config(**defaults)

    def set_symbol(self, symbol: str):
        self.cfg.symbol = symbol

    def set_timeframe(self, tf: str):
        self.cfg.timeframe = tf

    def _fetch_df(self, symbol=None, timeframe=None, limit=300) -> Optional[pd.DataFrame]:
        import time as _time
        sym = symbol or self.cfg.symbol
        tf  = timeframe or self.cfg.timeframe
        cache_key = f"{sym}_{tf}_{limit}"
        # Cache за 30 секунди — не зарежда борсата при всеки tick
        cached = self._ohlcv_cache.get(cache_key)
        if cached and (_time.time() - cached["ts"]) < 30:
            return cached["df"]
        df = self.exchange.get_ohlcv(sym, tf, limit)
        if df is not None:
            self._ohlcv_cache[cache_key] = {"df": df, "ts": _time.time()}
            return df
        if self.cfg.demo_mode:
            df = self._gen_demo_ohlcv(limit=limit)
            self._ohlcv_cache[cache_key] = {"df": df, "ts": _time.time()}
            return df
        return None

    @staticmethod
    def _gen_demo_ohlcv(limit=300, base=65_000.0) -> pd.DataFrame:
        """Реалистични синусоидални данни с тренд."""
        rng    = pd.date_range(end=datetime.utcnow(), periods=limit, freq="15min")
        prices = [base]
        for i in range(limit - 1):
            cycle = math.sin(i / 40) * 0.0008 + math.sin(i / 15) * 0.0003
            noise = np.random.normal(0.0001 + cycle, 0.003)
            prices.append(max(prices[-1] * (1 + noise), 1))
        return pd.DataFrame({
            "open":   [p*(1-abs(np.random.normal(0,0.0008))) for p in prices],
            "high":   [p*(1+abs(np.random.normal(0,0.0025))) for p in prices],
            "low":    [p*(1-abs(np.random.normal(0,0.0025))) for p in prices],
            "close":  prices,
            "volume": [abs(np.random.normal(800,200)) for _ in prices],
        }, index=rng).astype(float)

    @staticmethod
    def _gen_realistic_ohlcv(limit=300, base=65_000.0) -> pd.DataFrame:
        """За бектест — по-волатилен модел."""
        rng    = pd.date_range(end=datetime.utcnow(), periods=limit, freq="15min")
        prices = [base]
        for i in range(limit - 1):
            cycle = math.sin(i / 30) * 0.001
            noise = np.random.normal(0.0003 + cycle, 0.004)
            prices.append(max(prices[-1] * (1 + noise), 1))
        return pd.DataFrame({
            "open":   [p*(1-abs(np.random.normal(0,0.001))) for p in prices],
            "high":   [p*(1+abs(np.random.normal(0,0.003))) for p in prices],
            "low":    [p*(1-abs(np.random.normal(0,0.003))) for p in prices],
            "close":  prices,
            "volume": [abs(np.random.normal(500,150)) for _ in prices],
        }, index=rng)

    def _fetch_mtf(self) -> dict:
        import time as _time
        # Cache за 60 секунди
        if self._mtf_cache and hasattr(self, '_mtf_cache_ts'):
            if _time.time() - self._mtf_cache_ts < 60:
                return self._mtf_cache
        result = {}
        # Само 3 TF за по-бързо зареждане
        for tf, lim in [("15m", 100), ("1h", 100), ("4h", 100)]:
            df = self._fetch_df(timeframe=tf, limit=lim)
            if df is not None:
                result[tf] = df
        self._mtf_cache   = result
        self._mtf_cache_ts = _time.time()
        return result

    def tick(self) -> dict:
        df = self._fetch_df()
        if df is None or len(df) < 50:
            return {"error": "Недостатъчно данни"}
        try:
            df_ind    = self.strategy.compute(df)
            strat_sig = self.strategy.signal(df_ind)
        except Exception as e:
            return {"error": f"Стратегия грешка: {e}"}

        # MTF се обновява само ако cache-ът е изтекъл (60с)
        mtf    = self._mtf_cache if self._mtf_cache else self._fetch_mtf()
        eth_df = self._fetch_df("ETH/USDT", "1h", 50) if self.brain.corr_filter.enabled else None

        try:
            final = self.brain.decide(
                strategy_signal=strat_sig, symbol=self.cfg.symbol,
                mtf_data=mtf, eth_df=eth_df,
            )
        except Exception as e:
            final = strat_sig
            final["error"] = str(e)

        current_price = float(df["close"].iloc[-1])
        atr = None
        if "atr" in df_ind.columns:
            try: atr = float(df_ind["atr"].iloc[-1])
            except: pass

        self.risk.new_day(self.demo.balance)

        if self.demo.position:
            tr     = self.risk.tick_trailing(current_price, atr)
            closed = self.demo.update_position(
                current_price,
                trailing_stop=tr["stop"] if tr.get("activated") else None,
            )
            if closed:
                self.risk.close_position(closed["pnl_usdt"])

        sig = final.get("signal", "HOLD")
        if sig in ("LONG","SHORT") and not self.risk.should_pause and self.demo.position is None:
            bal      = self.demo.balance
            pos_plan = self.risk.build_position(balance=bal, entry=current_price, direction=sig, atr=atr)
            qty      = pos_plan["sizing"]["qty"]
            levels   = pos_plan["levels"]
            if qty > 0:
                self.risk.open_trailing(sig, current_price, levels["sl"])
                self.demo.open_position(
                    direction=sig, entry=current_price, qty=qty,
                    tp=levels["tp"], sl=levels["sl"],
                    strategy=self.strategy._active_name,
                )
                self._signals_log.append({
                    "time": datetime.utcnow().isoformat(),
                    "price": current_price,
                    "signal": sig,
                    "confidence": final.get("confidence", 0),
                    "strategy": self.strategy._active_name,
                })

        self._latest_signal = {
            **final,
            "current_price": current_price,
            "atr": atr,
            "strategy": self.strategy._active_name,
            "demo_balance": self.demo.balance,
            "demo_position": self.demo.position,
            "demo_pnl": self.demo.pnl,
            "win_rate": self.demo.win_rate,
            "risk_status": self.risk.get_status(),
        }
        return self._latest_signal

    def get_latest_signal(self): return self._latest_signal
    def get_signals_log(self):   return self._signals_log

    def run_backtest(self, days=7) -> dict:
        limit = max(days * 96, 300)
        # Опитваме реални данни от борсата
        df = self.exchange.get_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=limit)
        if df is None or len(df) < 60:
            df = self._gen_realistic_ohlcv(limit=limit)
        if df is None or len(df) < 60:
            return {"error": "Не могат да се заредят данни"}
        return self.backtest.run(df, initial_bal=self.demo.initial)

    @property
    def is_demo(self):    return self.cfg.demo_mode
    @property
    def connected(self):  return self.exchange.connected
