def valid_long_entry(df):

    latest = df.iloc[-1]

    conditions = [
        latest['EMA_50'] > latest['EMA_200'],
        latest['ADX'] > 22,
        latest['RSI'] > 50,
        latest['volume'] > df['volume'].rolling(20).mean().iloc[-1],
        latest['close'] > latest['EMA_50']
    ]

    return sum(conditions) >= 4


def valid_short_entry(df):

    latest = df.iloc[-1]

    conditions = [
        latest['EMA_50'] < latest['EMA_200'],
        latest['ADX'] > 22,
        latest['RSI'] < 50,
        latest['volume'] > df['volume'].rolling(20).mean().iloc[-1],
        latest['close'] < latest['EMA_50']
    ]

    return sum(conditions) >= 4
