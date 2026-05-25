# Phase 2 Acceptance Checklist

| Acceptance item | Verification method | Current result | API or page | Manual verification needed |
| --- | --- | --- | --- | --- |
| Git and codebase recovery audit completed | `git status`, `git branch --show-current`, `git log --oneline -n 8`, `git diff --stat`, `git diff`, `git diff --cached --stat` | Passed | N/A | Review dirty/untracked files before commit |
| Stage 0 EvidenceItem schema usable | `python -m pytest tests/test_stage0_foundation.py` | Passed | `backend/app/evidence/schemas.py` | None |
| Stage 0 AnalysisSnapshot supports portfolio fields | pytest import/construction coverage | Passed | `/api/snapshot/{symbol}`, `/api/portfolio/analysis-snapshot` | None |
| Stage 1 automatic facts still construct evidence | `python -m pytest tests/test_stage1_facts.py` | Passed | `/api/facts/etf/{symbol}`, `/api/facts/dragon-tiger/{symbol}`, `/api/facts/disclosures/{symbol}` | Tushare token availability in real environment |
| Empty portfolio with cash | `test_empty_portfolio_with_cash_is_valid` | Passed | `/api/portfolio` | None |
| Ordinary portfolio valuation and PnL | `test_portfolio_snapshot_valuation_and_exposures` | Passed | `/api/portfolio`, Portfolio panel | Verify real quote provider values during market/data availability |
| Cash and repo metrics | `test_portfolio_snapshot_valuation_and_exposures` | Passed | `/api/portfolio`, Portfolio panel | Confirm user's preferred repo cash-equivalent treatment |
| Primary theme unique attribution | `test_portfolio_snapshot_valuation_and_exposures` | Passed | `/api/portfolio` | Confirm user theme taxonomy |
| Composite exposure is not double counted | `test_portfolio_snapshot_valuation_and_exposures` | Passed | `/api/portfolio` | None |
| Missing price does not fabricate value | `test_missing_price_does_not_fabricate_market_value_or_pnl` | Passed | `/api/portfolio` | Frontend status display could be improved later |
| Single-position limit warning | `test_single_position_limit_becomes_system_hypothesis` | Passed | `/api/portfolio`, `/api/portfolio/analysis-snapshot` | Confirm real single-position limit |
| Theme limit warning | Metrics code path and expanded test inputs | Passed | `/api/portfolio` | Confirm real theme limit |
| Cash floor warning | Simulation cash-overrun test and metrics code path | Passed | `/api/portfolio`, `/api/portfolio/simulate` | Confirm real cash floor |
| Rule reminders are hypotheses, not facts | `test_single_position_limit_becomes_system_hypothesis` | Passed | `/api/portfolio/analysis-snapshot` | None |
| Buy simulation is read-only | `test_trade_simulation_reports_structure_change` | Passed | `/api/portfolio/simulate` | None |
| Buy simulation supports requested field aliases | `test_trade_simulation_accepts_requested_aliases_and_cash_warning` | Passed | `/api/portfolio/simulate` | None |
| Buy over cash returns reminder, not auto-correction | `test_trade_simulation_accepts_requested_aliases_and_cash_warning` | Passed | `/api/portfolio/simulate` | None |
| Sell simulation rejects over-available quantity | `test_sell_simulation_rejects_quantity_above_available` | Passed | `/api/portfolio/simulate` | None |
| Simulation does not modify saved snapshot | `test_trade_simulation_reports_structure_change` | Passed | `/api/portfolio/simulate` | None |
| Manual shareholder count evidence | `test_manual_evidence_enters_portfolio_snapshot` | Passed | `/api/portfolio/manual-evidence` | Verify actual entered source/date |
| Manual intraday observation evidence | `test_manual_evidence_enters_portfolio_snapshot` | Passed | `/api/portfolio/manual-evidence` | Verify actual entered source/date |
| Manual evidence converts to EvidenceItem | `test_manual_evidence_enters_portfolio_snapshot` | Passed | `/api/portfolio/analysis-snapshot` | None |
| Manual evidence keeps `manual_evidence` category | `test_manual_evidence_enters_portfolio_snapshot` | Passed | `/api/portfolio/analysis-snapshot` | None |
| Minimal frontend access exists | `npm run build` | Passed | Main app Portfolio panel | User should manually exercise forms in browser |
| Backend import/start smoke | `python -m compileall app`; FastAPI `TestClient` smoke | Passed | `/api/portfolio*` | None |

## Verification Commands

- `cd backend; python -m pytest`
- `cd backend; python -m compileall app`
- `cd frontend; npm run build`
- FastAPI `TestClient` smoke for portfolio routes

## Items Deferred By Design

- Broker sync, order execution, full ledger accounting, automatic shareholder/unlock feeds, margin/moneyflow/macros, PDF parsing, RAG, markdown export, external LLM sending, backtesting, scoring calibration, and broad UI redesign.

