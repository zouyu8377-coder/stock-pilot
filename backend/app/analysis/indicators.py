import pandas as pd


def compute_indicators(df: pd.DataFrame):
    """
    Calculate technical indicators from historical price data.
    Supports:
      - BaoStock: close
      - AkShare: 收盘

    Returns both indicators for API and MA data for K-line chart overlay.
    """

    price_col = "close" if "close" in df.columns else "收盘"
    print("INDICATOR PRICE COLUMN:", price_col)

    close = pd.to_numeric(df[price_col], errors="coerce")
    close = close.dropna()

    if len(close) < 60:
        raise ValueError("Not enough historical data to calculate indicators")

    # ---------- MA (all periods) ----------
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma30 = close.rolling(30).mean()
    ma60 = close.rolling(60).mean()

    # ---------- RSI14 ----------
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi14 = 100 - (100 / (1 + rs))
    rsi14 = rsi14.iloc[-1]

    # ---------- MACD ----------
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = (ema12 - ema26).iloc[-1]

    indicators = {
        "ma5": round(float(ma5.iloc[-1]), 2),
        "ma10": round(float(ma10.iloc[-1]), 2),
        "ma20": round(float(ma20.iloc[-1]), 2),
        "ma30": round(float(ma30.iloc[-1]), 2),
        "ma60": round(float(ma60.iloc[-1]), 2),
        "rsi14": round(float(rsi14), 2),
        "macd": round(float(macd), 2),
    }

    # Return MA series for K-line chart overlay
    ma_series = {
        "ma5": ma5.dropna().tolist(),
        "ma10": ma10.dropna().tolist(),
        "ma20": ma20.dropna().tolist(),
        "ma30": ma30.dropna().tolist(),
        "ma60": ma60.dropna().tolist(),
    }

    return indicators, ma_series