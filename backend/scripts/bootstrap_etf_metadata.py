from app.core.etf_data_updater import bootstrap_etf_metadata


def main():
    df, meta = bootstrap_etf_metadata(force=True)
    print(f"Saved {len(df)} ETF metadata rows via {meta.get('provider')} to {meta.get('metadata_path', 'backend/data/metadata/etf_meta.parquet')}")


if __name__ == "__main__":
    main()
