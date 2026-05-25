# Phase 3.5 Baseline Closure Report

Last updated: 2026-05-25

## Current Branch

- Branch at start: `master`

## Git State at Start

Tracked modified files:

- `.gitignore`
- `backend/.env.example`
- `backend/.gitignore`
- `backend/app/company_profile/providers/tushare_provider.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/requirements.txt`
- `backend/scripts/bootstrap_stock_metadata.py`
- `frontend/src/App.vue`
- `frontend/src/api/client.ts`

Untracked file summary:

- Phase 0-3 backend source under `backend/app/analysis_packet/`, `backend/app/evidence/`, `backend/app/facts/`, `backend/app/portfolio/`, `backend/app/tushare/`
- New API routes: `backend/app/api/analysis_packet.py`, `backend/app/api/facts.py`, `backend/app/api/portfolio.py`, `backend/app/api/snapshot.py`
- Phase 0-3 tests under `backend/tests/`
- Phase 3 sample generator under `backend/scripts/generate_phase3_acceptance_samples.py`
- Frontend Packet / Facts / Portfolio components
- Phase 2/3 docs and acceptance samples
- Tushare capability probe script and reports

Initial `git diff --stat` summary:

- 10 tracked files changed
- 305 insertions, 7 deletions

Initial `git ls-files --others --exclude-standard` count: 45 files.

## Existing Phase 3.5 Verification Results

From `docs/phase3_hardening_report.md`:

- `cd backend; python -m pytest`: passed, 28 tests.
- `cd backend; python -m pytest tests/test_phase3_analysis_packet.py -q`: passed, 6 tests.
- `cd backend; python -m compileall app`: passed.
- `cd frontend; npm run build`: passed.
- FastAPI smoke: Phase 2 four routes and Phase 3 packet/evidence include routes returned 200.

## Closure Steps for This Round

1. Create local project backup before Git add/commit.
2. Audit `.gitignore`, `backend/.gitignore`, environment examples, sensitive runtime directories and acceptance samples.
3. Scan candidate files for token/API key/secret/account/export risks without printing secret values.
4. If safe, create `feature/analysis-packet-v1-baseline` and commit a Phase 3.5 baseline.
5. Prepare user-facing manual browser acceptance checklist.
6. Prepare sanitized trial run guide.
7. Prepare user risk and repo treatment configuration confirmation document.
8. Stop after Phase 3.5 closure; do not enter Phase 4 or Phase 5.

## Scope Restrictions

This closure round must not:

- Develop Phase 4 or Phase 5.
- Add new business functionality.
- Connect new data sources.
- Refactor Analysis Packet, portfolio, evidence or facts architecture.
- Clean historical mojibake outside closure needs.
- Send Packet/account/attachments to any external LLM.
- Commit tokens, real account data, exports or attachments.
- Use destructive Git commands.

## Backup Result

- Backup status: succeeded.
- Backup directory: `C:/Project/Stock-Pilot_backup_after_phase3_5_20260525_090547`
- Backup time: 2026-05-25 09:05:47 local time.
- Project root confirmed: `C:/Project/Stock-Pilot`.
- Backup includes source, untracked Phase 0-3 files, tests, docs, samples, `.gitignore`, and config example files.
- Backup intentionally excludes dependency cache / repository metadata directories such as `node_modules` and `.git`.
- No sensitive values were printed or written into this report.

## Sensitive File and Ignore Audit

Ignore checks passed for:

- `backend/.env`
- `backend/data/portfolio/`
- `/backend/data/tushare/`
- `/backend/data/analysis_snapshots/`
- `/backend/data/phase3_acceptance_demo/`
- runtime cache directories
- `frontend/dist/`
- `frontend/node_modules/`
- Python `__pycache__/`
- `*.log`

Additional ignore rules added in this closure round:

- `backend/data/account_exports/`
- `backend/data/exports/`
- `backend/data/attachments/`
- `backend/data/uploads/`
- `backend/data/screenshots/`
- `account_exports/`
- `exports/`
- `attachments/`
- `uploads/`
- `screenshots/`

Sensitive pattern scan result:

- Candidate non-ignored text files were scanned for token/API, `sk-` style keys, bearer tokens, long hex tokens, and secret-like assignments.
- No real secret-like findings were detected in candidate files.
- Findings containing only environment variable names or documented placeholders were reviewed and allowed.
- `backend/.env.example` contains placeholders only.
- Current Tushare provider and metadata bootstrap script read `settings.TUSHARE_TOKEN`; no hard-coded Token value remains in those files.

Files that must remain permanently excluded from Git:

- `backend/.env`
- `backend/data/portfolio/`
- `backend/data/tushare/`
- `backend/data/analysis_snapshots/`
- `/backend/data/account_exports/`
- `/backend/data/exports/`
- `/backend/data/attachments/`
- real account exports
- user-uploaded attachments and screenshots
- local runtime caches and logs

Git baseline permission decision: allowed, provided `git add -n .` preview does not show ignored sensitive paths.

## Acceptance Sample Review

Reviewed files:

- `docs/acceptance_samples/phase3_single_etf_packet.json`
- `docs/acceptance_samples/phase3_single_etf_packet.md`
- `docs/acceptance_samples/phase3_single_holding_packet.json`
- `/docs/acceptance_samples/phase3_single_holding_packet.md`
- `docs/acceptance_samples/phase3_portfolio_packet.json`
- `/docs/acceptance_samples/phase3_portfolio_packet.md`

Conclusion:

- Samples are demo / sanitized acceptance outputs.
- Portfolio sample uses synthetic values: total assets 100000, cash 30000, repo 20000, demo holdings 20000/20000/10000.
- Manual evidence entries are non-sensitive demo evidence.
- Attachment and screenshot fields are null.
- No token, API key, local secret path, or non-null private attachment path was found.
- Samples are allowed to enter the Git baseline.

## Git Baseline Result

- Baseline status: succeeded.
- Branch: `feature/analysis-packet-v1-baseline`.
- Baseline commit: `bb3fa99`.
- Commit message: `Build evidence-based analysis packet and portfolio baseline`.
- Final sensitive path check confirmed `backend/.env`, portfolio data, Tushare cache, analysis snapshots, account exports, attachments, uploads and screenshots remain ignored.

## Browser Manual Acceptance

`browser manual acceptance = pending_user_verification`

Prepared checklist: `docs/manual_browser_acceptance_checklist.md`.

## Sanitized Trial Run

Prepared guide: `docs/sanitized_trial_run_guide.md`.

Recommendation remains: use sanitized demo portfolio first; do not import full real account data yet.

## User Risk Configuration Confirmation

Prepared document: `docs/user_risk_configuration_to_confirm.md`.

User confirmation is still required for:

- single-position limit convention;
- theme-limit convention;
- cash-floor convention;
- reverse repo cash-equivalent and liquidity convention.
