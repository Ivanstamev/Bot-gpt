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
from strategy_manager import StrategyManager, STRATEGY_RISK_DEFAULTS
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

        # Запази реалните timestamp-ове за визуализация
        if hasattr(df_ind.index, 'to_pydatetime'):
            timestamps = [str(t) for t in df_ind.index]
        else:
            timestamps = [str(i) for i in range(len(df_ind))]

        df_ind = df_ind.reset_index(drop=True)
        balance  = initial_bal
        trades   = []
        equity   = [{"time": timestamps[0] if timestamps else "0", "balance": round(initial_bal, 2)}]
        position = None
        min_conf = self.sm.active.min_confidence
        cfg      = self.rm.cfg

        for i in range(30, len(df_ind)):
            window = df_ind.iloc[:i].copy()
            row    = df_ind.iloc[i]
            ts     = timestamps[i] if i < len(timestamps) else str(i)

            try:
                price = float(row["close"])
                atr   = float(row["atr"]) if "atr" in df_ind.columns and not pd.isna(row.get("atr", float("nan"))) else None
                high  = float(row["high"])
                low   = float(row["low"])
            except:
                continue

            # Управление на позиция — проверяваме High/Low за по-реалистично TP/SL
            if position is not None:
                dir_ = position["dir"]
                hit_tp = (dir_=="LONG"  and high >= position["tp"]) or \
                         (dir_=="SHORT" and low  <= position["tp"])
                hit_sl = (dir_=="LONG"  and low  <= position["sl"]) or \
                         (dir_=="SHORT" and high >= position["sl"])

                if hit_tp or hit_sl:
                    exit_p = position["tp"] if hit_tp else position["sl"]
                    reason = "TP" if hit_tp else "SL"
                    if dir_ == "LONG":
                        pnl_pct = (exit_p - position["entry"]) / position["entry"] * 100
                    else:
                        pnl_pct = (position["entry"] - exit_p) / position["entry"] * 100

                    pnl_usdt = pnl_pct / 100 * position["margin"]
                    balance += pnl_usdt

                    trades.append({
                        "direction": dir_,
                        "entry":     round(position["entry"], 2),
                        "exit":      round(exit_p, 2),
                        "tp":        round(position["tp"], 2),
                        "sl":        round(position["sl"], 2),
                        "pnl_pct":   round(pnl_pct, 3),
                        "pnl_usdt":  round(pnl_usdt, 2),
                        "reason":    reason,
                        "opened_ts": position["opened_ts"],
                        "closed_ts": ts,
                        "opened_i":  position["opened_i"],
                        "closed_i":  i,
                        "balance":   round(balance, 2),
                        "rr":        round(abs(position["tp"]-position["entry"]) / max(abs(position["sl"]-position["entry"]),0.0001), 2),
                    })
                    equity.append({"time": ts, "balance": round(balance, 2)})
                    position = None
                    continue

            # Нов сигнал
            if position is None:
                try:
                    sig_data = self.sm.signal(window)
                except:
                    continue

                sig  = sig_data.get("signal", "HOLD")
                conf = sig_data.get("confidence", 0)

                if sig in ("LONG", "SHORT") and conf >= min_conf:
                    try:
                        # ATR-базиран TP/SL с добро R:R
                        if atr and cfg.use_atr:
                            # Адаптивен multiplier от стратегията
                            tp_mult = getattr(self.sm.active, 'atr_tp_mult', cfg.atr_tp_mult)
                            sl_mult = getattr(self.sm.active, 'atr_sl_mult', cfg.atr_sl_mult)
                            tp_dist = atr * tp_mult
                            sl_dist = atr * sl_mult
                        else:
                            tp_dist = price * cfg.tp_pct / 100
                            sl_dist = price * cfg.sl_pct / 100

                        # Минимален R:R = 2:1
                        if tp_dist / max(sl_dist, 0.0001) < 2.0:
                            tp_dist = sl_dist * 2.5

                        if sig == "LONG":
                            tp = price + tp_dist
                            sl = price - sl_dist
                        else:
                            tp = price - tp_dist
                            sl = price + sl_dist

                        # Размер на позицията
                        risk_amount  = balance * cfg.risk_pct / 100
                        margin       = min(risk_amount * cfg.leverage,
                                          balance * cfg.max_position_pct / 100)
                        if margin <= 0:
                            margin = balance * 0.02

                        if tp > 0 and sl > 0 and margin > 0:
                            position = {
                                "dir":       sig,
                                "entry":     price,
                                "tp":        tp,
                                "sl":        sl,
                                "margin":    margin,
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
        sym = symbol or self.cfg.symbol
        tf  = timeframe or self.cfg.timeframe
        # Опитваме реални данни дори в demo режим
        df = self.exchange.get_ohlcv(sym, tf, limit)
        if df is not None:
            return df
        if self.cfg.demo_mode:
            return self._gen_demo_ohlcv(limit=limit)
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
        result = {}
        for tf, lim in [("5m",100),("15m",200),("1h",200),("4h",150),("1d",100)]:
            df = self._fetch_df(timeframe=tf, limit=lim)
            if df is not None:
                result[tf] = df
        self._mtf_cache = result
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

        mtf    = self._mtf_cache or self._fetch_mtf()
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
