"""
strategy_manager.py
══════════════════════════════════════════════════════════════
5 стратегии с вградени индикатори (без pandas-ta).
══════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  TIME FILTER
# ─────────────────────────────────────────────────────────────

@dataclass
class TimeFilter:
    enabled: bool = True
    sessions: list = field(default_factory=lambda: [
        {"name": "London",   "start": "07:00", "end": "16:00"},
        {"name": "New York", "start": "13:00", "end": "21:00"},
    ])
    custom_enabled: bool = False
    custom_start: str = "08:00"
    custom_end:   str = "20:00"

    def is_allowed(self, dt: Optional[datetime] = None) -> tuple:
        if not self.enabled:
            return True, "Филтърът е изключен"
        now     = dt or datetime.utcnow()
        current = now.strftime("%H:%M")
        if self.custom_enabled:
            allowed = self.custom_start <= current <= self.custom_end
            return allowed, f"Ръчен прозорец {self.custom_start}–{self.custom_end} UTC"
        for s in self.sessions:
            if s["start"] <= current <= s["end"]:
                return True, f"Сесия {s['name']} активна"
        return False, "Извън търговските сесии"

    def add_session(self, name, start, end):
        self.sessions.append({"name": name, "start": start, "end": end})

    def remove_session(self, name):
        self.sessions = [s for s in self.sessions if s["name"] != name]


# ─────────────────────────────────────────────────────────────
#  STRATEGY CONFIG
# ─────────────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    name: str = "Unnamed"
    description: str = ""
    style: str = "balanced"
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
    vol_multiplier: float = 1.3

    min_confidence: float = 70.0

    time_filter: TimeFilter = field(default_factory=TimeFilter)
    custom_indicator_code: str = ""


# ─────────────────────────────────────────────────────────────
#  5 СТРАТЕГИИ
# ─────────────────────────────────────────────────────────────

def _tf_london_ny():
    return TimeFilter(enabled=True, sessions=[
        {"name": "London",   "start": "07:00", "end": "12:00"},
        {"name": "New York", "start": "13:00", "end": "21:00"},
    ])

def _tf_ny():
    return TimeFilter(enabled=True, sessions=[
        {"name": "New York", "start": "14:30", "end": "21:00"},
    ])

def _tf_asian():
    return TimeFilter(enabled=True, sessions=[
        {"name": "Asian",  "start": "00:00", "end": "08:00"},
        {"name": "London", "start": "07:00", "end": "16:00"},
    ])

def _tf_off():
    return TimeFilter(enabled=False)


STRATEGY_TEMPLATES = {
    "Quantum Scalper": StrategyConfig(
        name="Quantum Scalper",
        description="Агресивен скалп — бързи сделки, малки TP/SL.",
        style="scalp", timeframes=["1m","5m"],
        rsi_period=7, rsi_oversold=30.0, rsi_overbought=70.0,
        ema_fast=5, ema_medium=13, ema_slow=34,
        macd_fast=8, macd_slow=17, macd_signal=9,
        bb_period=14, bb_std=1.8, atr_period=7,
        vol_multiplier=1.5, min_confidence=65.0,
        time_filter=_tf_ny(),
    ),
    "NEXUS SMC Elite": StrategyConfig(
        name="NEXUS SMC Elite",
        description="Smart Money Concepts + Order Flow анализ.",
        style="aggressive", timeframes=["15m","1h"],
        rsi_period=14, rsi_oversold=35.0, rsi_overbought=65.0,
        ema_fast=9, ema_medium=21, ema_slow=50,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        vol_multiplier=1.4, min_confidence=72.0,
        time_filter=_tf_london_ny(),
    ),
    "Titan Trend": StrategyConfig(
        name="Titan Trend",
        description="Следва основния тренд. Triple EMA + MACD.",
        style="trend", timeframes=["1h","4h"],
        rsi_period=14, rsi_oversold=40.0, rsi_overbought=60.0,
        ema_fast=21, ema_medium=50, ema_slow=200,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        vol_multiplier=1.2, min_confidence=75.0,
        time_filter=_tf_london_ny(),
    ),
    "Phoenix Reversal": StrategyConfig(
        name="Phoenix Reversal",
        description="Улавя обрати при изчерпване. RSI + BB.",
        style="balanced", timeframes=["30m","1h"],
        rsi_period=14, rsi_oversold=25.0, rsi_overbought=75.0,
        ema_fast=9, ema_medium=21, ema_slow=55,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.5, atr_period=14,
        vol_multiplier=1.3, min_confidence=73.0,
        time_filter=_tf_asian(),
    ),
    "Iron Shield": StrategyConfig(
        name="Iron Shield",
        description="Балансирана и безопасна. Малко сделки, висока точност.",
        style="safe", timeframes=["4h","1d"],
        rsi_period=21, rsi_oversold=30.0, rsi_overbought=70.0,
        ema_fast=20, ema_medium=50, ema_slow=200,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=21,
        vol_multiplier=1.5, min_confidence=80.0,
        time_filter=_tf_off(),
    ),
}


# ─────────────────────────────────────────────────────────────
#  ВГРАДЕНИ ИНДИКАТОРИ (без pandas-ta)
# ─────────────────────────────────────────────────────────────

class Indicators:

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9):
        e_fast   = series.ewm(span=fast,   adjust=False).mean()
        e_slow   = series.ewm(span=slow,   adjust=False).mean()
        macd_line = e_fast - e_slow
        sig_line  = macd_line.ewm(span=signal, adjust=False).mean()
        hist      = macd_line - sig_line
        return macd_line, sig_line, hist

    @staticmethod
    def bollinger(series: pd.Series, period=20, std=2.0):
        mid   = series.rolling(period).mean()
        sigma = series.rolling(period).std()
        return mid + std * sigma, mid, mid - std * sigma

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k=14, d=3) -> tuple:
        lo_k  = low.rolling(k).min()
        hi_k  = high.rolling(k).max()
        stoch_k = 100 * (close - lo_k) / (hi_k - lo_k).replace(0, np.nan)
        stoch_d = stoch_k.rolling(d).mean()
        return stoch_k, stoch_d


# ─────────────────────────────────────────────────────────────
#  INDICATOR ENGINE
# ─────────────────────────────────────────────────────────────

class IndicatorEngine:

    def compute(self, df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
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

        df["stoch_k"], df["stoch_d"] = ind.stochastic(h, lo, c, cfg.stoch_k, cfg.stoch_d)

        df["vol_ma"]     = v.rolling(cfg.vol_ma_period).mean()
        df["vol_ratio"]  = v / df["vol_ma"].replace(0, np.nan)

        if cfg.custom_indicator_code.strip():
            df = self._run_custom(df, cfg.custom_indicator_code)

        return df.dropna(subset=["rsi", "ema_fast"])

    @staticmethod
    def _run_custom(df, code):
        try:
            local_ns = {"df": df.copy(), "pd": pd, "np": np}
            exec(code, local_ns)
            df = local_ns.get("df", df)
        except Exception as e:
            logger.error(f"Custom indicator error: {e}")
        return df


# ─────────────────────────────────────────────────────────────
#  SIGNAL GENERATOR
# ─────────────────────────────────────────────────────────────

class SignalGenerator:

    def generate(self, df: pd.DataFrame, cfg: StrategyConfig) -> dict:
        if df.empty or len(df) < 2:
            return self._hold("Недостатъчно данни")

        allowed, reason = cfg.time_filter.is_allowed()
        if not allowed:
            return self._hold(f"TimeFilter: {reason}")

        last = df.iloc[-1]
        prev = df.iloc[-2]
        vl, vs, reasons = 0, 0, []

        # RSI
        rsi = last.get("rsi", 50)
        if rsi < cfg.rsi_oversold:
            vl += 2; reasons.append(f"RSI={rsi:.1f} oversold")
        elif rsi > cfg.rsi_overbought:
            vs += 2; reasons.append(f"RSI={rsi:.1f} overbought")

        # EMA
        ef  = last.get("ema_fast",   0)
        em  = last.get("ema_medium", 0)
        es  = last.get("ema_slow",   0)
        cur = last.get("close",      0)
        if ef > em > es:
            vl += 2; reasons.append("EMA bullish alignment")
        elif ef < em < es:
            vs += 2; reasons.append("EMA bearish alignment")
        if cur > ef: vl += 1
        else:        vs += 1

        # MACD
        ml  = last.get("macd",        0)
        ms_ = last.get("macd_signal", 0)
        pml = prev.get("macd",        0)
        pms = prev.get("macd_signal", 0)
        if pml < pms and ml > ms_:
            vl += 2; reasons.append("MACD crossover UP")
        elif pml > pms and ml < ms_:
            vs += 2; reasons.append("MACD crossover DOWN")
        elif ml > ms_: vl += 1
        else:          vs += 1

        # Bollinger
        bbu = last.get("bb_upper", 0)
        bbl = last.get("bb_lower", 0)
        if cur < bbl:
            vl += 2; reasons.append("Под BB долна лента")
        elif cur > bbu:
            vs += 2; reasons.append("Над BB горна лента")

        # Stochastic
        sk  = last.get("stoch_k", 50)
        sd_ = last.get("stoch_d", 50)
        psk = prev.get("stoch_k", 50)
        psd = prev.get("stoch_d", 50)
        if sk < 20:
            vl += 1; reasons.append(f"Stoch oversold {sk:.0f}")
        elif sk > 80:
            vs += 1; reasons.append(f"Stoch overbought {sk:.0f}")
        if psk < psd and sk > sd_:
            vl += 1; reasons.append("Stoch crossover UP")
        elif psk > psd and sk < sd_:
            vs += 1; reasons.append("Stoch crossover DOWN")

        # Volume
        vr = last.get("vol_ratio", 1.0)
        if vr >= cfg.vol_multiplier:
            if vl >= vs: vl += 1
            else:        vs += 1
            reasons.append(f"Vol spike {vr:.1f}x")

        # Решение
        threshold = 4 if cfg.style in ["safe","balanced"] else 3

        if vl >= threshold and vl > vs:
            conf = min(97, 60 + (vl / 10) * 35)
            if conf >= cfg.min_confidence:
                return {"signal": "LONG",  "confidence": round(conf,1),
                        "votes_long": vl, "votes_short": vs,
                        "reasons": reasons,
                        "atr": last.get("atr"), "rsi": rsi}

        if vs >= threshold and vs > vl:
            conf = min(97, 60 + (vs / 10) * 35)
            if conf >= cfg.min_confidence:
                return {"signal": "SHORT", "confidence": round(conf,1),
                        "votes_long": vl, "votes_short": vs,
                        "reasons": reasons,
                        "atr": last.get("atr"), "rsi": rsi}

        return self._hold(f"Гласове L={vl} S={vs} < {threshold}")

    @staticmethod
    def _hold(reason):
        return {"signal":"HOLD","confidence":50,"votes_long":0,
                "votes_short":0,"reasons":[reason],"atr":None,"rsi":None}


# ─────────────────────────────────────────────────────────────
#  STRATEGY MANAGER
# ─────────────────────────────────────────────────────────────

class StrategyManager:

    def __init__(self):
        import copy
        self._templates   = {k: copy.deepcopy(v) for k, v in STRATEGY_TEMPLATES.items()}
        self._active_name = "NEXUS SMC Elite"
        self._indicators  = IndicatorEngine()
        self._signals     = SignalGenerator()

    @property
    def active(self) -> StrategyConfig:
        return self._templates[self._active_name]

    @property
    def names(self) -> list:
        return list(self._templates.keys())

    def select(self, name: str):
        if name in self._templates:
            self._active_name = name

    def update_param(self, param: str, value):
        if hasattr(self.active, param):
            setattr(self.active, param, value)

    def update_time_filter(self, **kwargs):
        tf = self.active.time_filter
        for k, v in kwargs.items():
            if hasattr(tf, k):
                setattr(tf, k, v)

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._indicators.compute(df.copy(), self.active)

    def signal(self, df: pd.DataFrame) -> dict:
        return self._signals.generate(df, self.active)

    def get_config_dict(self) -> dict:
        cfg = self.active
        return {
            "name": cfg.name, "description": cfg.description,
            "style": cfg.style, "timeframes": cfg.timeframes,
            "rsi_period": cfg.rsi_period, "rsi_oversold": cfg.rsi_oversold,
            "rsi_overbought": cfg.rsi_overbought,
            "ema_fast": cfg.ema_fast, "ema_medium": cfg.ema_medium,
            "ema_slow": cfg.ema_slow,
            "macd_fast": cfg.macd_fast, "macd_slow": cfg.macd_slow,
            "macd_signal": cfg.macd_signal,
            "bb_period": cfg.bb_period, "bb_std": cfg.bb_std,
            "atr_period": cfg.atr_period,
            "vol_multiplier": cfg.vol_multiplier,
            "min_confidence": cfg.min_confidence,
            "time_filter_on": cfg.time_filter.enabled,
            "sessions": cfg.time_filter.sessions,
            "custom_start": cfg.time_filter.custom_start,
            "custom_end": cfg.time_filter.custom_end,
        }
