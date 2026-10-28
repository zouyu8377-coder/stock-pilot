from __future__ import annotations

import json

from app.disclosure_verification import service


def test_verify_symbol_disclosures_requires_verified_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service.settings, "DISCLOSURE_VERIFICATION_MAX_DOCUMENTS", 2)
    monkeypatch.setattr(service, "_extract_pdf_pages", lambda content: [
        "[第1页]\nAI服务器相关产品收入同比增长30%，但公司未披露该业务收入占比。"
    ])

    announcements = [{
        "announcement_id": "ann-1",
        "title": "2025年年度报告",
        "announced_at": "2026-04-20",
        "pdf_url": "https://example.test/ann-1.pdf",
        "source": "cninfo",
    }]
    model_payload = {
        "items": [
            {
                "question": "AI服务器相关收入占比是否提升？",
                "status": "partially_supported",
                "conclusion": "收入增长，但占比未披露。",
                "quote": "AI服务器相关产品收入同比增长30%",
                "page": 1,
                "announcement_id": "ann-1",
                "confidence": 0.88,
            },
            {
                "question": "毛利率是否改善？",
                "status": "supported",
                "conclusion": "模型编造的结论。",
                "quote": "毛利率大幅提升",
                "page": 1,
                "announcement_id": "ann-1",
                "confidence": 0.9,
            },
        ],
        "overall_summary": "一项部分支持，一项无原文依据。",
    }

    result = service.verify_symbol_disclosures(
        "002463",
        force=True,
        announcement_fetcher=lambda symbol, start, end: announcements,
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=lambda prompt: json.dumps(model_payload, ensure_ascii=False),
    )

    assert result["status"] == "verified"
    assert result["items"][0]["status"] == "partially_supported"
    assert result["items"][0]["quote_verified"] is True
    assert result["items"][1]["status"] == "not_found"
    assert result["items"][1]["quote_verified"] is False
    assert result["counts"]["partially_supported"] == 1
    assert result["counts"]["not_found"] == 1
    assert service.load_disclosure_verification("002463")["status"] == "verified"


def test_verify_symbol_disclosures_degrades_when_pdf_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service, "_extract_pdf_pages", lambda content: [])

    result = service.verify_symbol_disclosures(
        "002463",
        force=True,
        announcement_fetcher=lambda symbol, start, end: [{
            "announcement_id": "ann-1",
            "title": "2025年年度报告",
            "announced_at": "2026-04-20",
            "pdf_url": "https://example.test/ann-1.pdf",
        }],
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=lambda prompt: "{}",
    )

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["pending_announcement_ids"] == ["ann-1"]
    assert result["processed_announcement_ids"] == []


def test_batch_limit_keeps_unread_announcements_for_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service.settings, "DISCLOSURE_VERIFICATION_MAX_DOCUMENTS", 1)
    monkeypatch.setattr(service, "_cache_is_fresh", lambda payload: False)
    monkeypatch.setattr(service, "_symbol_context", lambda symbol: {"questions": ["revenue"], "keywords": []})
    monkeypatch.setattr(service, "_extract_pdf_pages", lambda content: ["revenue"])
    monkeypatch.setattr(service, "_select_relevant_text", lambda *args: "revenue")
    monkeypatch.setattr(service, "_build_prompt", lambda *args: "test")
    monkeypatch.setattr(service, "_validate_model_items", lambda payload, docs: [
        {"status": "supported", "announcement_id": doc["announcement_id"]} for doc in docs
    ])
    announcements = [{"announcement_id": key, "pdf_url": key, "announced_at": key} for key in ("1", "2", "3")]
    def run():
        return service.verify_symbol_disclosures("002463", announcement_fetcher=lambda *args: list(announcements), pdf_fetcher=lambda url: b"pdf", model_caller=lambda prompt: "{}")
    assert len(run()["pending_announcement_ids"]) == 2
    assert len(run()["pending_announcement_ids"]) == 1
    assert run()["processed_announcement_ids"] == ["1", "2", "3"]


def test_cached_verification_only_calls_model_for_new_announcement(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service, "_cache_is_fresh", lambda payload: False)
    monkeypatch.setattr(service, "_extract_pdf_pages", lambda content: ["[page 1]\nrevenue grew"])
    calls = []

    first = [{
        "announcement_id": "ann-1",
        "title": "annual report",
        "announced_at": "2026-04-20",
        "pdf_url": "https://example.test/ann-1.pdf",
    }]
    second = [{
        "announcement_id": "ann-2",
        "title": "investor relations",
        "announced_at": "2026-06-13",
        "pdf_url": "https://example.test/ann-2.pdf",
    }, *first]

    def model(prompt):
        calls.append(prompt)
        announcement_id = "ann-2" if "ann-2.pdf" in prompt else "ann-1"
        return json.dumps({
            "items": [{
                "question": "revenue?",
                "status": "supported",
                "conclusion": "supported",
                "quote": "revenue grew",
                "page": 1,
                "announcement_id": announcement_id,
                "confidence": 0.9,
            }],
        })

    service.verify_symbol_disclosures(
        "002463",
        announcement_fetcher=lambda symbol, start, end: first,
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=model,
    )
    unchanged = service.verify_symbol_disclosures(
        "002463",
        announcement_fetcher=lambda symbol, start, end: first,
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=model,
    )
    updated = service.verify_symbol_disclosures(
        "002463",
        announcement_fetcher=lambda symbol, start, end: second,
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=model,
    )

    assert len(calls) == 2
    assert unchanged["trigger"] == "announcement_index_no_change"
    assert updated["trigger"] == "new_announcement"
    assert {item["announcement_id"] for item in updated["documents"]} == {"ann-1", "ann-2"}


def test_verification_prioritizes_new_report_over_old_keyword_match(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service.settings, "DISCLOSURE_VERIFICATION_MAX_DOCUMENTS", 1)
    monkeypatch.setattr(service, "_extract_pdf_pages", lambda content: ["[page 1]\nPCB产能增加"])

    announcements = [
        {
            "announcement_id": "recent",
            "title": "年度报告",
            "announced_at": "2026-04-27",
            "pdf_url": "https://example.test/recent.pdf",
        },
        {
            "announcement_id": "relevant",
            "title": "AI PCB产能投资项目公告",
            "announced_at": "2025-12-16",
            "pdf_url": "https://example.test/relevant.pdf",
        },
    ]

    result = service.verify_symbol_disclosures(
        "000657",
        force=True,
        announcement_fetcher=lambda symbol, start, end: announcements,
        pdf_fetcher=lambda url: b"%PDF mocked",
        model_caller=lambda prompt: json.dumps({
            "items": [{
                "question": "PCB产能是否增加？",
                "status": "supported",
                "conclusion": "产能增加",
                "quote": "PCB产能增加",
                "page": 1,
                "announcement_id": "relevant",
                "confidence": 0.9,
            }],
        }, ensure_ascii=False),
    )

    assert result["documents"][0]["announcement_id"] == "recent"
