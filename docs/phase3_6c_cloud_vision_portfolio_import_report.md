# Phase 3.6C Cloud Vision Portfolio Import Report

## Baseline

- Branch at start: `feature/portfolio-screenshot-draft-import`
- Latest baseline commit observed: `8647e5f Show frontend version and packet chain guard`
- Required 3.6A/3.6A-Fix/3.6B commits were present in history: `0927317`, `1ff6436`, `1f02688`
- Work branch: `feature/cloud-vision-portfolio-import`

## Scope Implemented

- Added an optional `volcengine_ark_vision` portfolio screenshot parser alongside `local_noop`.
- Added independent vision configuration, separate from the existing investment/deep-analysis LLM configuration.
- Added provider status API and upload form parameters:
  - `parser_provider`
  - `cloud_send_consent`
  - `user_notice_acknowledged_at`
- Added a consent-gated frontend flow with cloud privacy notice.
- Added strict JSON extraction prompt and local JSON/type validation into editable import drafts.
- Kept all model output as `portfolio_import_draft` / `cloud_vision_parsed_broker_screenshot` until user confirmation.
- On confirmation, creates a new `manual_account` snapshot with source `broker_screenshot_cloud_parsed_user_confirmed`.
- Screenshot evidence remains `include_in_analysis_packet = false`.
- Fixed `data_coverage` so rule-inferred business context is no longer marked as provided hard fact.
- Added daily-K boundary text: OHLC/volume/amount/daily change are local facts; 5/20/60-day returns are derived observations.

## Volcengine Ark Vision Integration

- Provider name: `volcengine_ark_vision`
- User-facing name: `云端视觉解析`
- Image transfer method implemented: OpenAI-compatible chat completions with a base64 `data:` URL image input in request memory.
- No public temporary URL is created.
- The implementation uses `VOLCENGINE_ARK_VISION_BASE_URL` plus `/chat/completions` if needed.
- The request prompt only asks for table/account field extraction and strict JSON. It explicitly forbids investment advice.

## Configuration

Real values are read only from local environment variables:

- `PORTFOLIO_VISION_PROVIDER`
- `VOLCENGINE_ARK_VISION_ENABLED`
- `VOLCENGINE_ARK_VISION_BASE_URL`
- `VOLCENGINE_ARK_VISION_API_KEY`
- `VOLCENGINE_ARK_VISION_MODEL`
- `VOLCENGINE_ARK_VISION_TIMEOUT`
- `VOLCENGINE_ARK_VISION_MAX_TOKENS`
- `VOLCENGINE_ARK_VISION_JSON_MODE`

`.env.example` contains only placeholders/empty values. API keys are not returned by provider status.

## Consent and Privacy Boundary

- `local_noop` never sends the image to cloud.
- `volcengine_ark_vision` rejects upload unless `cloud_send_consent=true`.
- The frontend treats selecting `云端视觉解析` and clicking `识别截图` as explicit authorization for that upload.
- Stock-Pilot does not automatically save a formal portfolio snapshot after parsing.
- Stock-Pilot does not automatically call the investment analysis LLM.
- The cloud provider result is a draft; the user must verify and confirm before a portfolio snapshot is written.
- Cloud service retention and processing are controlled by the user's service configuration and vendor policy.

## Failure Degradation

Cloud timeout, misconfiguration, non-JSON response, unsupported image input, or parse failure produce:

- `cloud_parse_failed`
- `manual_review_required`
- editable draft retained locally
- no formal portfolio snapshot
- no automatic retry

## Local Validation

- JSON must parse as an object.
- `holdings` rows are converted into `HoldingRowDraft`.
- Symbols/names are resolved locally by `resolve_symbol_or_name`.
- `601899` resolves to `601899.SH`.
- `002463` resolves to `002463.SZ`.
- Negative quantities are rejected/warned.
- `available_quantity > quantity` creates a warning and blocks confirmation.
- Suspicious quantity/price/market value mismatch creates a warning.
- Investment-advice-like fields from the model are ignored and warned.

## Packet Verification

Mock/local tests verify:

- User confirmation creates a new snapshot.
- Confirmed holdings enter single/portfolio packet data through `manual_account`.
- `broker_screenshot_price` and `system_quote_price` remain separate.
- Screenshot evidence is not exported into Packet by default.
- External driver matching remains available through the existing local resolver and packet builder.
- Shared driver de-duplication tests remain green.
- Packet generation does not call the investment analysis LLM.

## Real Cloud Call Status

Real Fire/Ark cloud invocation was not executed in this agent environment. Verification completed with mock vision provider and local API/build tests only. The user must run the manual browser checklist with their own `.env` configuration before treating cloud parsing as production-verified.

## Security and Git Check

- `.env` is gitignored.
- Uploads, portfolio snapshots, analysis packet exports, attachments, screenshots, and logs are gitignored.
- Tests and status responses do not expose API keys.
- The provider stores no image base64, full request payload, or raw account JSON in logs.
- This report contains no token, no real screenshot, no real account data, and no attachment.

## Test Results

- `cd backend && python -m pytest -q`: `48 passed`
- `cd backend && python -m compileall app`: passed
- `cd frontend && npm run build`: passed

## Known Limits

- Real cloud availability depends on the user's Ark endpoint/model supporting OpenAI-compatible multimodal image input.
- Provider health check reports configured state but does not send a real image.
- True model accuracy must be judged by the editable draft and user confirmation.

## Next Step Recommendation

Do not enter dashboard MVP planning until the user completes one real cloud parsing run with a脱敏 screenshot, confirms a local snapshot, and verifies portfolio plus single-stock packets. This round did not build a personal investment dashboard and did not enter Phase 4 or Phase 5.
