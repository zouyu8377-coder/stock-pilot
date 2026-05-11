from pathlib import Path
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[3]
BASE_MARKET_DIR = BASE_DIR / "data" / "base_market"


def normalize_symbol(symbol: str) -> str:
    """
    转换 symbol 为 baostock 格式
    600 / 601 / 603 / 605 / 688 -> sh
    000 / 001 / 002 / 003 / 300 -> sz
    """
    symbol = symbol.strip()

    if symbol.startswith(("600", "601", "603", "605", "688")):
        return f"sh.{symbol}"
    elif symbol.startswith(("000", "001", "002", "003", "300")):
        return f"sz.{symbol}"
    else:
        raise ValueError(f"Unknown symbol prefix: {symbol}")


class BaseMarketProvider:
    """
    本地 parquet 历史数据 provider
    """

    def get_daily_history(self, symbol: str, limit: int = 5000):
        """
        读取本地 base_market parquet 文件
        """
        normalized = normalize_symbol(symbol)
        parquet_path = BASE_MARKET_DIR / f"{normalized}.parquet"

        print(f"BASE MARKET LOAD: {normalized}")

        if not parquet_path.exists():
            raise FileNotFoundError(f"Base market file not found: {parquet_path}")

        df = pd.read_parquet(parquet_path)

        return df.tail(limit)