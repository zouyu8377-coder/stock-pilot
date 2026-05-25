# Phase 3.6D-Closure Acceptance Checklist

| Item | Verification | Result | Blocks commit | Blocks dashboard | User follow-up |
|---|---|---|---|---|---|
| Mixed worktree was backed up before cleanup | Local backup at `C:\Project\Stock-Pilot_backup_before_dashboard_baseline_20260525_232459` | Passed | No | No | None |
| Uncommitted files were classified | File-level A/B/C/D table in closure report | Passed | No | No | None |
| Current product flow is manual portfolio maintenance | UI/code audit and browser smoke | Passed | No | No | None |
| Screenshot/OCR/cloud vision is not active user flow | UI/code audit; historical backend kept inactive | Passed | No | No | None |
| Portfolio area button says `生成组合证据包 / Generate Portfolio Packet` | Browser smoke | Passed | No | No | None |
| Single-stock button says `生成单票证据包 / Generate Stock Packet` | Browser smoke | Passed | No | No | None |
| Single-stock page is not account analysis | UI copy and packet audit | Passed | No | No | None |
| Manual flow exposes `primary_theme`, `theme_tags`, and `position_role` | UI/API smoke | Passed | No | No | User must confirm real holdings |
| System suggestions remain separate from user confirmation | API test and UI copy | Passed | No | No | User decides whether to apply suggestions |
| Semantic confirmations persist | Pytest/API smoke | Passed | No | No | User must save real confirmations |
| Zijin composite theme is non-additive | Synthetic pytest/API smoke | Passed | No | No | None |
| Portfolio Packet official exposure uses only confirmed `primary_theme` | Pytest/API smoke | Passed | No | No | None |
| `theme_tags` are related observations only | Pytest/API smoke | Passed | No | No | None |
| Unclassified holdings show semantic gap, not limit breach | Pytest/API smoke | Passed | No | No | User completes missing semantics |
| AccountAnalysisContext is local and no-AI | Pytest/API smoke | Passed | No | No | None |
| Inactive rules are excluded from current AI reasoning | Packet/context audit | Passed | No | No | None |
| No dashboard page was built | File/code audit | Passed | No | No | None |
| No external AI was called | Command and API smoke audit | Passed | No | No | None |
| No OCR/cloud vision development was included in baseline | Git diff audit | Passed | No | No | None |
| Sensitive/local data is ignored | `git check-ignore` and scan | Passed | No | No | None |
| Backend tests pass | `python -m pytest -q` | Passed, 54 tests | No | No | None |
| Backend compile passes | `python -m compileall app` | Passed | No | No | None |
| Frontend build passes | `npm run build` | Passed | No | No | None |
| API smoke passes | Local TestClient/script smoke | Passed | No | No | None |
| Browser smoke passes | Local frontend smoke | Passed | No | No | None |
| Baseline commit created | Git commit hash recorded in final closure response | Passed | No | No | None |

## Required User Actions Before Real Dashboard Use

- Confirm `primary_theme`, `theme_tags`, and `position_role` for the real current holdings in the page.
- Generate one new real local Portfolio Packet and check that the theme structure matches the user's own understanding.
- Do not commit that real Packet, real account data, screenshots, exports, tokens, or attachments.
