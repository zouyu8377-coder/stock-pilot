from pathlib import Path
import pandas as pd
import tushare as ts

# ===== 配置 =====
TOKEN ="b10c8a6089c53e3327b8c89bf3b4d3851eb32d93818bf2549fb6cd32"

OUTPUT_DIR = Path("backend/data/metadata")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "stock_meta.parquet"


def main():
    print("Connecting to Tushare...")

    ts.set_token(TOKEN)
    pro = ts.pro_api()

    print("Downloading stock metadata...")

    df = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,list_date"
    )

    print(f"Downloaded {len(df)} stocks")

    # 清洗字段
    df = df.rename(
        columns={
            "ts_code": "ts_code",
            "symbol": "symbol",
            "name": "name",
            "area": "area",
            "industry": "industry",
            "list_date": "list_date",
        }
    )

    df["symbol"] = df["symbol"].astype(str).str.zfill(6)

    print(df.head())

    df.to_parquet(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("Saved to:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()