from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import portfolio as portfolio_api
from app.main import app
from app.portfolio.import_schemas import HoldingRowDraft, PortfolioImportDraftUpdate
from app.portfolio.import_service import PortfolioImportService
from app.portfolio.ocr_provider import OcrResult
from app.portfolio.service import PortfolioService
from app.portfolio.symbol_resolver import resolve_symbol_or_name


class MockOcrProvider:
    provider_name = "mock_local_ocr"

    def __init__(self, raw_text: str, status: str = "partial"):
        self.raw_text = raw_text
        self.status = status

    def extract_text(self, image_path: Path) -> OcrResult:
        return OcrResult(
            provider_name=self.provider_name,
            status=self.status,
            raw_text=self.raw_text,
            warnings=["mock OCR for sanitized test only"],
        )


def _fake_quote(symbol: str):
    prices = {
        "601899": {"price": 31.38, "name": "紫金矿业"},
        "002916": {"price": 88.0, "name": "深南电路"},
        "000657": {"price": 13.5, "name": "中钨高新"},
        "159934": {"price": 5.4, "name": "黄金ETF"},
    }
    return {**prices.get(symbol, {"price": 10.0, "name": symbol}), "provider": "test"}


def _service(tmp_path, raw_text: str = "", status: str = "partial"):
    portfolio_service = PortfolioService(tmp_path / "portfolio")
    return PortfolioImportService(
        root=tmp_path / "imports",
        upload_root=tmp_path / "uploads",
        ocr_provider=MockOcrProvider(raw_text, status),
        portfolio_service=portfolio_service,
    )


def test_upload_image_creates_draft_without_saving_snapshot(tmp_path):
    service = _service(tmp_path, "601899 紫金矿业 1000 800 30.00 31.64 31640 1640 5.47")

    draft = service.create_draft_from_upload("sanitized.png", "image/png", b"fake image bytes")

    assert draft.draft_id
    assert draft.needs_user_confirmation is True
    assert draft.saved_snapshot_id is None
    assert draft.holding_rows_draft[0].normalized_symbol == "601899.SH"
    assert not (tmp_path / "portfolio" / "default_portfolio.json").exists()


def test_non_image_and_oversized_upload_are_rejected(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="PNG"):
        service.create_draft_from_upload("bad.txt", "text/plain", b"x")
    with pytest.raises(ValueError, match="8MB"):
        service.create_draft_from_upload("huge.png", "image/png", b"x" * (8 * 1024 * 1024 + 1))


def test_partial_ocr_failure_creates_manual_entry_draft(tmp_path):
    service = _service(tmp_path, "", "failed_manual_entry_required")

    draft = service.create_draft_from_upload("empty.png", "image/png", b"fake")

    assert draft.ocr_status == "ocr_failed"
    assert draft.parse_status == "parse_incomplete"
    assert draft.holding_rows_draft == []
    assert any("手工补录" in warning for warning in draft.parse_warnings)


def test_symbol_resolver_code_name_conflict_and_name_candidates():
    symbol, name, status, candidates, warnings = resolve_symbol_or_name("601899", "深南电路")
    assert symbol == "601899.SH"
    assert name
    assert status == "conflict_requires_confirmation"
    assert candidates
    assert warnings

    symbol, name, status, candidates, warnings = resolve_symbol_or_name("", "紫金矿业")
    assert status in {"name_candidate_match", "unresolved"}
    assert symbol == "601899.SH" or candidates


def test_update_confirm_creates_new_snapshot_with_separated_prices(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = _service(
        tmp_path,
        "\n".join([
            "601899 紫金矿业 1000 800 30.00 31.64 31640 1640 5.47",
            "002916 深南电路 200 200 80.00 88.50 17700 1700 10.63",
            "000657 中钨高新 300 300 12.00 13.20 3960 360 10.00",
            "159934 黄金ETF 400 400 5.00 5.50 2200 200 10.00",
        ]),
    )
    draft = service.create_draft_from_upload("sanitized.png", "image/png", b"fake")
    rows = draft.holding_rows_draft
    rows[0].primary_theme = "METAL_RESOURCE"
    rows[0].theme_tags = ["METAL_RESOURCE"]
    update = service.update_draft(draft.draft_id, PortfolioImportDraftUpdate(holding_rows_draft=rows))

    result = service.confirm_draft(update.draft_id)
    state = result["state"]
    first = state.snapshot.positions[0]

    assert result["draft"].saved_snapshot_id == state.snapshot.snapshot_id
    assert (tmp_path / "portfolio" / "snapshots" / f"{state.snapshot.snapshot_id}.json").exists()
    assert first.source_type == "manual_account"
    assert first.broker_screenshot_price == 31.64
    assert first.system_quote_price == 31.38
    assert first.broker_screenshot_price_time is None
    assert first.system_quote_market_time is None
    assert first.available_quantity == 800
    assert first.confirmed_by_user is True
    assert service.portfolio_service.list_manual_evidence()[0].include_in_analysis_packet is False


def test_confirm_blocks_unresolved_required_fields(tmp_path):
    service = _service(tmp_path)
    draft = service.create_draft_from_upload("sanitized.png", "image/png", b"fake")
    draft.holding_rows_draft = [HoldingRowDraft(raw_name_text="未知标的", quantity=100, avg_cost=10)]
    service._write_draft(draft)

    with pytest.raises(ValueError, match="未匹配标准代码"):
        service.confirm_draft(draft.draft_id)


def test_api_smoke_import_update_confirm_reject_and_existing_routes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = _service(tmp_path, "601899 紫金矿业 1000 800 30.00 31.64 31640 1640 5.47")
    monkeypatch.setattr(portfolio_api, "portfolio_import_service", service)
    monkeypatch.setattr(portfolio_api, "portfolio_service", service.portfolio_service)
    client = TestClient(app)

    upload = client.post(
        "/api/portfolio/import/screenshot",
        files={"file": ("sanitized.png", b"fake", "image/png")},
    )
    assert upload.status_code == 200
    draft_id = upload.json()["data"]["draft_id"]

    assert client.get(f"/api/portfolio/import/drafts/{draft_id}").status_code == 200
    payload = upload.json()["data"]
    payload["holding_rows_draft"][0]["confirmed_by_user"] = True
    patch = client.patch(f"/api/portfolio/import/drafts/{draft_id}", json={
        "holding_rows_draft": payload["holding_rows_draft"],
    })
    assert patch.status_code == 200
    confirm = client.post(f"/api/portfolio/import/drafts/{draft_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["data"]["portfolio"]["snapshot"]["positions"][0]["broker_screenshot_price"] == 31.64

    reject_service = _service(tmp_path / "reject", "")
    monkeypatch.setattr(portfolio_api, "portfolio_import_service", reject_service)
    reject_upload = client.post(
        "/api/portfolio/import/screenshot",
        files={"file": ("empty.png", b"fake", "image/png")},
    )
    reject_id = reject_upload.json()["data"]["draft_id"]
    assert client.delete(f"/api/portfolio/import/drafts/{reject_id}").json()["data"]["parse_status"] == "user_rejected"

    assert client.get("/api/portfolio").status_code == 200
    assert client.get("/api/portfolio/analysis-snapshot").status_code == 200

