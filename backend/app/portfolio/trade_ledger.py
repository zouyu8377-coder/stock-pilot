from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.portfolio.import_schemas import PortfolioImportDraft


class PortfolioTradeLedger:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "transactions.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write(self, payload: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def append_confirmed_batch(
        self,
        draft: PortfolioImportDraft,
        *,
        applied_to_portfolio: bool,
        resulting_snapshot_id: str | None,
        user_reason: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        batch_id = f"trade_batch_{uuid4().hex}"
        transactions = [
            {
                "transaction_id": f"transaction_{uuid4().hex}",
                "batch_id": batch_id,
                "symbol": row.normalized_symbol,
                "name": row.normalized_name or row.raw_name_text,
                "side": row.side,
                "average_price": row.average_price,
                "quantity": row.quantity,
                "amount": row.amount,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "action_time_source": "screenshot_time" if row.occurred_at else "user_confirmation_time",
                "confirmed_at": now,
                "source_type": "broker_trade_screenshot_cloud_parsed_user_confirmed",
                "source_draft_id": draft.draft_id,
                "image_reference": Path(draft.image_reference).name,
                "model": draft.provider_model,
                "prompt_version": draft.provider_prompt_version,
                "applied_to_portfolio": applied_to_portfolio,
                "resulting_snapshot_id": resulting_snapshot_id,
            }
            for row in draft.transaction_rows_draft
        ]
        batch = {
            "batch_id": batch_id,
            "confirmed_at": now,
            "source_draft_id": draft.draft_id,
            "applied_to_portfolio": applied_to_portfolio,
            "resulting_snapshot_id": resulting_snapshot_id,
            "user_reason": (user_reason or "").strip() or None,
            "transactions": transactions,
        }
        records = self._read()
        records.append(batch)
        self._write(records)
        return batch

    def list_batches(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self._read()[-limit:]))
