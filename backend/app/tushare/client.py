from __future__ import annotations

import re
import time
from datetime import timedelta
from typing import Any

import pandas as pd

from app.core.config import Settings, settings
from app.tushare.cache import TushareCache, params_digest
from app.tushare.exceptions import TushareConfigError, TushareRequestError


RATE_LIMIT_HINTS = ("频率", "rate", "limit", "too many", "超限")


def sanitize_tushare_error(message: str) -> str:
    cleaned = re.sub(r"[A-Za-z0-9]{24,}", "[REDACTED]", str(message))
    return cleaned.replace("\n", " ")[:240]


class TushareLowFrequencyClient:
    """
    Shared low-frequency Tushare access layer.

    Page requests should prefer cached data or background jobs. This class keeps
    token handling, throttling and sanitized errors in one place.
    """

    def __init__(self, config: Settings = settings, cache: TushareCache | None = None):
        self.settings = config
        self.cache = cache or TushareCache(config.TUSHARE_CACHE_ROOT)
        self._pro = None
        self._last_request_at: float | None = None

    def require_token(self) -> str:
        token = self.settings.TUSHARE_TOKEN.strip()
        if not token:
            raise TushareConfigError("Tushare token is not configured. Set backend env var TUSHARE_TOKEN.")
        return token

    @property
    def pro(self):
        if self._pro is None:
            import tushare as ts

            ts.set_token(self.require_token())
            self._pro = ts.pro_api()
        return self._pro

    def _throttle(self) -> None:
        interval = max(int(self.settings.TUSHARE_RATE_LIMIT_SECONDS), 0)
        if interval <= 0 or self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_at = time.monotonic()

    def query(
        self,
        endpoint: str,
        *,
        namespace: str,
        fields: str | None = None,
        ttl: timedelta | None = None,
        force: bool = False,
        **params: Any,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        cache_key = f"{endpoint}_{params_digest(params)}"
        if not force:
            cached = self.cache.read(namespace, cache_key, ttl)
            if cached is not None:
                return cached, {
                    "endpoint": endpoint,
                    "params": params,
                    "cache_hit": True,
                    "row_count": int(len(cached)),
                }

        try:
            self._throttle()
            if fields:
                df = self.pro.query(endpoint, fields=fields, **params)
            else:
                df = self.pro.query(endpoint, **params)
            if df is None:
                df = pd.DataFrame()
            meta = self.cache.write(namespace, cache_key, df, endpoint=endpoint, params=params)
            meta["cache_hit"] = False
            return df, meta
        except TushareConfigError:
            raise
        except Exception as exc:
            safe = sanitize_tushare_error(str(exc))
            if any(hint in safe.lower() for hint in RATE_LIMIT_HINTS):
                raise TushareRequestError(f"Tushare request is rate limited: {safe}") from exc
            raise TushareRequestError(f"Tushare request failed: {safe}") from exc
