# Phase 3 Release Readiness Checklist

| Acceptance item | Verification method | Current result | Related file/API/page | Blocks real-account use |
| --- | --- | --- | --- | --- |
| Full single-stock Packet sections exist | Backend tests and sample JSON | Passed | `backend/app/analysis_packet/packet_service.py`, `docs/acceptance_samples/phase3_single_holding_packet.json` | No |
| Full portfolio Packet sections exist | Backend tests and sample JSON | Passed | `docs/acceptance_samples/phase3_portfolio_packet.json` | No |
| ETF facts enter Packet or show unavailable | ETF sample generation | Passed | `phase3_single_etf_packet.json` | No, if user accepts unavailable boundary |
| Dragon-tiger boundary visible | Holding sample and global boundaries | Passed | `phase3_single_holding_packet.md` | No |
| Announcement/survey index boundary visible | Holding sample and missing data | Passed | `phase3_single_holding_packet.md` | No |
| Evidence fields include source/time/reliability/boundary | Markdown renderer and samples | Passed | `packet_service.py` | No |
| Manual evidence include=true exports | Demo sample and tests | Passed | `test_phase3_analysis_packet.py` | No |
| Manual evidence include=false excluded | Demo sample and tests | Passed | `test_phase3_analysis_packet.py` | No |
| Manual evidence not mixed into auto_fact | Backend tests | Passed | `test_phase3_analysis_packet.py` | No |
| Primary theme unique attribution not double counted | Demo 50% invested sample | Passed | `phase3_portfolio_packet.json` | No |
| Theme tags are non-additive observations | Sample boundary text | Passed | `related_risk_observations` | No |
| Default risk parameters are unconfirmed | Tests and samples | Passed | `system_hypothesis` | No, but user should confirm before relying |
| Snapshot time not used as quote time | Tests and samples | Passed | `market_price_as_of = null` | No |
| Missing quote time boundary visible | Sample Markdown | Passed | `phase3_portfolio_packet.md` | No |
| Privacy notice visible in Markdown | Tests and samples | Passed | Packet Markdown | No |
| Packet generation does not call external LLM | Code inspection | Passed | `packet_service.py`, `api/analysis_packet.py` | No |
| No automatic attachment upload | Code inspection | Passed | Manual evidence payload only references paths | No |
| No obvious mojibake in acceptance samples | `rg` over `docs/acceptance_samples` | Passed | Acceptance samples | No |
| Backend tests pass | `python -m pytest` | Passed, 28 tests | `backend/tests/*` | No |
| Backend compile passes | `python -m compileall app` | Passed | `backend/app` | No |
| Frontend build passes | `npm run build` | Passed | `frontend` | No |
| UI render/copy check | In-app browser attempted | Partially passed: build passed; browser blocked localhost | `AnalysisPacketPanel.vue`, `PortfolioPanel.vue` | No for backend trial; manually verify UI |
| Tushare real facts available | Runtime token/config | Partial: unavailable in current run | Stage 1 fact services | No, but facts will be incomplete |
| Real risk limits confirmed by user | Manual confirmation | Not passed | Portfolio settings | Yes for full real-account use |
| Repo cash-equivalent policy confirmed | Manual confirmation | Not passed | `account_overview.repo_policy` | Yes for full real-account use |

Recommendation: start with脱敏 test data. Move to a small real manually entered portfolio only after reviewing exported Packet content, confirming risk limits, and deciding how repo should be treated.
