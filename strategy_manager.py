"""
strategy_manager.py
NEXUS BOT PRO
"""

from __future__ import annotations


# ============================================================
# STRATEGY TEMPLATE
# ============================================================

class StrategyTemplate:

    def __init__(
        self,
        name,
        description,
        style="balanced",
        target_days=7
    ):

        self.name = name
        self.description = description
        self.style = style
        self.target_days = target_days


# ============================================================
# STRATEGY TEMPLATES
# ============================================================

STRATEGY_TEMPLATES = {

    "Scalp Fast": StrategyTemplate(
        "Scalp Fast",
        "Бързи сделки",
        "scalp",
        1
    ),

    "Trend Pro": StrategyTemplate(
        "Trend Pro",
        "Тренд стратегия",
        "trend",
        7
    ),

    "Safe Mode": StrategyTemplate(
        "Safe Mode",
        "Консервативна стратегия",
        "safe",
        14
    ),
}


# ============================================================
# STRATEGY MANAGER
# ============================================================

class StrategyManager:

    def __init__(self):

        self.templates = STRATEGY_TEMPLATES

        self._active_name = "Scalp Fast"

    # --------------------------------------------------------

    def set_strategy(self, name):

        if name in self.templates:
            self._active_name = name

    # --------------------------------------------------------

    @property
    def active_strategy(self):

        return self.templates[self._active_name]

    # --------------------------------------------------------

    def compute(self, df):

        # Тук по-късно ще добавиш индикатори
        return df

    # --------------------------------------------------------

    def signal(self, df):

        # Временен dummy сигнал
        return {
            "signal": "HOLD",
            "strategy": self._active_name
        }
