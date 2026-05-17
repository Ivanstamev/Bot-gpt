"""
risk_management.py — NEXUS BOT PRO
Position Sizing, Trailing Stop, Daily Guard
"""

from __future__ import annotations
import math
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    risk_pct: float = 1.0
    max_position_pct: float = 20.0
    tp_pct: float = 2.0
    sl_pct: float = 1.0
    use_atr: bool = True
    atr_tp_mult: float = 2.5
    atr_sl_mult: float = 1.0
    trailing_stop: bool = True
    trailing_pct: float = 0.8
    trailing_atr_mult: float = 1.5
    trailing_activation_pct: float = 0.5
    daily_loss_limit_pct: float = 5.0
    max_consecutive_losses: int = 4
    leverage: int = 10
    mode: str = "futures"


@dataclass
class TrailingState:
    active: bool = False
    direction: str = "LONG"
    entry_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float("inf")
    current_stop: float = 0.0
    activated: bool = False


@dataclass
class DailyStats:
    date: str = ""
    starting_balance: float = 0.0
    realized_pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    bot_paused: bool = False


# ─────────────────────────────────────────────────────────────
#  POSITION SIZER
# ─────────────────────────────────────────────────────────────

class PositionSizer:
    def __init__(self, config: RiskConfig):
        self.cfg = config

    def calculate(self, balance, entry_price, sl_price, direction="LONG"):
        if entry_price <= 0 or sl_price <= 0:
            return self._empty()

        if direction == "LONG":
            sl_dist_pct = (entry_price - sl_price) / entry_price * 100
        else:
            sl_dist_pct = (sl_price - entry_price) / entry_price * 100

        if sl_dist_pct <= 0:
            return self._empty()

        risk_amount = balance * self.cfg.risk_pct / 100
        qty = risk_amount / (entry_price * sl_dist_pct / 100)

        if self.cfg.mode == "futures":
            notional = qty * entry_price
            margin   = notional / self.cfg.leverage
        else:
            margin   = qty * entry_price
            notional = margin

        max_notional = balance * self.cfg.max_position_pct / 100
        if self.cfg.mode == "futures":
            max_notional *= self.cfg.leverage

        if notional > max_notional:
            scale    = max_notional / notional
            qty     *= scale
            margin  *= scale
            notional*= scale

        qty = round(qty, 4) if entry_price >= 10000 else round(qty, 3)

        return {
            "qty": qty, "entry_price": entry_price, "sl_price": sl_price,
            "risk_amount": round(risk_amount, 2), "margin_used": round(margin, 2),
            "notional": round(notional, 2), "sl_dist_pct": round(sl_dist_pct, 3),
            "leverage": self.cfg.leverage if self.cfg.mode == "futures" else 1,
            "mode": self.cfg.mode,
        }

    @staticmethod
    def _empty():
        return {"qty":0,"entry_price":0,"sl_price":0,"risk_amount":0,
                "margin_used":0,"notional":0,"sl_dist_pct":0,"leverage":1,"mode":"spot"}


# ─────────────────────────────────────────────────────────────
#  TP/SL CALCULATOR
# ─────────────────────────────────────────────────────────────

class TPSLCalculator:
    def __init__(self, config: RiskConfig):
        self.cfg = config

    def calculate(self, entry, direction, atr=None):
        use_atr = self.cfg.use_atr and atr and atr > 0

        if use_atr:
            tp_dist = atr * self.cfg.atr_tp_mult
            sl_dist = atr * self.cfg.atr_sl_mult
        else:
            tp_dist = entry * self.cfg.tp_pct / 100
            sl_dist = entry * self.cfg.sl_pct / 100

        if direction == "LONG":
            tp = entry + tp_dist
            sl = entry - sl_dist
        else:
            tp = entry - tp_dist
            sl = entry + sl_dist

        rr = tp_dist / sl_dist if sl_dist > 0 else 0

        return {
            "tp": round(tp, 4), "sl": round(sl, 4),
            "tp_dist": round(tp_dist, 4), "sl_dist": round(sl_dist, 4),
            "rr_ratio": round(rr, 2), "atr_based": use_atr,
        }


# ─────────────────────────────────────────────────────────────
#  TRAILING STOP
# ─────────────────────────────────────────────────────────────

class TrailingStopEngine:
    def __init__(self, config: RiskConfig):
        self.cfg   = config
        self.state = TrailingState()

    def open_position(self, direction, entry_price, initial_sl):
        self.state = TrailingState(
            active=True, direction=direction,
            entry_price=entry_price, highest_price=entry_price,
            lowest_price=entry_price, current_stop=initial_sl, activated=False,
        )

    def update(self, current_price, atr=None):
        s = self.state
        if not s.active:
            return {"stop":0,"activated":False,"hit":False,"moved":False}

        old_stop = s.current_stop

        if self.cfg.use_atr and atr and atr > 0:
            trail_dist = atr * self.cfg.trailing_atr_mult
        else:
            trail_dist = current_price * self.cfg.trailing_pct / 100

        activation_dist = s.entry_price * self.cfg.trailing_activation_pct / 100

        if s.direction == "LONG":
            if not s.activated and current_price >= s.entry_price + activation_dist:
                s.activated = True
            if current_price > s.highest_price:
                s.highest_price = current_price
            if s.activated:
                new_stop = s.highest_price - trail_dist
                if new_stop > s.current_stop:
                    s.current_stop = new_stop
            hit = current_price <= s.current_stop
        else:
            if not s.activated and current_price <= s.entry_price - activation_dist:
                s.activated = True
            if current_price < s.lowest_price:
                s.lowest_price = current_price
            if s.activated:
                new_stop = s.lowest_price + trail_dist
                if new_stop < s.current_stop:
                    s.current_stop = new_stop
            hit = current_price >= s.current_stop

        if hit:
            s.active = False

        return {
            "stop":      round(s.current_stop, 4),
            "activated": s.activated,
            "hit":       hit,
            "moved":     s.current_stop != old_stop,
        }

    def close(self):
        self.state.active = False

    @property
    def current_stop(self):
        return self.state.current_stop

    @property
    def is_active(self):
        return self.state.active


# ─────────────────────────────────────────────────────────────
#  DAILY GUARD
# ─────────────────────────────────────────────────────────────

class DailyGuard:
    def __init__(self, config: RiskConfig):
        self.cfg   = config
        self.stats = DailyStats()

    def new_day(self, balance):
        from datetime import date
        today = str(date.today())
        if self.stats.date != today:
            self.stats = DailyStats(date=today, starting_balance=balance)

    def record_trade(self, pnl_usdt):
        self.stats.trades += 1
        self.stats.realized_pnl += pnl_usdt

        if pnl_usdt > 0:
            self.stats.wins += 1
            self.stats.consecutive_losses = 0
        else:
            self.stats.losses += 1
            self.stats.consecutive_losses += 1

        if self.stats.starting_balance > 0:
            loss_pct = -self.stats.realized_pnl / self.stats.starting_balance * 100
            if loss_pct >= self.cfg.daily_loss_limit_pct:
                self.stats.bot_paused = True
                return True

        if self.stats.consecutive_losses >= self.cfg.max_consecutive_losses:
            self.stats.bot_paused = True
            return True

        return False

    def resume(self):
        self.stats.bot_paused = False
        self.stats.consecutive_losses = 0

    @property
    def should_pause(self):
        return self.stats.bot_paused


# ─────────────────────────────────────────────────────────────
#  RISK MANAGER — главен клас
# ─────────────────────────────────────────────────────────────

class RiskManager:
    def __init__(self, config: Optional[RiskConfig] = None):
        self.cfg      = config or RiskConfig()
        self.sizer    = PositionSizer(self.cfg)
        self.tpsl     = TPSLCalculator(self.cfg)
        self.trailing = TrailingStopEngine(self.cfg)
        self.daily    = DailyGuard(self.cfg)

    def update_config(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.cfg, k):
                setattr(self.cfg, k, v)
        self.sizer    = PositionSizer(self.cfg)
        self.tpsl     = TPSLCalculator(self.cfg)
        self.trailing = TrailingStopEngine(self.cfg)
        self.daily    = DailyGuard(self.cfg)

    def build_position(self, balance, entry, direction, atr=None):
        levels  = self.tpsl.calculate(entry, direction, atr)
        sizing  = self.sizer.calculate(balance, entry, levels["sl"], direction)
        return {
            "direction": direction, "entry": entry,
            "levels":    levels,    "sizing": sizing,
            "summary": {
                "qty":       sizing["qty"],
                "tp":        levels["tp"],
                "sl":        levels["sl"],
                "rr":        levels["rr_ratio"],
                "risk_usdt": sizing["risk_amount"],
                "margin":    sizing["margin_used"],
                "notional":  sizing["notional"],
            }
        }

    def open_trailing(self, direction, entry, sl):
        if self.cfg.trailing_stop:
            self.trailing.open_position(direction, entry, sl)

    def tick_trailing(self, current_price, atr=None):
        if self.cfg.trailing_stop and self.trailing.is_active:
            return self.trailing.update(current_price, atr)
        return {"stop":0,"activated":False,"hit":False,"moved":False}

    def close_position(self, pnl_usdt):
        self.trailing.close()
        return self.daily.record_trade(pnl_usdt)

    def new_day(self, balance):
        self.daily.new_day(balance)

    def resume(self):
        """Продължава бота след пауза."""
        self.daily.resume()

    @property
    def should_pause(self):
        return self.daily.should_pause

    def get_status(self):
        s = self.daily.stats
        return {
            "date":               s.date,
            "daily_pnl":          round(s.realized_pnl, 2),
            "daily_trades":       s.trades,
            "wins":               s.wins,
            "losses":             s.losses,
            "consecutive_losses": s.consecutive_losses,
            "paused":             s.bot_paused,
            "trailing_active":    self.trailing.is_active,
            "trailing_stop":      self.trailing.current_stop,
        }
