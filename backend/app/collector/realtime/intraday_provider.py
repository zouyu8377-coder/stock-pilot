import akshare as ak
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo


class IntradayProvider:
    """
    分时数据 provider（日内K线）
    返回数据格式:
    [
      {
        "time": "2026-05-11 09:31:00",
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "volume": int
      }
    ]
    """

    def __init__(self):
        pass

    def get_intraday(self, symbol: str):
        """
        获取当日1分钟K线数据。
        如果当天交易还在进行中，只返回到当前时点的数据；
        数据缺失时 fallback 也只生成到当前时点。
        """
        try:
            symbol = symbol.zfill(6)
            print(f"[INTRADAY] fetching akshare min data for {symbol}")

            df = ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period="1",
                adjust=""
            )

            if df is None or df.empty:
                print(f"[INTRADAY] akshare returned empty for {symbol}")
                return []

            # 标准化列名
            col_map = {
                "时间": "time",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            }
            rename_map = {cn: en for cn, en in col_map.items() if cn in df.columns}
            if rename_map:
                df = df.rename(columns=rename_map)

            tz = ZoneInfo("Asia/Shanghai")
            now = datetime.now(tz)
            result = []

            for _, row in df.iterrows():
                time_str = str(row.get("time", ""))
                if not time_str:
                    continue

                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    t = dt.time()

                    # 过滤午休 11:31-12:59
                    if dt_time(11, 31) <= t < dt_time(13, 0):
                        continue
                    # 过滤非交易时段
                    if t < dt_time(9, 30) or t > dt_time(15, 0):
                        continue
                    # 过滤未来数据：当天且超过当前时间的数据不展示
                    if dt.date() == now.date() and dt > now:
                        continue

                    result.append({
                        "time": time_str,
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("volume", 0)),
                    })
                except Exception:
                    continue

            print(f"[INTRADAY] parsed {len(result)} points from akshare for {symbol}")
            return result

        except Exception as e:
            print(f"[INTRADAY] akshare failed: {e}")
            return []

    def _generate_fallback(self, symbol: str):
        """
        fallback：数据缺失时空置，不再生成模拟数据。
        原则：显示出来的数据必须是真实的。
        """
        print("[INTRADAY] fallback returning empty list")
        return []
