def liquidity_sweep_detected(df):

    latest = df.iloc[-1]

    upper_wick = latest['high'] - max(latest['open'], latest['close'])
    lower_wick = min(latest['open'], latest['close']) - latest['low']

    candle_size = latest['high'] - latest['low']

    if candle_size == 0:
        return False

    upper_ratio = upper_wick / candle_size
    lower_ratio = lower_wick / candle_size

    if upper_ratio > 0.45 or lower_ratio > 0.45:
        return True

    return False
