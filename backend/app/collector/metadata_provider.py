from pathlib import Path
import pandas as pd


class MetadataProvider:
    def __init__(self):
        BASE_DIR = Path(__file__).resolve().parents[2]
        path = BASE_DIR / "data" / "metadata" / "stock_meta.parquet"

        print("METADATA LOAD:", path)

        self.df = pd.read_parquet(path)
        self.df["symbol"] = self.df["symbol"].astype(str).str.zfill(6)

    def get(self, symbol: str):
        row = self.df[self.df["symbol"] == symbol]

        if row.empty:
            return None

        r = row.iloc[0]

        return {
            "name": r["name"],
            "industry": r["industry"],
            "area": r["area"],
            "list_date": str(r["list_date"]),
        }


metadata_provider = MetadataProvider()