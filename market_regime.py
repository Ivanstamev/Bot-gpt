def detect_market_regime(df):

    adx = df['ADX'].iloc[-1]
    atr = df['ATR'].iloc[-1]

    recent_range = df['high'].tail(20).max() - df['low'].tail(20).min()

    if adx < 20:
        return "RANGE"

    if atr > df['ATR'].rolling(50).mean().iloc[-1] * 2:
        return "HIGH_VOLATILITY"

    if recent_range < df['close'].iloc[-1] * 0.01:
        return "CHOPPY"

    return "TREND"
