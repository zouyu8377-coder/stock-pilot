from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


def safe_cache_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.=-]+", "_", value.strip())
    return value[:120] or "default"


def params_digest(params: dict[str, Any]) -> str:
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class TushareCache:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        for subdir in [
            "etf",
            "dragon_tiger",
            "announcements",
            "surveys",
            "margin",
            "moneyflow",
            "events",
            "valuation",
        ]:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

    def paths(self, namespace: str, cache_key: str) -> tuple[Path, Path]:
        base = self.root / safe_cache_name(namespace)
        base.mkdir(parents=True, exist_ok=True)
        name = safe_cache_name(cache_key)
        return base / f"{name}.parquet", base / f"{name}.meta.json"

    def read(self, namespace: str, cache_key: str, max_age: timedelta | None = None) -> pd.DataFrame | None:
        data_path, meta_path = self.paths(namespace, cache_key)
        if not data_path.exists() or not meta_path.exists():
            return None
        if max_age is not None:
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                fetched_at = datetime.fromisoformat(payload["fetched_at"])
            except Exception:
                return None
            if datetime.utcnow() - fetched_at > max_age:
                return None
        return pd.read_parquet(data_path)

    def write(
        self,
        namespace: str,
        cache_key: str,
        df: pd.DataFrame,
        *,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        data_path, meta_path = self.paths(namespace, cache_key)
        df.to_parquet(data_path, index=False)
        meta = {
            "endpoint": endpoint,
            "params": params,
            "row_count": int(len(df)),
            "fetched_at": datetime.utcnow().isoformat(),
            "data_path": str(data_path),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta
