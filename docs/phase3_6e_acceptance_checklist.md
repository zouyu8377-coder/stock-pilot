# Phase 3.6E Acceptance Checklist

| Item | Verification | Synthetic Result | Blocks Dashboard | User Action Needed |
| --- | --- | --- | --- | --- |
| Snapshot valuation and current quote estimate are separate | Pytest synthetic portfolio | Passed in targeted run | No | Check real page wording |
| Current estimated total assets equals enriched market value plus carried cash/repo | Pytest synthetic portfolio | Passed in targeted run | No | Check real Portfolio Packet export |
| Current position/cash/repo weights sum to approximately 100% | Pytest synthetic portfolio | Passed in targeted run | No | Check real Portfolio Packet export |
| Official theme exposure uses current estimated denominator | Pytest synthetic portfolio | Passed in targeted run | No | None |
| Official `AI_PCB` contains only PCB holdings | Pytest synthetic tags | Passed in targeted run | No | None |
| Related tag `AI_PCB` excludes AI ETF unless user confirms that tag | Pytest synthetic tags | Passed in targeted run | No | None |
| `AI_THEME_ETF` related observation remains separate | Pytest synthetic tags | Passed in targeted run | No | None |
| `HIGH_VOLATILITY` remains descriptive and threshold-free | Pytest packet boundary | Passed in targeted run | No | None |
| `AI_RELATED` is not auto-generated or auto-saved | Pytest synthetic tags | Passed in targeted run | No | Optional future confirmation only |
| User-confirmed `observation` is not Missing Data | Pytest synthetic roles | Passed in targeted run | No | None |
| Unconfirmed observation/unclassified role still surfaces as a gap | Pytest synthetic roles | Passed in targeted run | No | Confirm role when desired |
| Portfolio default AI questions are descriptive | Pytest AI boundary | Passed in targeted run | No | None |
| Inactive decision rules are explicit | Pytest AI boundary | Passed in targeted run | No | None |
| AccountAnalysisContext external driver summary is compact | Pytest synthetic driver | Passed in targeted run | No | None |
| Existing external driver shared-driver de-dup remains available in detailed packet | Regression pytest | Passed | No | None |
| Quote time, company profile, data coverage boundaries do not regress | Regression pytest | Passed | No | None |
| Manual holdings maintenance still works | Regression pytest and browser smoke | Passed | No | Real page smoke |
| No dashboard, AI call, OCR, cloud vision, screenshot flow added | Code review / rg | Passed | No | None |
| No real account packet/data/token/screenshot committed | Git and privacy scan | Passed | No | None |

## User Real-Page Checks

- Confirm the account summary wording separates saved snapshot values from current quote estimates.
- Regenerate the real Portfolio Packet locally and check that current weights are self-consistent.
- Confirm `AI_PCB` related observation no longer includes the AI ETF.
- Confirm confirmed `observation` roles are not listed as Missing Data.
