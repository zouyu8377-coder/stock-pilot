# Phase 3.6B Portfolio Screenshot Import Report

## Baseline and Branch

- Baseline commit: `1ff6436` (`Fix visible analysis packet export chain`).
- Development branch: `feature/portfolio-screenshot-draft-import`.
- Initial working tree: clean.
- Current scope: screenshot upload, OCR/parse draft, standard symbol matching, user edit, explicit confirmation, new portfolio snapshot, portfolio Analysis Packet reuse.
- Explicitly out of scope: personal investment dashboard, account-level AI command page, broker sync, auto trading, new macro drivers, Phase 4/5.

## Service Ports

- Found old `uvicorn --reload --port 8000` process at startup and stopped it.
- `127.0.0.1:8000` has no listening backend after cleanup.
- This round uses backend `http://127.0.0.1:8001`.
- Frontend default API base URL was changed from `127.0.0.1:8000` to `127.0.0.1:8001`.
- Backend `http://127.0.0.1:8001/health` returned `ok` after restart.

## Existing Manual Entry Review

1. Manual entry did not infer name from code or code from name because `PortfolioPanel.vue` only saved raw user inputs and `PortfolioService` only used quote name as a fallback during enrichment. There was no resolver in the save path.
2. `quantity` means total position quantity. `available_quantity` means currently sellable quantity, and trade simulation already uses it for sell validation. The UI labels were unclear and several Chinese strings were mojibake, so this round replaces them with explicit Chinese labels.
3. Standard Tushare-style symbols such as `601899.SH`, `002916.SZ`, and `159934.SZ` are now normalized through `to_ts_code`.
4. `601899` now resolves to `601899.SH` and a standard name when metadata or fallback mapping is available.
5. Name-only input such as `紫金矿业` now produces a candidate standard symbol through local metadata/fallback matching.
6. OCR draft confirmation reuses `PortfolioSnapshotInput` and `PortfolioService.save_snapshot`; it does not create a second incompatible account structure.

## OCR Provider and Degradation

- Added a replaceable provider interface in `backend/app/portfolio/ocr_provider.py`.
- Default provider is `local_noop`: it saves the screenshot and creates an auditable manual-entry draft when no reliable local OCR engine is configured.
- A local sidecar text mode is supported for controlled/manual testing.
- Automated tests use a mock local OCR provider with fully sanitized rows.
- No external LLM or unspecified cloud OCR call is made.

## Data Flow

Implemented state flow:

```text
uploaded
-> ocr_processing
-> draft_parsed / parse_incomplete
-> needs_user_confirmation
-> user_confirmed
-> saved_as_portfolio_snapshot
```

Failure states:

```text
ocr_failed
parse_incomplete
user_rejected
```

Any non-confirmed draft keeps `saved_snapshot_id = null` and does not write the formal portfolio snapshot.

## Data Model and Privacy

- Added `PortfolioImportDraft`, `AccountSummaryDraft`, `HoldingRowDraft`, and `SymbolCandidate`.
- Uploads are stored under ignored local data directories.
- Drafts include OCR raw text locally, but no real OCR text or image is committed.
- Confirmed positions are stored as `manual_account`.
- Screenshot attachment evidence is created with `include_in_analysis_packet = false`.
- `.gitignore` explicitly excludes uploads, import drafts, portfolio snapshots, exports, attachments, and account data.

## Confirmation and Snapshot Save

- Confirmation endpoint blocks unresolved symbols and missing required fields.
- Confirmation creates a new portfolio snapshot id and writes it to a snapshot history directory while updating the current portfolio view.
- Old snapshot files are not deleted or overwritten.
- Snapshot source is `broker_screenshot_confirmed`; position source is `manual_account`.

## Price Separation

Confirmed positions preserve:

- `broker_screenshot_price`
- `broker_screenshot_price_source`
- `broker_screenshot_price_time = null` when no screenshot time is known
- `system_quote_price`
- `system_quote_retrieved_at`
- `system_quote_market_time = null`
- `quote_time_status = unavailable`

Screenshot prices are only for reconciliation and do not overwrite system quote prices.

## External Driver Association

- Draft rows call the existing external driver context builder after symbol resolution.
- Configured symbols show their profile id and mapping status as read-only context.
- No new macro factor or external driver mapping was added.
- Theme tags are suggested/contextual only; user fields are not auto-decided by OCR.

## Frontend

- Existing portfolio area now includes a minimal screenshot import flow.
- User can upload an image, view OCR/parse state, edit row fields, select candidates, save draft changes, reject the draft, and confirm into a new snapshot.
- Labels clarify:
  - 持仓数量：当前账户持有的总股数
  - 可用数量：当前可卖出的股数
  - 平均成本：用户账户展示的持仓成本价
  - 截图现价：截图画面中的价格，仅用于复核，不等同系统最新行情
- Browser render check on `127.0.0.1:5173` found the portfolio import entry visible after expanding the panel and no console errors.

## Future Direction Recorded, Not Implemented

Future personal investment dashboard direction:

- Product home can evolve from single-stock search into a personal investment dashboard.
- Dashboard may show total assets, available cash, repo, current holdings, `primary_theme`, `theme_tags`, external drivers, risk reminders, candidate trade simulations, and portfolio Analysis Packet.
- Single-stock analysis should remain as drill-down from holdings.
- Future AI output should be based on portfolio packets and produce account-level review/action candidates, not isolated buy/sell conclusions.
- Possible future action states: risk-control watch, hold and observe, opportunity watch, candidate action pending confirmation, insufficient evidence.

This round did not implement the dashboard or account-level AI.

## Verification Summary

- `cd backend && python -m pytest -q`: 41 passed.
- `cd backend && python -m compileall app`: passed.
- `cd frontend && npm run build`: passed.
- API smoke coverage is included in `backend/tests/test_phase3_6b_portfolio_import.py`.

