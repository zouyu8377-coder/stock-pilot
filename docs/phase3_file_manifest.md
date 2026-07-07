# Phase 3 File Manifest

Last updated: 2026-05-25

## Untracked Phase 0-3 Files

Current untracked count from `git ls-files --others --exclude-standard`: 45.

Source and API:

- `backend/app/analysis_packet/__init__.py`
- `backend/app/analysis_packet/packet_service.py`
- `backend/app/analysis_packet/snapshot_builder.py`
- `backend/app/api/analysis_packet.py`
- `backend/app/api/facts.py`
- `backend/app/api/portfolio.py`
- `backend/app/api/snapshot.py`
- `backend/app/evidence/__init__.py`
- `backend/app/evidence/schemas.py`
- `backend/app/facts/__init__.py`
- `backend/app/facts/common.py`
- `backend/app/facts/disclosure_service.py`
- `backend/app/facts/dragon_tiger_service.py`
- `backend/app/facts/etf_service.py`
- `backend/app/portfolio/__init__.py`
- `backend/app/portfolio/schemas.py`
- `backend/app/portfolio/service.py`
- `backend/app/tushare/__init__.py`
- `backend/app/tushare/cache.py`
- `backend/app/tushare/client.py`
- `backend/app/tushare/exceptions.py`

Scripts and tests:

- `backend/scripts/generate_phase3_acceptance_samples.py`
- `scripts/tushare_capability_probe.py`
- `backend/tests/test_phase3_analysis_packet.py`
- `backend/tests/test_stage0_foundation.py`
- `backend/tests/test_stage1_facts.py`
- `backend/tests/test_stage2_portfolio.py`

Frontend:

- `frontend/src/components/AnalysisPacketPanel.vue`
- `frontend/src/components/AutoFactsPanel.vue`
- `frontend/src/components/PortfolioPanel.vue`

Docs and samples:

- `docs/acceptance_samples/phase3_portfolio_packet.json`
- `docs/acceptance_samples/phase3_portfolio_packet.md`
- `docs/acceptance_samples/phase3_single_etf_packet.json`
- `docs/acceptance_samples/phase3_single_etf_packet.md`
- `docs/acceptance_samples/phase3_single_holding_packet.json`
- `docs/acceptance_samples/phase3_single_holding_packet.md`
- `docs/phase2_acceptance_checklist.md`
- `docs/phase2_recovery_report.md`
- `docs/phase3_implementation_report.md`
- `docs/stage0_foundation_notes.md`
- `docs/tushare_capability_report.json`
- `docs/tushare_capability_report.md`

## Modified Tracked Files

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

## Recommended To Add Later

Add Phase 0-3 source, tests, frontend components, and docs after review:

- `backend/app/analysis_packet/`
- `backend/app/api/analysis_packet.py`
- `backend/app/api/facts.py`
- `backend/app/api/portfolio.py`
- `backend/app/api/snapshot.py`
- `backend/app/evidence/`
- `backend/app/facts/`
- `backend/app/portfolio/`
- `backend/app/tushare/`
- `backend/tests/`
- `frontend/src/components/AnalysisPacketPanel.vue`
- `frontend/src/components/AutoFactsPanel.vue`
- `frontend/src/components/PortfolioPanel.vue`
- `docs/phase*_*.md`
- `docs/acceptance_samples/phase3_*`
- `backend/scripts/generate_phase3_acceptance_samples.py`
- `scripts/tushare_capability_probe.py`

## Do Not Add

Do not add secrets or local run data:

- `backend/.env`
- any file containing `TUSHARE_TOKEN`
- `backend/data/tushare/`
- `backend/data/portfolio/`
- `backend/data/analysis_snapshots/`
- `backend/data/phase3_acceptance_demo/`
- real account exports or real manual evidence attachments
- cache, parquet, log, and generated runtime data

## Gitignore Notes

Already present or added:

- `backend/data/analysis_snapshots/`
- `backend/data/portfolio/`
- `backend/data/tushare/`
- `backend/data/phase3_acceptance_demo/`
- `backend/data/*.lock`, `*.parquet`, `*.log`
- `.env`, `.env.local`

Before committing, re-run `git status --short` and inspect any files under `backend/data/`.
