from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.analysis_packet.packet_service import build_account_analysis_context
from app.core.config import settings
from app.portfolio import portfolio_service
from app.portfolio.dashboard import MARKET_EVENT_REGISTRY_PATH, build_dashboard
from app.theme_evidence import THEME_EVIDENCE_REGISTRY_PATH


CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "portfolio_dashboard.json"
CACHE_VERSION = "portfolio_dashboard.v6"
_LOCK = threading.Lock()


def _source_paths() -> list[Path]:
    data_root = Path(__file__).resolve().parents[2] / "data"
    return [
        portfolio_service.portfolio_path,
        portfolio_service.evidence_path,
        THEME_EVIDENCE_REGISTRY_PATH,
        MARKET_EVENT_REGISTRY_PATH,
        data_root / "base_market" / "sh.000300.parquet",
        data_root / "update_status.json",
        data_root / "etf_update_status.json",
        data_root / "attractiveness" / "consensus_registry.json",
        data_root / "theme_evidence" / "announcement_verification",
        data_root / "cache" / "etf_share",
    ]


def _fingerprint() -> str:
    digest = hashlib.sha256()
    digest.update(CACHE_VERSION.encode("ascii"))
    for path in _source_paths():
        digest.update(str(path.resolve()).encode("utf-8"))
        if path.exists() and path.is_dir():
            digest.update(f"dir:{path.stat().st_mtime_ns}".encode("ascii"))
            for child in sorted(path.glob("*"))[:200]:
                if child.is_file():
                    stat = child.stat()
                    digest.update(f"{child.name}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
        elif path.exists():
            stat = path.stat()
            digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode("ascii"))
        else:
            digest.update(b"missing")
    return digest.hexdigest()


def _read_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(CACHE_PATH)


def invalidate_dashboard_cache() -> None:
    try:
        CACHE_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def get_dashboard_bundle(*, force: bool = False) -> dict[str, Any]:
    with _LOCK:
        now = datetime.now(timezone.utc)
        fingerprint = _fingerprint()
        cached = _read_cache()
        if not force and cached:
            try:
                expires_at = datetime.fromisoformat(str(cached["expires_at"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                expires_at = now
            if cached.get("fingerprint") == fingerprint and expires_at > now:
                cached["cache"] = {
                    "status": "hit",
                    "cached_at": cached.get("cached_at"),
                    "expires_at": cached.get("expires_at"),
                }
                return cached

        state = portfolio_service.get_state()
        context = build_account_analysis_context(mode="compact", state=state)
        dashboard = build_dashboard(state, context, persist_attractiveness_history=True)
        ttl = max(1, int(settings.DASHBOARD_CACHE_SECONDS))
        payload = {
            "fingerprint": fingerprint,
            "cached_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
            "context": context,
            "dashboard": dashboard,
            "cache": {
                "status": "miss" if not force else "refresh",
                "cached_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
            },
        }
        _write_cache(payload)
        return payload
