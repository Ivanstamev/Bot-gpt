"""
strategy_manager.py — NEXUS BOT PRO v3
Нова сигнална логика с реален edge:
- Влизаме само по посока на тренда (EMA alignment)
- Изискваме momentum потвърждение (MACD + RSI заедно)
- Стохастик за точния тайминг на входа
- Volume spike за потвърждение
- Минимален win rate цел: 45-55%
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
            return True, "Изключен"
        now = dt or datetime.utcnow()
        cur = now.strftime("%H:%M")
        if self.custom_enabled:
            return self.custom_start <= cur <= self.custom_end, "Ръчен"
        for s in self.sessions:
            if s["start"] <= cur <= s["end"]:
                return True, s["name"]
        return False, "Извън сесия"

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
    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 40.0
    rsi_overbought: float = 60.0
    # EMA
    ema_fast: int = 9
    ema_medium: int = 21
    ema_slow: int = 50
    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # BB
    bb_period: int = 20
    bb_std: float = 2.0
    # ATR
    atr_period: int = 14
    # Stoch
    stoch_k: int = 14
    stoch_d: int = 3
    # Volume
    vol_ma_period: int = 20
    vol_multiplier: float = 1.0
    # Signal
    min_confidence: float = 70.0
    # TP/SL
    atr_tp_mult: float = 3.5
    atr_sl_mult: float = 1.0
    time_filter: TimeFilter = field(default_factory=TimeFilter)
    custom_indicator_code: str = ""


# ── Фабрични настройки за риск ──────────────────────────────
STRATEGY_RISK_DEFAULTS = {
    "Quantum Scalper": {
        "risk_pct": 8.0, "leverage": 25, "use_atr": True,
        "atr_tp_mult": 3.0, "atr_sl_mult": 0.7,
        "tp_pct": 5.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_pct": 0.8,
        "trailing_atr_mult": 1.2, "trailing_activation_pct": 1.0,
        "daily_loss_limit_pct": 20.0, "max_consecutive_losses": 10,
        "max_position_pct": 40.0,
    },
    "NEXUS SMC Elite": {
        "risk_pct": 7.0, "leverage": 25, "use_atr": True,
        "atr_tp_mult": 3.5, "atr_sl_mult": 0.8,
        "tp_pct": 6.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 1.5, "trailing_activation_pct": 1.2,
        "daily_loss_limit_pct": 18.0, "max_consecutive_losses": 8,
        "max_position_pct": 40.0,
    },
    "Titan Trend": {
        "risk_pct": 5.0, "leverage": 20, "use_atr": True,
        "atr_tp_mult": 4.5, "atr_sl_mult": 1.0,
        "tp_pct": 7.0, "sl_pct": 1.5,
        "trailing_stop": True, "trailing_pct": 1.2,
        "trailing_atr_mult": 2.0, "trailing_activation_pct": 1.5,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 7,
        "max_position_pct": 35.0,
    },
    "Phoenix Reversal": {
        "risk_pct": 4.5, "leverage": 15, "use_atr": True,
        "atr_tp_mult": 4.0, "atr_sl_mult": 0.9,
        "tp_pct": 6.0, "sl_pct": 1.2,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 1.8, "trailing_activation_pct": 1.2,
        "daily_loss_limit_pct": 15.0, "max_consecutive_losses": 6,
        "max_position_pct": 35.0,
    },
    "Iron Shield": {
        "risk_pct": 3.5, "leverage": 12, "use_atr": True,
        "atr_tp_mult": 4.5, "atr_sl_mult": 1.0,
        "tp_pct": 5.0, "sl_pct": 1.0,
        "trailing_stop": True, "trailing_pct": 1.0,
        "trailing_atr_mult": 2.2, "trailing_activation_pct": 1.5,
        "daily_loss_limit_pct": 12.0, "max_consecutive_losses": 5,
        "max_position_pct": 30.0,
    },
}


STRATEGY_TEMPLATES = {
    "Quantum Scalper": StrategyConfig(
        name="Quantum Scalper",
        description="Скалп с висок леверидж. Цел: 2x за 7–10 дни.",
        style="scalp", target_days=8, timeframes=["1m","5m"],
        rsi_period=7, rsi_oversold=38.0, rsi_overbought=62.0,
        ema_fast=5, ema_medium=13, ema_slow=34,
        macd_fast=8, macd_slow=17, macd_signal=9,
        bb_period=14, bb_std=1.8, atr_period=7,
        stoch_k=9, stoch_d=3,
        vol_multiplier=1.0, min_confidence=68.0,
        atr_tp_mult=3.0, atr_sl_mult=0.7,
        time_filter=TimeFilter(enabled=False),
    ),
    "NEXUS SMC Elite": StrategyConfig(
        name="NEXUS SMC Elite",
        description="Smart Money концепция. Цел: 2x за 10–15 дни.",
        style="aggressive", target_days=12, timeframes=["15m","1h"],
        rsi_period=14, rsi_oversold=40.0, rsi_overbought=60.0,
        ema_fast=8, ema_medium=21, ema_slow=55,
        macd_fast=10, macd_slow=22, macd_signal=7,
        bb_period=20, bb_std=2.0, atr_period=14,
        stoch_k=14, stoch_d=3,
        vol_multiplier=1.0, min_confidence=70.0,
        atr_tp_mult=3.5, atr_sl_mult=0.8,
        time_filter=TimeFilter(enabled=False),
    ),
    "Titan Trend": StrategyConfig(
        name="Titan Trend",
        description="Тренд следване. Цел: 2x за 15–20 дни.",
        style="trend", target_days=17, timeframes=["1h","4h"],
        rsi_period=14, rsi_oversold=42.0, rsi_overbought=58.0,
        ema_fast=20, ema_medium=50, ema_slow=100,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        stoch_k=14, stoch_d=3,
        vol_multiplier=1.0, min_confidence=70.0,
        atr_tp_mult=4.5, atr_sl_mult=1.0,
        time_filter=TimeFilter(enabled=False),
    ),
    "Phoenix Reversal": StrategyConfig(
        name="Phoenix Reversal",
        description="Обрати при изчерпване. Цел: 2x за 20–25 дни.",
        style="balanced", target_days=22, timeframes=["30m","1h"],
        rsi_period=14, rsi_oversold=38.0, rsi_overbought=62.0,
        ema_fast=9, ema_medium=21, ema_slow=50,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        stoch_k=9, stoch_d=3,
        vol_multiplier=1.0, min_confidence=67.0,
        atr_tp_mult=4.0, atr_sl_mult=0.9,
        time_filter=TimeFilter(enabled=False),
    ),
    "Iron Shield": StrategyConfig(
        name="Iron Shield",
        description="Безопасна с висока точност. Цел: 2x за 25–30 дни.",
        style="safe", target_days=28, timeframes=["4h","1d"],
        rsi_period=14, rsi_oversold=40.0, rsi_overbought=60.0,
        ema_fast=20, ema_medium=50, ema_slow=100,
        macd_fast=12, macd_slow=26, macd_signal=9,
        bb_period=20, bb_std=2.0, atr_period=14,
        stoch_k=9, stoch_d=3,
        vol_multiplier=1.0, min_confidence=67.0,
        atr_tp_mult=4.5, atr_sl_mult=1.0,
        time_filter=TimeFilter(enabled=False),
    ),
}


class Indicators:
    @staticmethod
    def ema(s, p): return s.ewm(span=p, adjust=False).mean()

    @staticmethod
    def rsi(s, p=14):
        d = s.diff()
        g = d.clip(lower=0).ewm(span=p, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
        return 100 - 100/(1 + g/l.replace(0, np.nan))

    @staticmethod
    def macd(s, f=12, sl=26, sig=9):
        m = s.ewm(span=f,adjust=False).mean() - s.ewm(span=sl,adjust=False).mean()
        ms = m.ewm(span=sig,adjust=False).mean()
        return m, ms, m-ms

    @staticmethod
    def bollinger(s, p=20, std=2.0):
        mid = s.rolling(p).mean()
        sg  = s.rolling(p).std()
        return mid+std*sg, mid, mid-std*sg

    @staticmethod
    def atr(h, l, c, p=14):
        tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        return tr.ewm(span=p, adjust=False).mean()

    @staticmethod
    def stoch(h, l, c, k=14, d=3):
        lk = l.rolling(k).min()
        hk = h.rolling(k).max()
        sk = 100*(c-lk)/(hk-lk).replace(0,np.nan)
        return sk, sk.rolling(d).mean()


class IndicatorEngine:
    def compute(self, df, cfg):
        if len(df) < 60: return df
        ind = Indicators()
        c,h,lo,v = df["close"],df["high"],df["low"],df["volume"]

        df["rsi"]        = ind.rsi(c, cfg.rsi_period)
        df["ema_fast"]   = ind.ema(c, cfg.ema_fast)
        df["ema_medium"] = ind.ema(c, cfg.ema_medium)
        df["ema_slow"]   = ind.ema(c, cfg.ema_slow)

        ml,ms,mh          = ind.macd(c, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
        df["macd"]        = ml
        df["macd_signal"] = ms
        df["macd_hist"]   = mh

        df["bb_upper"],df["bb_mid"],df["bb_lower"] = ind.bollinger(c, cfg.bb_period, cfg.bb_std)
        df["bb_width"] = (df["bb_upper"]-df["bb_lower"])/df["bb_mid"]

        df["atr"]     = ind.atr(h, lo, c, cfg.atr_period)
        df["atr_pct"] = df["atr"]/c*100

        df["stoch_k"],df["stoch_d"] = ind.stoch(h, lo, c, cfg.stoch_k, cfg.stoch_d)

        df["vol_ma"]    = v.rolling(cfg.vol_ma_period).mean()
        df["vol_ratio"] = v/df["vol_ma"].replace(0,np.nan)

        # Допълнителни
        df["ema_200"]   = ind.ema(c, 200)
        df["rsi_ma"]    = df["rsi"].rolling(5).mean()  # RSI smoothed

        if cfg.custom_indicator_code.strip():
            try:
                ns = {"df": df.copy(), "pd": pd, "np": np}
                exec(cfg.custom_indicator_code, ns)
                df = ns.get("df", df)
            except Exception as e:
                logger.error(f"Custom: {e}")

        return df.dropna(subset=["rsi","ema_fast","macd","stoch_k"])


class SignalGenerator:
    """
    Нова логика с реален trading edge:

    LONG условия (трябват 3+ от 4):
      1. ТРЕНД: EMA fast > EMA medium > EMA slow (bullish alignment)
      2. MOMENTUM: MACD line > signal AND histogram расте
      3. ТАЙМИНГ: RSI излиза от oversold (35-50) OR Stoch cross от <30
      4. ПОТВЪРЖДЕНИЕ: Цена > EMA fast + volume > MA

    SHORT условия — огледално.

    Confluence score = брой изпълнени условия → confidence
    """

    def generate(self, df, cfg):
        if df.empty or len(df) < 3:
            return self._hold("Недостатъчно данни")

        allowed, reason = cfg.time_filter.is_allowed()
        if not allowed:
            return self._hold(f"TimeFilter: {reason}")

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 2 else prev

        c   = last.get("close",       0)
        ef  = last.get("ema_fast",    0)
        em  = last.get("ema_medium",  0)
        es  = last.get("ema_slow",    0)
        e200= last.get("ema_200",     0)
        pef = prev.get("ema_fast",    0)
        pem = prev.get("ema_medium",  0)

        rsi    = last.get("rsi",        50)
        prsi   = prev.get("rsi",        50)
        rsi_ma = last.get("rsi_ma",     50)

        ml   = last.get("macd",        0)
        ms   = last.get("macd_signal", 0)
        mh   = last.get("macd_hist",   0)
        pml  = prev.get("macd",        0)
        pms  = prev.get("macd_signal", 0)
        pmh  = prev.get("macd_hist",   0)
        pmh2 = prev2.get("macd_hist",  0)

        sk   = last.get("stoch_k",  50)
        sd   = last.get("stoch_d",  50)
        psk  = prev.get("stoch_k",  50)
        psd  = prev.get("stoch_d",  50)

        bbu  = last.get("bb_upper", c*1.02)
        bbl  = last.get("bb_lower", c*0.98)
        bbm  = last.get("bb_mid",   c)

        vr   = last.get("vol_ratio", 1.0)
        atr_pct = last.get("atr_pct", 1.0)

        # ATR филтър — пропускаме при flat пазар
        if atr_pct < 0.1:
            return self._hold("Flat пазар — ATR твърде нисък")

        # ═══════════════════════════════════════════════════════
        # LONG АНАЛИЗ
        # ═══════════════════════════════════════════════════════
        long_score = 0
        long_reasons = []

        # 1. ТРЕНД — EMA alignment (задължително условие за trend стратегии)
        if ef > em and em > es:
            long_score += 2
            long_reasons.append("✅ EMA bullish тренд")
        elif ef > em:
            long_score += 1
            long_reasons.append("〽️ Частичен bullish тренд")

        # EMA crossover — силен сигнал
        if pef <= pem and ef > em:
            long_score += 2
            long_reasons.append("🔥 EMA Golden Cross")

        # Цената над 200 EMA = macro bullish
        if c > e200 and e200 > 0:
            long_score += 1
            long_reasons.append("📈 Над EMA200")

        # 2. MOMENTUM — MACD
        if pml < pms and ml > ms:  # crossover
            long_score += 3
            long_reasons.append("🔥 MACD bullish crossover")
        elif ml > ms and ml > 0:   # above zero
            long_score += 2
            long_reasons.append("✅ MACD bullish над 0")
        elif ml > ms:              # bullish но под 0
            long_score += 1
            long_reasons.append("〽️ MACD bullish")

        # MACD histogram расте (momentum набира скорост)
        if mh > pmh > pmh2 and mh > 0:
            long_score += 2
            long_reasons.append("⚡ MACD hist ускорява")
        elif mh > pmh and mh > 0:
            long_score += 1
            long_reasons.append("✅ MACD hist расте")

        # 3. ТАЙМИНГ — RSI + Stoch
        # RSI излиза от oversold зона
        if prsi < cfg.rsi_oversold and rsi > prsi and rsi < 55:
            long_score += 3
            long_reasons.append("🔥 RSI излиза от oversold")
        elif rsi < cfg.rsi_oversold:
            long_score += 1
            long_reasons.append("〽️ RSI oversold")
        elif 45 < rsi < 60 and rsi > rsi_ma:
            long_score += 1
            long_reasons.append("✅ RSI в bullish зона")

        # Stoch crossover от oversold
        if psk < psd and sk > sd and sk < 40:
            long_score += 3
            long_reasons.append("🔥 Stoch bullish cross от дъно")
        elif sk < 25:
            long_score += 1
            long_reasons.append("〽️ Stoch oversold")
        elif sk > sd and sk < 60:
            long_score += 1
            long_reasons.append("✅ Stoch bullish")

        # 4. ПОТВЪРЖДЕНИЕ — цена + BB + volume
        if c < bbl:  # под долна BB — reversal точка
            long_score += 2
            long_reasons.append("✅ Под BB — reversal зона")
        elif c > bbm and bbu > bbm:
            long_score += 1
            long_reasons.append("✅ Над BB средна")

        if vr > 1.3:
            long_score += 2
            long_reasons.append(f"⚡ Volume spike {vr:.1f}x")
        elif vr > 1.0:
            long_score += 1

        # ═══════════════════════════════════════════════════════
        # SHORT АНАЛИЗ
        # ═══════════════════════════════════════════════════════
        short_score = 0
        short_reasons = []

        if ef < em and em < es:
            short_score += 2
            short_reasons.append("✅ EMA bearish тренд")
        elif ef < em:
            short_score += 1
            short_reasons.append("〽️ Частичен bearish тренд")

        if pef >= pem and ef < em:
            short_score += 2
            short_reasons.append("🔥 EMA Death Cross")

        if c < e200 and e200 > 0:
            short_score += 1
            short_reasons.append("📉 Под EMA200")

        if pml > pms and ml < ms:
            short_score += 3
            short_reasons.append("🔥 MACD bearish crossover")
        elif ml < ms and ml < 0:
            short_score += 2
            short_reasons.append("✅ MACD bearish под 0")
        elif ml < ms:
            short_score += 1
            short_reasons.append("〽️ MACD bearish")

        if mh < pmh < pmh2 and mh < 0:
            short_score += 2
            short_reasons.append("⚡ MACD hist ускорява надолу")
        elif mh < pmh and mh < 0:
            short_score += 1
            short_reasons.append("✅ MACD hist пада")

        if prsi > cfg.rsi_overbought and rsi < prsi and rsi > 45:
            short_score += 3
            short_reasons.append("🔥 RSI излиза от overbought")
        elif rsi > cfg.rsi_overbought:
            short_score += 1
            short_reasons.append("〽️ RSI overbought")
        elif 40 < rsi < 55 and rsi < rsi_ma:
            short_score += 1
            short_reasons.append("✅ RSI в bearish зона")

        if psk > psd and sk < sd and sk > 60:
            short_score += 3
            short_reasons.append("🔥 Stoch bearish cross от връх")
        elif sk > 75:
            short_score += 1
            short_reasons.append("〽️ Stoch overbought")
        elif sk < sd and sk > 40:
            short_score += 1
            short_reasons.append("✅ Stoch bearish")

        if c > bbu:
            short_score += 2
            short_reasons.append("✅ Над BB — reversal зона")
        elif c < bbm:
            short_score += 1
            short_reasons.append("✅ Под BB средна")

        if vr > 1.3:
            short_score += 2
            short_reasons.append(f"⚡ Volume spike {vr:.1f}x")
        elif vr > 1.0:
            short_score += 1

        # ═══════════════════════════════════════════════════════
        # РЕШЕНИЕ — минимален score за влизане
        # Scalp: 9, Aggressive: 10, Trend/Balanced: 11, Safe: 12
        # ═══════════════════════════════════════════════════════
        thresholds = {"scalp": 8, "aggressive": 9, "trend": 9, "balanced": 9, "safe": 10}
        threshold = thresholds.get(cfg.style, 10)
        max_score = 20  # теоретичен максимум

        if long_score >= threshold and long_score > short_score:
            conf = min(95, 55 + (long_score / max_score) * 40)
            if conf >= cfg.min_confidence:
                return {
                    "signal": "LONG", "confidence": round(conf, 1),
                    "votes_long": long_score, "votes_short": short_score,
                    "reasons": long_reasons[:6], "atr": last.get("atr"), "rsi": rsi,
                }

        if short_score >= threshold and short_score > long_score:
            conf = min(95, 55 + (short_score / max_score) * 40)
            if conf >= cfg.min_confidence:
                return {
                    "signal": "SHORT", "confidence": round(conf, 1),
                    "votes_long": long_score, "votes_short": short_score,
                    "reasons": short_reasons[:6], "atr": last.get("atr"), "rsi": rsi,
                }

        return self._hold(f"Score L={long_score} S={short_score} < {threshold}")

    @staticmethod
    def _hold(r):
        return {"signal":"HOLD","confidence":50,"votes_long":0,
                "votes_short":0,"reasons":[r],"atr":None,"rsi":None}


class StrategyManager:
    def __init__(self):
        import copy
        self._templates   = {k: copy.deepcopy(v) for k, v in STRATEGY_TEMPLATES.items()}
        self._active_name = "NEXUS SMC Elite"
        self._indicators  = IndicatorEngine()
        self._signals     = SignalGenerator()

    @property
    def active(self): return self._templates[self._active_name]

    @property
    def names(self): return list(self._templates.keys())

    def select(self, name):
        if name in self._templates:
            self._active_name = name

    def update_param(self, param, value):
        if hasattr(self.active, param):
            setattr(self.active, param, value)

    def reset_to_default(self, name=None):
        import copy
        t = name or self._active_name
        if t in STRATEGY_TEMPLATES:
            self._templates[t] = copy.deepcopy(STRATEGY_TEMPLATES[t])

    def update_time_filter(self, **kwargs):
        tf = self.active.time_filter
        for k, v in kwargs.items():
            if hasattr(tf, k): setattr(tf, k, v)

    def compute(self, df): return self._indicators.compute(df.copy(), self.active)
    def signal(self, df):  return self._signals.generate(df, self.active)

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
