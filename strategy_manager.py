from market_regime import detect_market_regime
from smart_entry import valid_long_entry, valid_short_entry
from liquidity_filter import liquidity_sweep_detected


class StrategyManager:

    def __init__(self):
        self.active = type('', (), {})()
        self.active.min_confidence = 80

    def compute(self, df):
        return df

    def signal(self, df):

        regime = detect_market_regime(df)

        if regime != "TREND":
            return {
                "signal": "HOLD",
                "confidence": 0
            }

        if liquidity_sweep_detected(df):
            return {
                "signal": "HOLD",
                "confidence": 0
            }

        if valid_long_entry(df):
            return {
                "signal": "LONG",
                "confidence": 82
            }

        if valid_short_entry(df):
            return {
                "signal": "SHORT",
                "confidence": 82
            }

        return {
            "signal": "HOLD",
            "confidence": 0
        }

    def select(self, name):
        pass
