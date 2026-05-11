from pathlib import Path
import json
import pandas as pd
from datetime import datetime, timedelta


BASE_DATA_DIR = Path("data")
HISTORY_DIR = BASE_DATA_DIR / "history"
INDICATORS_DIR = BASE_DATA_DIR / "indicators"
HOT_CACHE_TTL = timedelta(seconds=30)


class CacheManager:
    """
    统一缓存管理器
    """

    def __init__(self):
        self.hot_cache = {}

        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        INDICATORS_DIR.mkdir(parents=True, exist_ok=True)

    def set_hot(self, symbol: str, data: dict):
        self.hot_cache[symbol] = {
            "data": data,
            "updated_at": datetime.utcnow().isoformat(),
        }

    def get_hot(self, symbol: str):
        item = self.hot_cache.get(symbol)
        if not item:
            return None
        try:
            updated_at = datetime.fromisoformat(item["updated_at"])
        except Exception:
            self.hot_cache.pop(symbol, None)
            return None
        if datetime.utcnow() - updated_at > HOT_CACHE_TTL:
            self.hot_cache.pop(symbol, None)
            return None
        return item["data"]

    def _history_path(self, symbol: str):
        return HISTORY_DIR / f"{symbol}.parquet"

    def has_history(self, symbol: str):
        return self._history_path(symbol).exists()

    def write_history(self, symbol: str, df: pd.DataFrame):
        path = self._history_path(symbol)
        df.to_parquet(path)

    def read_history(self, symbol: str):
        path = self._history_path(symbol)
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def _indicator_path(self, symbol: str):
        return INDICATORS_DIR / f"{symbol}.json"

    def has_indicators(self, symbol: str):
        return self._indicator_path(symbol).exists()

    def write_indicators(self, symbol: str, indicators: dict):
        path = self._indicator_path(symbol)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                indicators,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def read_indicators(self, symbol: str):
        path = self._indicator_path(symbol)

        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


cache = CacheManager()
