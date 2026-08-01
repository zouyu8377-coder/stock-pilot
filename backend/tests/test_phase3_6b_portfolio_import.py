from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import portfolio as portfolio_api
from app.main import app
from app.portfolio.import_schemas import HoldingRowDraft, PortfolioImportDraftUpdate
from app.portfolio.import_service import PortfolioImportService, provider_statuses
from app.portfolio.ocr_provider import OcrResult, VolcengineArkVisionPortfolioImageParser
from app.portfolio.schemas import PortfolioSnapshotInput
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


class MockVisionProvider:
    provider_name = "volcengine_ark_vision"

    def __init__(self, payload: dict | None = None, status: str = "draft_parsed"):
        self.payload = payload
        self.status = status
        self.called = False

    def parse_image(self, image_path: Path, screenshot_kind: str = "current_holdings") -> OcrResult:
        self.called = True
        if self.status != "draft_parsed":
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                warnings=["mock cloud failure"],
                error_summary="mock timeout",
            )
        return OcrResult(
            provider_name=self.provider_name,
            status="draft_parsed",
            raw_text="[omitted]",
            structured_payload=self.payload or _mock_vision_payload(),
            warnings=["mock cloud vision for sanitized test only"],
        )


def _mock_trade_payload():
    return {
        "source_view": {"platform_guess": "同花顺", "screenshot_displayed_time": None, "warnings": []},
        "transactions": [
            {
                "raw_symbol": None,
                "raw_name": "中国人寿",
                "side": "buy",
                "average_price": 40.33,
                "quantity": 100,
                "amount": 4033,
                "occurred_at": None,
                "warnings": [],
            },
            {
                "raw_symbol": None,
                "raw_name": "药明康德",
                "side": "sell",
                "average_price": 125.586,
                "quantity": 100,
                "amount": 12558.6,
                "occurred_at": None,
                "warnings": [],
            },
        ],
        "parse_warnings": [],
    }


def _mock_vision_payload():
    return {
        "source_view": {
            "platform_guess": "同花顺",
            "screenshot_displayed_time": None,
            "warnings": ["部分字段需人工核对"],
        },
        "account_summary": {
            "total_assets": 100000,
            "cash_available": 10000,
            "total_market_value": 90000,
            "total_unrealized_pnl": 1200,
            "repo_amount": None,
            "repo_available_date": None,
        },
        "holdings": [
            {
                "raw_symbol": "601899",
                "raw_name": "紫金矿业",
                "quantity": 1000,
                "available_quantity": 800,
                "avg_cost": 30,
                "screenshot_price": 31.64,
                "market_value": 31640,
                "unrealized_pnl": 1640,
                "unrealized_pnl_pct": 5.47,
                "warnings": [],
                "recommendation": "buy",
            },
            {
                "raw_symbol": "002463",
                "raw_name": "沪电股份",
                "quantity": 200,
                "available_quantity": 250,
                "avg_cost": 42,
                "screenshot_price": 44,
                "market_value": 8800,
                "unrealized_pnl": 400,
                "unrealized_pnl_pct": 4.76,
                "warnings": ["可用数量疑似识别错误"],
            },
        ],
        "unrecognized_text": ["模拟脱敏账户"],
        "parse_warnings": [],
    }


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

    symbol, name, status, candidates, warnings = resolve_symbol_or_name("", "医药ETF汇添富")
    assert symbol == "159929.SZ"
    assert status == "name_candidate_match"

    symbol, name, status, candidates, warnings = resolve_symbol_or_name("", "创业板人工智能ET")
    assert symbol == "159382.SZ"
    assert status == "name_candidate_match"


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


def test_holdings_screenshot_preserves_confirmed_account_cost(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = _service(tmp_path, "601899 紫金矿业 1000 800 30.00 31.64 31640 1640 5.47")
    service.portfolio_service.save_snapshot(PortfolioSnapshotInput(
        total_assets=100000,
        cash_available=10000,
        account_actual_total_cost=120000,
        positions=[],
    ))
    draft = service.create_draft_from_upload("sanitized.png", "image/png", b"fake")

    result = service.confirm_draft(draft.draft_id)

    assert result["state"].snapshot.account_actual_total_cost == 120000
    assert result["state"].metrics.account_total_pnl < 0


def test_holdings_screenshot_preserves_confirmed_position_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = _service(tmp_path, "601899 紫金矿业 1000 800 30.00 31.64 31640 1640 5.47")
    service.portfolio_service.save_snapshot(PortfolioSnapshotInput(
        total_assets=100000,
        cash_available=10000,
        positions=[{
            "symbol": "601899.SH",
            "name": "紫金矿业",
            "quantity": 900,
            "avg_cost": 29,
            "primary_theme": "铜",
            "theme_tags": ["铜"],
            "directions": ["铜"],
            "risk_flags": ["HIGH_VOLATILITY"],
            "semantic_classification_status": "user_confirmed",
            "semantic_classification_source": "manual_confirmed_from_system_suggestion",
        }],
    ))
    draft = service.create_draft_from_upload("sanitized.png", "image/png", b"fake")

    result = service.confirm_draft(draft.draft_id)
    position = result["state"].snapshot.positions[0]

    assert position.directions == ["铜"]
    assert position.primary_theme == "铜"
    assert position.risk_flags == ["HIGH_VOLATILITY"]
    assert position.semantic_classification_status == "user_confirmed"
    assert position.semantic_classification_source == "manual_confirmed_from_system_suggestion"


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


def test_provider_status_does_not_expose_api_key(monkeypatch):
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_ENABLED", True)
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_BASE_URL", "https://ark.example/v3")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_API_KEY", "mock-redacted-key")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_MODEL", "vision-model")

    status = provider_statuses()

    encoded = str(status)
    assert "mock-redacted-key" not in encoded
    cloud = next(item for item in status["providers"] if item["provider"] == "volcengine_ark_vision")
    assert cloud["status"] == "configured_not_verified"
    assert cloud["api_key_configured"] is True


class _VisionResponse:
    status_code = 200
    text = ""

    def __init__(self, content: str, finish_reason: str = "stop"):
        self.content = content
        self.finish_reason = finish_reason

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{
                "finish_reason": self.finish_reason,
                "message": {"content": self.content},
            }],
            "usage": {
                "prompt_tokens": 900,
                "completion_tokens": 700,
                "total_tokens": 1600,
            },
        }


def test_minimax_vision_contract_normalizes_output_and_records_usage(tmp_path, monkeypatch):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    payload = _mock_vision_payload()
    payload["holdings"][0]["warnings"] = ["a" * 100, "second", "ignored"]
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["payload"] = json
        return _VisionResponse(f"```json\n{__import__('json').dumps(payload, ensure_ascii=False)}\n```")

    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_ENABLED", True)
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_BASE_URL", "https://ark.example/v3")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_API_KEY", "secret")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_MODEL", "minimax-m3")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_MAX_TOKENS", 4096)

    result = VolcengineArkVisionPortfolioImageParser(http_post=fake_post).parse_image(image)

    assert result.status == "draft_parsed"
    assert result.model_name == "minimax-m3"
    assert result.usage == {"prompt_tokens": 900, "completion_tokens": 700, "total_tokens": 1600}
    assert captured["payload"]["max_tokens"] == 4096
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    first = result.structured_payload["holdings"][0]
    assert "recommendation" not in first
    assert len(first["warnings"]) == 2
    assert len(first["warnings"][0]) == 80


def test_minimax_vision_rejects_truncated_response(tmp_path, monkeypatch):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_ENABLED", True)
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_BASE_URL", "https://ark.example/v3")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_API_KEY", "secret")
    monkeypatch.setattr("app.portfolio.ocr_provider.settings.VOLCENGINE_ARK_VISION_MODEL", "minimax-m3")

    parser = VolcengineArkVisionPortfolioImageParser(
        http_post=lambda *_args, **_kwargs: _VisionResponse('{"holdings":[', "length"),
    )
    result = parser.parse_image(image)

    assert result.status == "cloud_parse_failed"
    assert "token 上限" in (result.error_summary or "")


def test_cloud_provider_requires_consent_before_any_parse(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="授权"):
        service.create_draft_from_upload(
            "sanitized.png",
            "image/png",
            b"fake",
            options={"parser_provider": "volcengine_ark_vision", "cloud_send_consent": False},
        )

    assert not list((tmp_path / "uploads").glob("*.png"))


def test_mock_cloud_vision_creates_editable_draft_and_keeps_portfolio_unchanged(tmp_path, monkeypatch):
    provider = MockVisionProvider()
    service = _service(tmp_path)
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)

    draft = service.create_draft_from_upload(
        "sanitized.png",
        "image/png",
        b"fake",
        options={"parser_provider": "volcengine_ark_vision", "cloud_send_consent": True},
    )

    assert provider.called is True
    assert draft.source_type == "cloud_vision_parsed_broker_screenshot"
    assert draft.parser_provider == "volcengine_ark_vision"
    assert draft.cloud_send_consent is True
    assert draft.needs_user_confirmation is True
    assert draft.account_summary_draft.cash_available_ocr == 10000
    assert draft.holding_rows_draft[0].normalized_symbol == "601899.SH"
    assert draft.holding_rows_draft[1].normalized_symbol == "002463.SZ"
    assert any("投资建议" in warning for warning in draft.parse_warnings)
    assert any("可用数量" in warning for warning in draft.holding_rows_draft[1].validation_warnings)
    assert not (tmp_path / "portfolio" / "default_portfolio.json").exists()


def test_cloud_failure_falls_back_to_manual_review_without_snapshot(tmp_path, monkeypatch):
    provider = MockVisionProvider(status="cloud_parse_failed")
    service = _service(tmp_path)
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)

    draft = service.create_draft_from_upload(
        "sanitized.png",
        "image/png",
        b"fake",
        options={"parser_provider": "volcengine_ark_vision", "cloud_send_consent": True},
    )

    assert draft.parse_status == "manual_review_required"
    assert draft.cloud_parse_status == "cloud_parse_failed"
    assert draft.holding_rows_draft == []
    assert draft.provider_error_summary == "mock timeout"
    assert not (tmp_path / "portfolio" / "default_portfolio.json").exists()


def test_trade_screenshot_record_only_writes_ledger_without_changing_portfolio(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    provider = MockVisionProvider(payload=_mock_trade_payload())
    service = _service(tmp_path)
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)
    service.portfolio_service.save_snapshot(PortfolioSnapshotInput(**{
        "cash_available": 50000,
        "positions": [
            {"symbol": "603259", "name": "药明康德", "quantity": 500, "avg_cost": 120},
        ],
    }))
    before = service.portfolio_service.load_snapshot()
    draft = service.create_draft_from_upload(
        "trades.png",
        "image/png",
        b"fake",
        options={
            "screenshot_kind": "trade_history",
            "parser_provider": "volcengine_ark_vision",
            "cloud_send_consent": True,
        },
    )

    result = service.confirm_draft(draft.draft_id, apply_transactions_to_portfolio=False)
    after = service.portfolio_service.load_snapshot()

    assert len(draft.transaction_rows_draft) == 2
    assert result["transaction_batch"]["applied_to_portfolio"] is False
    assert before.snapshot_id == after.snapshot_id
    assert service.trade_ledger.list_batches()[0]["transactions"][0]["side"] == "buy"


def test_trade_screenshot_can_apply_confirmed_transactions(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    provider = MockVisionProvider(payload=_mock_trade_payload())
    service = _service(tmp_path)
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)
    service.portfolio_service.save_snapshot(PortfolioSnapshotInput(**{
        "cash_available": 50000,
        "positions": [
            {"symbol": "603259", "name": "药明康德", "quantity": 500, "avg_cost": 120},
        ],
    }))
    draft = service.create_draft_from_upload(
        "trades.png",
        "image/png",
        b"fake",
        options={
            "screenshot_kind": "trade_history",
            "parser_provider": "volcengine_ark_vision",
            "cloud_send_consent": True,
        },
    )
    result = service.confirm_draft(draft.draft_id, apply_transactions_to_portfolio=True)
    snapshot = result["state"].snapshot
    positions = {position.symbol.split(".", 1)[0]: position for position in snapshot.positions}

    assert positions["601628"].quantity == 100
    assert positions["601628"].avg_cost == 40.33
    assert positions["603259"].quantity == 400
    assert positions["603259"].avg_cost == pytest.approx(118.6035)
    assert snapshot.cash_available == pytest.approx(58525.6)
    assert result["transaction_batch"]["applied_to_portfolio"] is True


def test_trade_screenshot_sale_can_create_negative_diluted_cost(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = _service(tmp_path)
    service.portfolio_service.save_snapshot(PortfolioSnapshotInput(**{
        "cash_available": 0,
        "positions": [
            {"symbol": "603259", "name": "药明康德", "quantity": 500, "avg_cost": 120},
        ],
    }))
    provider = MockVisionProvider(payload={
        "source_view": {"platform_guess": "同花顺", "screenshot_displayed_time": None, "warnings": []},
        "transactions": [{
            "raw_symbol": "603259",
            "raw_name": "药明康德",
            "side": "sell",
            "average_price": 200,
            "quantity": 400,
            "amount": 80000,
            "occurred_at": None,
            "warnings": [],
        }],
        "parse_warnings": [],
    })
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)

    draft = service.create_draft_from_upload(
        "trades.png",
        "image/png",
        b"fake",
        options={
            "screenshot_kind": "trade_history",
            "parser_provider": "volcengine_ark_vision",
            "cloud_send_consent": True,
        },
    )
    result = service.confirm_draft(draft.draft_id, apply_transactions_to_portfolio=True)
    position = result["state"].snapshot.positions[0]

    assert position.quantity == 100
    assert position.avg_cost == -200


def test_cloud_confirm_source_and_block_available_quantity_over_quantity(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    provider = MockVisionProvider()
    service = _service(tmp_path)
    monkeypatch.setattr(service, "_provider_for", lambda provider_name: provider)
    draft = service.create_draft_from_upload(
        "sanitized.png",
        "image/png",
        b"fake",
        options={"parser_provider": "volcengine_ark_vision", "cloud_send_consent": True},
    )

    with pytest.raises(ValueError, match="可用数量大于持仓数量"):
        service.confirm_draft(draft.draft_id)

    rows = draft.holding_rows_draft
    rows[1].available_quantity = 200
    rows[0].primary_theme = "METAL_RESOURCE"
    rows[1].primary_theme = "AI_PCB_HARDWARE"
    update = service.update_draft(draft.draft_id, PortfolioImportDraftUpdate(holding_rows_draft=rows))
    result = service.confirm_draft(update.draft_id)

    snapshot = result["state"].snapshot
    assert snapshot.source_type == "broker_screenshot_cloud_parsed_user_confirmed"
    assert snapshot.positions[0].source_type == "manual_account"
    assert "云端视觉解析" in (snapshot.positions[0].source_name or "")
    assert snapshot.positions[0].broker_screenshot_price == 31.64
    assert snapshot.positions[0].system_quote_price == 31.38
    assert service.portfolio_service.list_manual_evidence()[0].include_in_analysis_packet is False
