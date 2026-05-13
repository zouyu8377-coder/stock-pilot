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

    def search(self, query: str = "", limit: int = 20):
        term = query.strip()
        df = self.df

        if term:
            mask = (
                df["symbol"].astype(str).str.contains(term, case=False, na=False)
                | df["name"].astype(str).str.contains(term, case=False, na=False)
            )
            df = df[mask]

        df = df.head(limit)
        results = []
        for _, row in df.iterrows():
            results.append({
                "symbol": str(row.get("symbol", "")).zfill(6),
                "name": str(row.get("name", "")),
                "industry": str(row.get("industry", "")),
                "area": str(row.get("area", "")),
            })
        return results


metadata_provider = MetadataProvider()
