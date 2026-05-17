"""
logic.py
══════════════════════════════════════════════════════════════
AI Мозък на бота:
  • Корелационен филтър (DXY & ETH sentiment)
  • Multi-timeframe trend analysis
  • OpenAI/Gemini анализ (по избор)
  • Финално решение: LONG / SHORT / HOLD + confidence
══════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import logging
import os
from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  MARKET SENTIMENT (Корелационен филтър)
# ─────────────────────────────────────────────────────────────

class CorrelationFilter:
    """
    Проверява пазарния сентимент преди да разреши сигнал.

    Логика:
    ──────
    1. DXY (Индекс на долара):
       • Ако DXY расте бързо  → блокирай LONG сигнали за крипто
       • Ако DXY пада бързо   → потвърди LONG, блокирай SHORT

    2. ETH (водещ индикатор за крипто пазара):
       • Ако ETH е в силен uptrend → добавя confidence към BTC LONG
       • Ако ETH пада             → предупреждение за BTC LONG

    3. BTC Dominance (по избор):
       • Ако BTC.D расте → altcoins може да падат

    Данни: подаваш OHLCV DataFrames отвън (от engine.py)
    """

    def __init__(
        self,
        dxy_threshold_pct: float  = 0.3,   # % промяна за 4ч → "бърз ръст на DXY"
        eth_corr_window:   int    = 20,     # свещи за ETH корелация
        enabled:           bool   = True,
    ):
        self.dxy_threshold = dxy_threshold_pct
        self.eth_window    = eth_corr_window
        self.enabled       = enabled

    def check(
        self,
        signal:    str,
        symbol:    str,
        eth_df:    Optional[pd.DataFrame] = None,
        dxy_df:    Optional[pd.DataFrame] = None,
        btcdom_df: Optional[pd.DataFrame] = None,
    ) -> dict:
        """
        Параметри
        ---------
        signal    : "LONG" | "SHORT" от стратегията
        symbol    : напр. "BTC/USDT", "ETH/USDT"
        eth_df    : OHLCV на ETH (за BTC и altcoins)
        dxy_df    : OHLCV на DXY (ако е достъпен)
        btcdom_df : OHLCV на BTC.D (по избор)

        Връща
        ------
        {
          "allowed":     bool,
          "confidence_adj": float  (−20 до +10),
          "reasons":     list[str],
          "sentiment":   "BULLISH" | "BEARISH" | "NEUTRAL",
        }
        """
        if not self.enabled:
            return {"allowed": True, "confidence_adj": 0,
                    "reasons": ["Корелационен филтър изключен"], "sentiment": "NEUTRAL"}

        reasons    = []
        adjustments = 0.0
        blocked    = False
        sentiment  = "NEUTRAL"

        # ── DXY Анализ ──────────────────────────────────────
        if dxy_df is not None and len(dxy_df) >= 5:
            dxy_change = self._pct_change(dxy_df, periods=4)
            if dxy_change > self.dxy_threshold:
                # DXY расте силно → риск за крипто LONG
                reasons.append(f"⚠️ DXY +{dxy_change:.2f}% — долар се укрепва")
                adjustments -= 15
                if signal == "LONG":
                    blocked = True
                    reasons.append("🚫 LONG блокиран от DXY силен ръст")
                sentiment = "BEARISH"
            elif dxy_change < -self.dxy_threshold:
                # DXY пада → благоприятно за крипто
                reasons.append(f"✅ DXY {dxy_change:.2f}% — долар отслабва")
                adjustments += 8
                sentiment = "BULLISH"
            else:
                reasons.append(f"DXY неутрален: {dxy_change:.2f}%")
        else:
            reasons.append("DXY данни недостъпни — пропускане на DXY филтър")

        # ── ETH Корелация ────────────────────────────────────
        is_btc = "BTC" in symbol.upper()
        is_alt = not is_btc and "ETH" not in symbol.upper()

        if eth_df is not None and len(eth_df) >= self.eth_window:
            eth_trend = self._trend_direction(eth_df, self.eth_window)
            eth_mom   = self._pct_change(eth_df, periods=4)

            if eth_trend == "UP":
                reasons.append(f"✅ ETH в uptrend (+{eth_mom:.2f}%)")
                if signal == "LONG":
                    adjustments += 7
                    sentiment = max_sentiment(sentiment, "BULLISH")
            elif eth_trend == "DOWN":
                reasons.append(f"⚠️ ETH в downtrend ({eth_mom:.2f}%)")
                if signal == "LONG":
                    adjustments -= 10
                    if is_btc or is_alt:
                        blocked = True
                        reasons.append("🚫 LONG блокиран — ETH слаб")
                    sentiment = min_sentiment(sentiment, "BEARISH")
            else:
                reasons.append(f"ETH неутрален: {eth_mom:.2f}%")
        else:
            reasons.append("ETH данни недостъпни")

        # ── BTC Dominance (за алткойн сигнали) ──────────────
        if is_alt and btcdom_df is not None and len(btcdom_df) >= 5:
            dom_change = self._pct_change(btcdom_df, periods=6)
            if dom_change > 0.5:
                reasons.append(f"⚠️ BTC.D расте +{dom_change:.2f}% — натиск върху алткойни")
                if signal == "LONG":
                    adjustments -= 8
                    blocked = True
                    reasons.append("🚫 Alt LONG блокиран от BTC.D ръст")

        return {
            "allowed":        not blocked,
            "confidence_adj": round(adjustments, 1),
            "reasons":        reasons,
            "sentiment":      sentiment,
        }

    @staticmethod
    def _pct_change(df: pd.DataFrame, periods: int = 1) -> float:
        if len(df) < periods + 1:
            return 0.0
        close = df["close"].values
        return (close[-1] - close[-periods-1]) / close[-periods-1] * 100

    @staticmethod
    def _trend_direction(df: pd.DataFrame, window: int) -> str:
        """Прост тренд: UP / DOWN / NEUTRAL."""
        if len(df) < window:
            return "NEUTRAL"
        sl = df["close"].values[-window:]
        x  = np.arange(len(sl))
        slope = np.polyfit(x, sl, 1)[0]
        mean  = sl.mean()
        if slope > mean * 0.0005:
            return "UP"
        if slope < -mean * 0.0005:
            return "DOWN"
        return "NEUTRAL"


def max_sentiment(a: str, b: str) -> str:
    order = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}
    return a if order.get(a, 1) >= order.get(b, 1) else b

def min_sentiment(a: str, b: str) -> str:
    order = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}
    return a if order.get(a, 1) <= order.get(b, 1) else b


# ─────────────────────────────────────────────────────────────
#  MULTI-TIMEFRAME TREND
# ─────────────────────────────────────────────────────────────

class MultiTimeframeTrend:
    """
    Анализира тренда на всички таймфреймове.
    Връща обобщена картина: bullish / bearish / mixed.
    """

    TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

    def analyze(self, data: dict[str, pd.DataFrame]) -> dict:
        """
        data: { "1m": df, "1h": df, "4h": df, ... }
        """
        results = {}
        score   = 0  # +1 bullish, -1 bearish per TF

        for tf, df in data.items():
            if df is None or len(df) < 20:
                results[tf] = {"trend": "N/A", "ema_align": None, "rsi": None}
                continue

            close = df["close"].values
            rsi   = self._rsi(close)
            ema9  = self._ema(close, 9)
            ema21 = self._ema(close, 21)
            ema50 = self._ema(close, 50) if len(close) >= 50 else ema21

            bullish = sum([
                ema9  > ema21,
                ema21 > ema50,
                close[-1] > ema9,
                rsi > 50,
            ])

            if bullish >= 3:
                trend = "BULLISH 🟢"
                score += 1
            elif bullish <= 1:
                trend = "BEARISH 🔴"
                score -= 1
            else:
                trend = "NEUTRAL ⚪"

            results[tf] = {
                "trend":    trend,
                "rsi":      round(rsi, 1),
                "ema9":     round(ema9, 2),
                "ema21":    round(ema21, 2),
                "price":    round(close[-1], 2),
                "bullish_votes": bullish,
            }

        total = len(data)
        if total > 0:
            pct = score / total * 100
        else:
            pct = 0

        overall = "STRONGLY BULLISH" if pct > 60 else \
                  "BULLISH"          if pct > 20 else \
                  "STRONGLY BEARISH" if pct < -60 else \
                  "BEARISH"          if pct < -20 else "MIXED"

        return {"timeframes": results, "overall": overall, "score": score, "total": total}

    @staticmethod
    def _ema(prices: np.ndarray, period: int) -> float:
        if len(prices) < period:
            return float(prices[-1])
        k = 2 / (period + 1)
        v = float(np.mean(prices[:period]))
        for p in prices[period:]:
            v = float(p) * k + v * (1 - k)
        return v

    @staticmethod
    def _rsi(prices: np.ndarray, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)[-period:]
        gains  = deltas[deltas > 0].sum() / period
        losses = -deltas[deltas < 0].sum() / period
        if losses == 0:
            return 100.0
        return 100 - (100 / (1 + gains / losses))


# ─────────────────────────────────────────────────────────────
#  AI BRAIN
# ─────────────────────────────────────────────────────────────

class AIBrain:
    """
    Главен мозък на бота.
    Комбинира:
      1. Сигнал от стратегията
      2. Корелационен филтър
      3. Multi-TF тренд
      4. (По избор) OpenAI анализ

    Финално решение: LONG / SHORT / HOLD + confidence
    """

    def __init__(
        self,
        openai_key: Optional[str] = None,
        use_ai:     bool = False,
    ):
        self.corr_filter = CorrelationFilter()
        self.mtf_trend   = MultiTimeframeTrend()
        self.use_ai      = use_ai
        self._openai_key = openai_key or os.getenv("OPENAI_API_KEY")

    def decide(
        self,
        strategy_signal: dict,
        symbol: str,
        mtf_data: Optional[dict[str, pd.DataFrame]] = None,
        eth_df:   Optional[pd.DataFrame] = None,
        dxy_df:   Optional[pd.DataFrame] = None,
    ) -> dict:
        """
        Взема финалното решение.

        Параметри
        ---------
        strategy_signal : изход от StrategyManager.signal()
        symbol          : "BTC/USDT" и т.н.
        mtf_data        : { "1h": df, "4h": df, ... }
        eth_df          : DataFrame на ETH за корелация
        dxy_df          : DataFrame на DXY (ако е наличен)
        """
        sig  = strategy_signal.get("signal", "HOLD")
        conf = strategy_signal.get("confidence", 50.0)
        reasons = list(strategy_signal.get("reasons", []))

        # ── Корелационен филтър ──────────────────────────────
        corr = self.corr_filter.check(
            signal=sig, symbol=symbol,
            eth_df=eth_df, dxy_df=dxy_df,
        )
        conf += corr["confidence_adj"]
        conf  = max(0, min(100, conf))
        reasons += corr["reasons"]

        if not corr["allowed"]:
            return self._build(
                "HOLD", conf, reasons,
                blocked=True, block_reason="Корелационен филтър блокира",
                sentiment=corr["sentiment"],
            )

        # ── Multi-TF анализ ──────────────────────────────────
        mtf_result = {"overall": "N/A", "timeframes": {}}
        if mtf_data:
            mtf_result = self.mtf_trend.analyze(mtf_data)
            overall    = mtf_result.get("overall", "N/A")

            if sig == "LONG" and "BEARISH" in overall:
                conf -= 12
                reasons.append(f"⚠️ MTF тренд: {overall} — намален confidence")
            elif sig == "SHORT" and "BULLISH" in overall:
                conf -= 12
                reasons.append(f"⚠️ MTF тренд: {overall} — намален confidence")
            elif sig == "LONG" and "BULLISH" in overall:
                conf += 8
                reasons.append(f"✅ MTF тренд потвърждава: {overall}")
            elif sig == "SHORT" and "BEARISH" in overall:
                conf += 8
                reasons.append(f"✅ MTF тренд потвърждава: {overall}")

            conf = max(0, min(100, conf))

        # ── OpenAI анализ (по избор) ─────────────────────────
        ai_comment = ""
        if self.use_ai and self._openai_key and sig != "HOLD":
            ai_comment = self._ask_openai(sig, symbol, conf, reasons, mtf_result)
            if ai_comment:
                reasons.append(f"🤖 AI: {ai_comment}")

        # ── Финален праг за confidence ───────────────────────
        if sig != "HOLD" and conf < 55:
            sig = "HOLD"
            reasons.append(f"Confidence {conf:.1f}% под минималния праг")

        return self._build(sig, conf, reasons,
                           mtf=mtf_result, sentiment=corr["sentiment"],
                           ai_comment=ai_comment)

    def _ask_openai(
        self, signal: str, symbol: str, conf: float,
        reasons: list, mtf: dict,
    ) -> str:
        """Изпраща контекст към OpenAI и получава кратко мнение."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._openai_key)

            mtf_summary = ""
            for tf, data in mtf.get("timeframes", {}).items():
                mtf_summary += f"  {tf}: {data.get('trend','N/A')} RSI={data.get('rsi','N/A')}\n"

            prompt = f"""Ти си AI трейдинг асистент. Анализирай следния сигнал и дай КРАТКО мнение (1–2 изречения):

Символ: {symbol}
Сигнал: {signal}
Confidence: {conf:.1f}%
Причини:
{chr(10).join(f'- {r}' for r in reasons[:6])}

Multi-TF тренд:
{mtf_summary}

Отговори само дали потвърждаваш сигнала или препоръчваш внимание. Максимум 2 изречения на български."""

            response = client.chat.completions.create(
                model    = "gpt-4o-mini",
                messages = [{"role": "user", "content": prompt}],
                max_tokens = 120,
                temperature = 0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI error: {e}")
            return ""

    @staticmethod
    def _build(
        signal: str,
        confidence: float,
        reasons: list,
        blocked: bool = False,
        block_reason: str = "",
        mtf: dict = None,
        sentiment: str = "NEUTRAL",
        ai_comment: str = "",
    ) -> dict:
        return {
            "signal":     signal,
            "confidence": round(min(100, max(0, confidence)), 1),
            "reasons":    reasons,
            "blocked":    blocked,
            "block_reason": block_reason,
            "mtf":        mtf or {},
            "sentiment":  sentiment,
            "ai_comment": ai_comment,
            "timestamp":  datetime.utcnow().isoformat(),
        }


# NAN SAFETY PATCH
def sanitize_dataframe(df):
    if df is None:
        return None
    return df.fillna(0)
