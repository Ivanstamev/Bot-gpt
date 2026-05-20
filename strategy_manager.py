class StrategyTemplate:
    def __init__(self, name, description, style="balanced", target_days=7):
        self.name = name
        self.description = description
        self.style = style
        self.target_days = target_days


STRATEGY_TEMPLATES = {
    "Scalp Fast": StrategyTemplate("Scalp Fast", "Бързи сделки", "scalp", 1),
    "Trend Pro": StrategyTemplate("Trend Pro", "Тренд стратегия", "trend", 7),
    "Safe Mode": StrategyTemplate("Safe Mode", "Консервативна стратегия", "safe", 14),
}
