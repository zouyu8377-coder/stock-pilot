from fastapi import APIRouter, Query
from app.collector.router import collector
import pandas as pd

router = APIRouter()


@router.get("/history/{symbol}")
def get_history(symbol: str, limit: int = Query(default=250, ge=10, le=5000)):
    """
    获取股票历史K线数据（含MA均线）
    limit: 返回最近N条数据，默认250条（约1年）
    """
    df = collector.get_history(symbol, limit)

    if df is None or df.empty:
        return []

    # 兼容中英文列名
    date_col = "date" if "date" in df.columns else "日期"
    open_col = "open" if "open" in df.columns else "开盘"
    high_col = "high" if "high" in df.columns else "最高"
    low_col = "low" if "low" in df.columns else "最低"
    close_col = "close" if "close" in df.columns else "收盘"

    # 计算MA（基于完整数据）
    close = pd.to_numeric(df[close_col], errors="coerce")
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma30 = close.rolling(30).mean()
    ma60 = close.rolling(60).mean()

    # 取最近limit条
    df_limited = df.tail(limit)

    result = []
    for i, (_, row) in enumerate(df_limited.iterrows()):
        result.append({
            "date": str(row[date_col])[:10],
            "open": float(row[open_col]),
            "high": float(row[high_col]),
            "low": float(row[low_col]),
            "close": float(row[close_col]),
            "ma5": round(float(ma5.iloc[i]), 2) if pd.notna(ma5.iloc[i]) else None,
            "ma10": round(float(ma10.iloc[i]), 2) if pd.notna(ma10.iloc[i]) else None,
            "ma20": round(float(ma20.iloc[i]), 2) if pd.notna(ma20.iloc[i]) else None,
            "ma30": round(float(ma30.iloc[i]), 2) if pd.notna(ma30.iloc[i]) else None,
            "ma60": round(float(ma60.iloc[i]), 2) if pd.notna(ma60.iloc[i]) else None,
        })

    return result


@router.get("/intraday/{symbol}")
def get_intraday(symbol: str):
    """
    获取当日分时数据
    """
    try:
        from app.collector.realtime.intraday_provider import IntradayProvider

        provider = IntradayProvider()
        data = provider.get_intraday(symbol)
        print(f"[INTRADAY] Fetched {len(data)} points for {symbol}")
        return data
    except Exception as e:
        print(f"[INTRADAY] Error: {e}")
        return []