# Phase 3.6B Acceptance Checklist

## Automated

- [x] Legal image upload creates an import draft.
- [x] Non-image upload is rejected.
- [x] Oversized image upload is rejected.
- [x] Mock OCR complete result creates multiple draft rows.
- [x] Partial/failed OCR creates warnings and manual-entry draft.
- [x] `601899` resolves to `601899.SH`.
- [x] Name/code conflict requires user confirmation.
- [x] Name-only input can return candidate symbols.
- [x] `quantity` and `available_quantity` are separate fields.
- [x] Screenshot price and system quote price are stored separately.
- [x] Draft confirmation is required before formal snapshot save.
- [x] Confirmed import creates a new snapshot id and history file.
- [x] Confirmed holding can associate existing external driver profile context.
- [x] Screenshot evidence defaults to `include_in_analysis_packet = false`.
- [x] Upload/draft/snapshot directories are ignored by Git.
- [x] No external LLM call is made by import tests or services.
- [x] Existing single-stock and portfolio packet tests still pass.
- [x] Frontend build passes.

## Manual Browser Acceptance Required

- [ ] Upload the synthetic sample or another fully sanitized screenshot.
- [ ] Confirm the page shows a draft instead of directly saving a portfolio.
- [ ] Check 紫金矿业, 深南电路/沪电股份, 中钨高新, and ETF code/name matching.
- [ ] Check quantity, available quantity, cost, and screenshot price labels.
- [ ] Correct at least one draft field and save the draft.
- [ ] Confirm the current formal portfolio is unchanged before confirmation.
- [ ] Click "确认并保存为新的持仓快照".
- [ ] Confirm a new snapshot is created and older snapshot files remain.
- [ ] Generate a portfolio Analysis Packet from the confirmed sanitized portfolio.
- [ ] Verify screenshot price and system quote price are not confused.
- [ ] Verify screenshot attachment is not automatically included in Packet manual evidence.
- [ ] Verify no account-level AI advice or dashboard was added.

## Sensitive Data Gate

- [x] No real screenshot committed.
- [x] No real account position committed.
- [x] No token committed.
- [x] No OCR raw text from a real account committed.
- [x] No generated account export committed.

