# Phase 3.6C Acceptance Checklist

## Completed Locally

- [x] Added `local_noop` and `volcengine_ark_vision` provider choices.
- [x] Added independent Fire/Ark vision env configuration.
- [x] Added provider status API without API key exposure.
- [x] Added upload API consent fields.
- [x] Rejects cloud parsing when consent is not checked.
- [x] Cloud provider produces editable draft only.
- [x] Cloud failure falls back to manual-review draft.
- [x] User confirmation creates a new portfolio snapshot.
- [x] Confirmation source records cloud parsed draft plus user confirmation.
- [x] Screenshot evidence defaults to `include_in_analysis_packet=false`.
- [x] Symbol/name standardization remains local.
- [x] `quantity` and `available_quantity` semantics are preserved.
- [x] `broker_screenshot_price` and `system_quote_price` remain separate.
- [x] `data_coverage` no longer marks rule-inferred company business as provided hard fact.
- [x] Daily-K boundary marks 5/20/60-day returns as derived observations.
- [x] External driver and shared driver tests remain passing.
- [x] No personal investment dashboard was built.
- [x] No Phase 4 or Phase 5 work was started.

## Test Results

- [x] `cd backend && python -m pytest -q` -> `48 passed`
- [x] `cd backend && python -m compileall app` -> passed
- [x] `cd frontend && npm run build` -> passed
- [x] API smoke covered by FastAPI `TestClient` tests.

## Not Claimed

- [ ] Real Volcengine Ark cloud call passed.
- [ ] User browser workflow passed with real local `.env`.
- [ ] Real account screenshot parsed.
- [ ] Real account data exported.

These remain user-side manual acceptance items.
