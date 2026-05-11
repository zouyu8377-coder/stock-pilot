import akshare as ak
import pandas as pd
import random
from datetime import datetime, timedelta


def build_mock_history(symbol: str):
    """
    生成 mock 历史K线（60日）
    """
    rows = []

    price = 100 + random.uniform(-20, 20)

    for i in range(60):
        date = datetime.now() - timedelta(days=60 - i)

        close = price + random.uniform(-2, 2)

        rows.append(
            {
                "日期": date.strftime("%Y-%m-%d"),
                "收盘": round(close, 2),
            }
        )

        price = close

    return pd.DataFrame(rows)


class AkshareHistoryProvider:
    """
    历史 K 线 provider
    """

    def get_daily_history(self, symbol: str):
        """
        获取最近60天日线
        """

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                adjust="qfq",
            )

            if df is None or df.empty:
                raise Exception("empty dataframe")

            return df.tail(60)

        except Exception as e:
            print(f"AkShare failed, fallback to mock history: {e}")
            return build_mock_history(symbol)