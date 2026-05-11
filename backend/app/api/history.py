from fastapi import APIRouter, HTTPException, Query
from app.collector.router import collector
import pandas as pd

router = APIRouter()


def _pick_column(df: pd.DataFrame, *candidates: str) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise KeyError(f"Missing required column, expected one of: {candidates}")


def _to_optional_float(value) -> float | None:
    if pd.isna(value):
        return None
    return round(float(value), 2)


@router.get("/history/{symbol}")
def get_history(symbol: str, limit: int = Query(default=250, ge=10, le=5000)):
    try:
        df = collector.get_history(symbol, 5000)
    except Exception as e:
        print(f"[HISTORY] Error: {e}")
        raise HTTPException(status_code=502, detail=f"History data unavailable: {symbol}") from e

    if df is None or df.empty:
        return []

    try:
        date_col = _pick_column(df, "date", "日期")
        open_col = _pick_column(df, "open", "开盘")
        high_col = _pick_column(df, "high", "最高")
        low_col = _pick_column(df, "low", "最低")
        close_col = _pick_column(df, "close", "收盘")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    close = pd.to_numeric(df[close_col], errors="coerce")
    ma_frame = pd.DataFrame({
        "ma5": close.rolling(5).mean(),
        "ma10": close.rolling(10).mean(),
        "ma20": close.rolling(20).mean(),
        "ma30": close.rolling(30).mean(),
        "ma60": close.rolling(60).mean(),
    })

    df_limited = df.tail(limit)
    ma_frame = ma_frame.reindex(df_limited.index)

    result = []
    for idx, row in df_limited.iterrows():
        ma_row = ma_frame.loc[idx]
        result.append({
            "date": str(row[date_col])[:10],
            "open": float(row[open_col]),
            "high": float(row[high_col]),
            "low": float(row[low_col]),
            "close": float(row[close_col]),
            "ma5": _to_optional_float(ma_row["ma5"]),
            "ma10": _to_optional_float(ma_row["ma10"]),
            "ma20": _to_optional_float(ma_row["ma20"]),
            "ma30": _to_optional_float(ma_row["ma30"]),
            "ma60": _to_optional_float(ma_row["ma60"]),
        })

    return result


@router.get("/intraday/{symbol}")
def get_intraday(symbol: str):
    try:
        from app.collector.realtime.intraday_provider import IntradayProvider

        provider = IntradayProvider()
        data = provider.get_intraday(symbol)
        print(f"[INTRADAY] Fetched {len(data)} points for {symbol}")
        return data
    except Exception as e:
        print(f"[INTRADAY] Error: {e}")
        raise HTTPException(status_code=502, detail=f"Intraday data unavailable: {symbol}") from e
