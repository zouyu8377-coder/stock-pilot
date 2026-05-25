from pathlib import Path

import pandas as pd

from app.facts.common import compact_symbol


def _clean(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    return "" if text.lower() in {"nan", "none", "null"} else text


class MetadataProvider:
    def __init__(self):
        base_dir = Path(__file__).resolve().parents[2]
        self.metadata_dir = base_dir / "data" / "metadata"
        path = self.metadata_dir / "stock_meta.parquet"

        print("METADATA LOAD:", path)

        self.df = self._load_stock_meta(path)
        self.etf_df = self._load_etf_meta()
        self.search_df = pd.concat([self.df, self.etf_df], ignore_index=True)

    def _load_stock_meta(self, path: Path):
        df = pd.read_parquet(path)
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df["asset_type"] = "stock"
        return df

    def _load_etf_meta(self):
        path = self.metadata_dir / "etf_meta.parquet"
        if path.exists():
            df = pd.read_parquet(path)
        else:
            df = pd.DataFrame([
                {
                    "ts_code": "159382.SZ",
                    "symbol": "159382",
                    "name": "创业板人工智能ETF南方",
                    "area": "SZ",
                    "industry": "ETF",
                    "list_date": "",
                    "fund_type": "ETF",
                    "management": "南方基金",
                    "asset_type": "etf",
                },
                {
                    "ts_code": "159934.SZ",
                    "symbol": "159934",
                    "name": "黄金ETF易方达",
                    "area": "SZ",
                    "industry": "ETF",
                    "list_date": "",
                    "fund_type": "ETF",
                    "management": "易方达基金",
                    "asset_type": "etf",
                },
            ])
        if df.empty:
            return pd.DataFrame(columns=[*self.df.columns, "fund_type", "management"])
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df["area"] = df.get("area", df.get("market", "")).fillna("")
        df["industry"] = df.get("industry", df.get("fund_type", "ETF")).fillna("ETF")
        df["list_date"] = df.get("list_date", "").fillna("").astype(str)
        df["asset_type"] = "etf"
        for column in self.df.columns:
            if column not in df.columns:
                df[column] = ""
        return df

    def get(self, symbol: str):
        code = compact_symbol(symbol)
        row = self.search_df[self.search_df["symbol"] == code]

        if row.empty:
            return None

        r = row.iloc[0]
        return {
            "name": _clean(r.get("name")),
            "industry": _clean(r.get("industry")),
            "area": _clean(r.get("area")),
            "list_date": _clean(r.get("list_date")),
            "asset_type": _clean(r.get("asset_type")) or "stock",
            "fund_type": _clean(r.get("fund_type")),
            "management": _clean(r.get("management")),
        }

    def search(self, query: str = "", limit: int = 20):
        term = query.strip()
        df = self.search_df

        if term:
            industry = df["industry"] if "industry" in df.columns else pd.Series("", index=df.index)
            mask = (
                df["symbol"].astype(str).str.contains(term, case=False, na=False, regex=False)
                | df["name"].astype(str).str.contains(term, case=False, na=False, regex=False)
                | industry.astype(str).str.contains(term, case=False, na=False, regex=False)
            )
            df = df[mask]

        df = df.head(limit)
        results = []
        for _, row in df.iterrows():
            results.append({
                "symbol": _clean(row.get("symbol")).zfill(6),
                "name": _clean(row.get("name")),
                "industry": _clean(row.get("industry")),
                "area": _clean(row.get("area")),
                "asset_type": _clean(row.get("asset_type")) or "stock",
                "fund_type": _clean(row.get("fund_type")),
                "management": _clean(row.get("management")),
            })
        return results


metadata_provider = MetadataProvider()
