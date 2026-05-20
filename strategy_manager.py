"""
strategy_manager.py — NEXUS BOT PRO
5 стратегии, оптимизирани за реален пазар.
Цели: 2x за 15–30 дни. Агресивната — 7–10 дни.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class TimeFilter:
    enabled: bool = False
    sessions: list = field(default_factory=lambda: [
        {"name": "London",   "start": "07:00", "end": "16:00"},
        {"name": "New York", "start": "13:00", "end": "21:00"},
    ])
    custom_enabled: bool = False
    custom_start: str = "00:00"
    custom_end:   str = "23:59"

    def is_allowed(self, dt=None):
        if not self.enabled:
            return True, "Филтърът е изключен"
        now = dt or datetime.utcnow()
        current = now.strftime("%H:%M")
        if self.custom_enabled:
            return self.custom_start <= current <= self.custom_end, f"Ръчен прозорец"
        for s in self.sessions:
            if s["start"] <= current <= s["end"]:
                return True, f"Сесия {s['name']}"
        return False, "Извън търговските сесии"

    def add_session(self, name, start, end):
        self.sessions.append({"name": name, "start": start, "end": end})

    def remove_session(self, name):
        self.sessions = [s for s in self.sessions if s["name"] != name]


@dataclass
class StrategyConfig:
    name: str = "Unnamed"
    description: str = ""
    style: str = "balanced"
    target_days: int = 30
    timeframes: list = field(default_factory=lambda: ["15m", "1h"])
    symbol: str = "BTC/USDT"
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    ema_fast: int = 9
    ema_medium: int = 21
    ema_slow: int = 50
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    stoch_k: int = 14
    stoch_d: int = 3
    vol_ma_period: int = 20
    vol_multiplier: float = 1.2
    min_confidence: float = 65.0
    atr_tp_mult: float = 3.5
    atr_sl_mult: float = 1.0
    time_filter: TimeFilter = field(default_factory=TimeFilter)
    custom_indicator_code: str = ""


# Фабрични настройки за риск мениджмент по стратегия
STRATEGY_RISK_DEFAULTS = {
    "Quantum Scalper": {
        "risk_pct": 5.0, "leverage": 20,
        "atr_tp_mult": 2.5, "atr_sl_mult": 0.8,
        "tp_pct": 4.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_atr_mult": 1.5,
        "trailing_activation_pct": 0.8,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 8,
    },
    "NEXUS SMC Elite": {
        "risk_pct": 6.0, "leverage": 20,
        "atr_tp_mult": 3.5, "atr_sl_mult": 1.0,
        "tp_pct": 5.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_atr_mult": 2.0,
        "trailing_activation_pct": 1.0,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 8,
    },
    "Titan Trend": {
        "risk_pct": 4.0, "leverage": 15,
        "atr_tp_mult": 4.0, "atr_sl_mult": 1.2,
        "tp_pct": 6.0, "sl_pct": 1.5,
        "trailing_stop": True, "trailing_atr_mult": 2.5,
        "trailing_activation_pct": 1.5,
        "daily_loss_limit_pct": 12.0, "max_consecutive_losses": 6,
    },
    "Phoenix Reversal": {
        "risk_pct": 3.5, "leverage": 12,
        "atr_tp_mult": 3.5, "atr_sl_mult": 1.0,
        "tp_pct": 5.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_atr_mult": 2.0,
        "trailing_activation_pct": 1.2,
        "daily_loss_limit_pct": 12.0, "max_consecutive_losses": 5,
    },
    "Iron Shield": {
        "risk_pct": 2.5, "leverage": 10,
        "atr_tp_mult": 4.0, "atr_sl_mult": 1.0,
        "tp_pct": 4.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_atr_mult": 2.5,
        "trailing_activation_pct": 1.5,
        "daily_loss_limit_pct": 10.0, "max_consecutive_losses": 4,
    },
}


STRATEGY_TEMPLATES = {
    "Quantum Scalper": StrategyConfig(
        name="Quantum Scalper",
        description="Агресивен скалп. Цел: 2x за 7–10 дни. Висок риск/награда.",
        style="scalp", target_days=8, timeframes=["1m","5m"],
        rsi_period=7, rsi_oversold=35.0, rsi_overbought=65.0,
        ema_fast=5, ema_medium=13, ema_slow=34,
        macd_fast=8, macd_slow=17, macd_signal=9,
        bb_period=14, bb_std=1.8, atr_period=7,
        vol_multiplier=1.1, min_confidence=60.0,
        atr_tp_mult=2.5, atr_sl_mult=0.8,
        time_filter=TimeFilter(enabled=False),
    ),
    "NEXUS SMC Elite": StrategyConfig(
        name="NEXUS SMC Elite",
        description="Smart Money + Order Flow. Цел: 2x за 10–15 дни.",
        style="aggressive", target_days=12, timeframes=["15m","1h"],
        rsi_period=14, rsi_oversold=36.0, rsi_overbought=64.0,
        ema_fast=8, ema_medium=21, ema_slow=55,
        macd_fast=10, macd_slow=22, macd_signal=7,
        bb_period=20, bb_std=2.0, atr_period=14,
        vol_multiplier=1.1, min_confidence=62.0,
        atr_tp_mult=3.5, atr_sl_mult=1.0,
        time_filter=TimeFilter(enabled=False),
    ),
    "Titan Trend": StrategyConfig(
        name="Titan Trend",
        description="Trend-following. Triple EMA + MACD. Цел: 2x за 15–20 дни.",
        style="trend", target_days=17, timeframes=["1h","4h"],
        rsi_period=14, rsi_oversold=40.0, rsi_overbought=60.0,
        ema_fast=20, ema_medium=50, ema_slow=100,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        vol_multiplier=1.1, min_confidence=63.0,
        atr_tp_mult=4.0, atr_sl_mult=1.2,
        time_filter=TimeFilter(enabled=False),
    ),
    "Phoenix Reversal": StrategyConfig(
        name="Phoenix Reversal",
        description="Улавя обрати. RSI + BB дивергенция. Цел: 2x за 20–25 дни.",
        style="balanced", target_days=22, timeframes=["30m","1h"],
        rsi_period=14, rsi_oversold=33.0, rsi_overbought=67.0,
        ema_fast=9, ema_medium=21, ema_slow=55,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.2, atr_period=14,
        vol_multiplier=1.1, min_confidence=63.0,
        atr_tp_mult=3.5, atr_sl_mult=1.0,
        time_filter=TimeFilter(enabled=False),
    ),
    "Iron Shield": StrategyConfig(
        name="Iron Shield",
        description="Безопасна. Висока точност. Цел: 2x за 25–30 дни.",
        style="safe", target_days=28, timeframes=["4h","1d"],
        rsi_period=14, rsi_oversold=33.0, rsi_overbought=67.0,
        ema_fast=21, ema_medium=55, ema_slow=100,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        vol_multiplier=1.1, min_confidence=65.0,
        atr_tp_mult=4.0, atr_sl_mult=1.0,
        time_filter=TimeFilter(enabled=False),
    ),
}


class Indicators:
    @staticmethod
    def ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series, period=14):
        delta = series.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series, fast=12, slow=26, signal=9):
        ef = series.ewm(span=fast, adjust=False).mean()
        es = series.ewm(span=slow, adjust=False).mean()
        ml = ef - es
        sl = ml.ewm(span=signal, adjust=False).mean()
        return ml, sl, ml - sl

    @staticmethod
    def bollinger(series, period=20, std=2.0):
        mid   = series.rolling(period).mean()
        sigma = series.rolling(period).std()
        return mid + std * sigma, mid, mid - std * sigma

    @staticmethod
    def atr(high, low, close, period=14):
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def stochastic(high, low, close, k=14, d=3):
        lo_k = low.rolling(k).min()
        hi_k = high.rolling(k).max()
        sk   = 100 * (close - lo_k) / (hi_k - lo_k).replace(0, np.nan)
        return sk, sk.rolling(d).mean()


class IndicatorEngine:
    def compute(self, df, cfg):
        if len(df) < 50:
            return df
        ind = Indicators()
        c, h, lo, v = df["close"], df["high"], df["low"], df["volume"]
        df["rsi"]        = ind.rsi(c, cfg.rsi_period)
        df["ema_fast"]   = ind.ema(c, cfg.ema_fast)
        df["ema_medium"] = ind.ema(c, cfg.ema_medium)
        df["ema_slow"]   = ind.ema(c, cfg.ema_slow)
        ml, ms, mh       = ind.macd(c, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
        df["macd"]        = ml
        df["macd_signal"] = ms
        df["macd_hist"]   = mh
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = ind.bollinger(c, cfg.bb_period, cfg.bb_std)
        df["bb_width"]   = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["atr"]        = ind.atr(h, lo, c, cfg.atr_period)
        df["atr_pct"]    = df["atr"] / c * 100
        df["stoch_k"], df["stoch_d"] = ind.stochastic(h, lo, c, cfg.stoch_k, cfg.stoch_d)
        df["vol_ma"]     = v.rolling(cfg.vol_ma_period).mean()
        df["vol_ratio"]  = v / df["vol_ma"].replace(0, np.nan)
        df["momentum"]   = c / c.shift(10) - 1
        df["body"]       = abs(c - df["open"])
        df["upper_wick"] = df["high"] - df[["open","close"]].max(axis=1)
        df["lower_wick"] = df[["open","close"]].min(axis=1) - df["low"]
        if cfg.custom_indicator_code.strip():
            try:
                ns = {"df": df.copy(), "pd": pd, "np": np}
                exec(cfg.custom_indicator_code, ns)
                df = ns.get("df", df)
            except Exception as e:
                logger.error(f"Custom indicator: {e}")
        return df.dropna(subset=["rsi", "ema_fast"])


class SignalGenerator:
    def generate(self, df, cfg):
        if df.empty or len(df) < 3:
            return self._hold("Недостатъчно данни")
        allowed, reason = cfg.time_filter.is_allowed()
        if not allowed:
            return self._hold(f"TimeFilter: {reason}")

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        vl, vs, reasons = 0, 0, []

        # RSI
        rsi = last.get("rsi", 50)
        if   rsi < cfg.rsi_oversold - 5:  vl += 3; reasons.append(f"RSI={rsi:.0f} силно oversold")
        elif rsi < cfg.rsi_oversold:       vl += 2; reasons.append(f"RSI={rsi:.0f} oversold")
        elif rsi > cfg.rsi_overbought + 5: vs += 3; reasons.append(f"RSI={rsi:.0f} силно overbought")
        elif rsi > cfg.rsi_overbought:     vs += 2; reasons.append(f"RSI={rsi:.0f} overbought")
        prev_rsi = prev.get("rsi", 50)
        if rsi > prev_rsi and rsi < 50: vl += 1; reasons.append("RSI расте от дъно")
        elif rsi < prev_rsi and rsi > 50: vs += 1; reasons.append("RSI пада от връх")

        # EMA
        ef  = last.get("ema_fast",   0)
        em  = last.get("ema_medium", 0)
        es  = last.get("ema_slow",   0)
        pef = prev.get("ema_fast",   0)
        pem = prev.get("ema_medium", 0)
        cur = last.get("close",      0)
        if ef > em > es:   vl += 2; reasons.append("EMA bullish alignment")
        elif ef < em < es: vs += 2; reasons.append("EMA bearish alignment")
        if pef <= pem and ef > em: vl += 2; reasons.append("EMA golden cross")
        elif pef >= pem and ef < em: vs += 2; reasons.append("EMA death cross")
        if cur > ef: vl += 1
        else:        vs += 1

        # MACD
        ml  = last.get("macd",        0)
        ms_ = last.get("macd_signal", 0)
        mh  = last.get("macd_hist",   0)
        pml = prev.get("macd",        0)
        pms = prev.get("macd_signal", 0)
        pmh = prev.get("macd_hist",   0)
        if pml < pms and ml > ms_:   vl += 3; reasons.append("MACD bullish crossover")
        elif pml > pms and ml < ms_: vs += 3; reasons.append("MACD bearish crossover")
        elif ml > ms_: vl += 1
        else:          vs += 1
        if mh > 0 and mh > pmh: vl += 1; reasons.append("MACD hist расте")
        elif mh < 0 and mh < pmh: vs += 1; reasons.append("MACD hist пада")

        # Bollinger
        bbu = last.get("bb_upper", 0)
        bbl = last.get("bb_lower", 0)
        bbm = last.get("bb_mid",   0)
        bbw = last.get("bb_width", 0)
        pbw = prev.get("bb_width", 0)
        if cur < bbl:   vl += 2; reasons.append("Под BB долна лента")
        elif cur > bbu: vs += 2; reasons.append("Над BB горна лента")
        if bbw > pbw * 1.2:
            if cur > bbm: vl += 1; reasons.append("BB breakout нагоре")
            else:         vs += 1; reasons.append("BB breakout надолу")

        # Stochastic
        sk  = last.get("stoch_k", 50)
        sd_ = last.get("stoch_d", 50)
        psk = prev.get("stoch_k", 50)
        psd = prev.get("stoch_d", 50)
        if sk < 20 and sd_ < 20:   vl += 2; reasons.append(f"Stoch oversold {sk:.0f}")
        elif sk > 80 and sd_ > 80: vs += 2; reasons.append(f"Stoch overbought {sk:.0f}")
        if psk < psd and sk > sd_ and sk < 40: vl += 2; reasons.append("Stoch bull cross дъно")
        elif psk > psd and sk < sd_ and sk > 60: vs += 2; reasons.append("Stoch bear cross връх")

        # Momentum
        mom = last.get("momentum", 0)
        if mom > 0.005:  vl += 1; reasons.append(f"Mom +{mom*100:.1f}%")
        elif mom < -0.005: vs += 1; reasons.append(f"Mom {mom*100:.1f}%")

        # Volume
        vr = last.get("vol_ratio", 1.0)
        if vr >= cfg.vol_multiplier:
            if vl > vs: vl += 1; reasons.append(f"Vol {vr:.1f}x confirm LONG")
            elif vs > vl: vs += 1; reasons.append(f"Vol {vr:.1f}x confirm SHORT")

        # Price action
        body       = last.get("body",       0)
        lower_wick = last.get("lower_wick", 0)
        upper_wick = last.get("upper_wick", 0)
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            vl += 1; reasons.append("Hammer свещ")
        elif upper_wick > body * 2 and lower_wick < body * 0.5:
            vs += 1; reasons.append("Shooting star")

        # ATR филтър
        atr_pct = last.get("atr_pct", 1.0)
        if atr_pct < 0.15:
            return self._hold("ATR твърде нисък — flat пазар")

        # Решение
        threshold = 5 if cfg.style in ("scalp", "aggressive") else 6
        total = vl + vs

        if vl >= threshold and vl > vs:
            dom  = vl / max(total, 1)
            conf = min(95, 52 + dom * 35 + min(vl / 12, 1.0) * 13)
            if conf >= cfg.min_confidence:
                return {"signal": "LONG",  "confidence": round(conf,1),
                        "votes_long": vl, "votes_short": vs,
                        "reasons": reasons, "atr": last.get("atr"), "rsi": rsi}

        if vs >= threshold and vs > vl:
            dom  = vs / max(total, 1)
            conf = min(95, 52 + dom * 35 + min(vs / 12, 1.0) * 13)
            if conf >= cfg.min_confidence:
                return {"signal": "SHORT", "confidence": round(conf,1),
                        "votes_long": vl, "votes_short": vs,
                        "reasons": reasons, "atr": last.get("atr"), "rsi": rsi}

        return self._hold(f"Гласове L={vl} S={vs} < {threshold}")

    @staticmethod
    def _hold(reason):
        return {"signal":"HOLD","confidence":50,"votes_long":0,
                "votes_short":0,"reasons":[reason],"atr":None,"rsi":None}


class StrategyManager:
    def __init__(self):
        import copy
        self._templates   = {k: copy.deepcopy(v) for k, v in STRATEGY_TEMPLATES.items()}
        self._active_name = "NEXUS SMC Elite"
        self._indicators  = IndicatorEngine()
        self._signals     = SignalGenerator()

    @property
    def active(self):
        return self._templates[self._active_name]

    @property
    def names(self):
        return list(self._templates.keys())

    def select(self, name):
        if name in self._templates:
            self._active_name = name

    def update_param(self, param, value):
        if hasattr(self.active, param):
            setattr(self.active, param, value)

    def reset_to_default(self, name=None):
        """Фабрически настройки на стратегията."""
        import copy
        target = name or self._active_name
        if target in STRATEGY_TEMPLATES:
            self._templates[target] = copy.deepcopy(STRATEGY_TEMPLATES[target])

    def update_time_filter(self, **kwargs):
        tf = self.active.time_filter
        for k, v in kwargs.items():
            if hasattr(tf, k):
                setattr(tf, k, v)

    def compute(self, df):
        return self._indicators.compute(df.copy(), self.active)

    def signal(self, df):
        return self._signals.generate(df, self.active)

    def get_config_dict(self):
        cfg = self.active
        return {
            "name": cfg.name, "description": cfg.description,
            "style": cfg.style, "target_days": cfg.target_days,
            "timeframes": cfg.timeframes,
            "rsi_period": cfg.rsi_period, "rsi_oversold": cfg.rsi_oversold,
            "rsi_overbought": cfg.rsi_overbought,
            "ema_fast": cfg.ema_fast, "ema_medium": cfg.ema_medium, "ema_slow": cfg.ema_slow,
            "macd_fast": cfg.macd_fast, "macd_slow": cfg.macd_slow, "macd_signal": cfg.macd_signal,
            "bb_period": cfg.bb_period, "bb_std": cfg.bb_std,
            "atr_period": cfg.atr_period,
            "vol_multiplier": cfg.vol_multiplier, "min_confidence": cfg.min_confidence,
            "time_filter_on": cfg.time_filter.enabled,
            "sessions": cfg.time_filter.sessions,
            "custom_start": cfg.time_filter.custom_start, "custom_end": cfg.time_filter.custom_end,
        }
