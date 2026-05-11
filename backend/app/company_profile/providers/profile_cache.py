import json
from datetime import datetime, timedelta
from pathlib import Path

from app.company_profile.schemas import CompanyProfile

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "company_profile"
CACHE_TTL_DAYS = 7


class ProfileCache:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str) -> Path:
        return CACHE_DIR / f"{symbol}.json"

    def get(self, symbol: str) -> CompanyProfile | None:
        path = self._cache_path(symbol)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            cached_at = payload.get("cached_at")
            if not cached_at:
                return None

            dt = datetime.fromisoformat(cached_at)
            if datetime.now() - dt > timedelta(days=CACHE_TTL_DAYS):
                return None

            return CompanyProfile(**payload.get("profile", {}))
        except Exception as e:
            print(f"[ProfileCache] read failed for {symbol}: {e}")
            return None

    def set(self, symbol: str, profile: CompanyProfile) -> None:
        path = self._cache_path(symbol)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "cached_at": datetime.now().isoformat(),
                        "profile": profile.model_dump(),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f"[ProfileCache] write failed for {symbol}: {e}")
