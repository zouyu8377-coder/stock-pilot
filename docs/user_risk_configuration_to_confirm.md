# User Risk Configuration To Confirm

Do not treat these as decided settings. The user must confirm the final risk and liquidity convention before using real account data.

## 1. Single Position Limit

Questions to confirm:

- Should there be one unified max weight for every single position?
- Should limits differ by `position_role`, such as `core`, `trend`, `short_term`, or `observation`?
- Should an over-limit result be a reminder only?
- In the future, should over-limit status become a stronger simulated-trade warning?
- Should ETFs and individual stocks use different limits?

## 2. Single Theme Limit

Questions to confirm:

- Should `AI_PCB`, `METAL_RESOURCE`, `GOLD`, `AI_THEME_ETF`, and other themes have separate upper limits?
- Should formal theme exposure continue to use only one `primary_theme` per holding?
- Should `theme_tags` remain related-risk observations only and not be added into formal exposure totals?
- How should `COMPOSITE_EXPOSURE` be displayed when a position belongs to one formal primary theme but has multiple related risks?

Recommended default convention before confirmation:

- `primary_theme` is the only formal attribution bucket.
- `theme_tags` are non-additive risk observations.
- No theme-limit value should be treated as user-confirmed yet.

## 3. Cash Floor

Questions to confirm:

- What is the minimum cash-available ratio in normal market conditions?
- Should the cash floor increase during high volatility or after portfolio drawdown?
- Should cash-floor warnings apply only to simulated buys?
- Should cash-floor warnings ever produce a sell suggestion automatically?

Recommended boundary before confirmation:

- Cash-floor warnings should remain reminders only.
- The system should not automatically conclude that a position must be sold.

## 4. Reverse Repo Treatment

Questions to confirm:

- Should `repo_amount` be included in total assets?
- Should reverse repo continue to be displayed separately from `cash_available`?
- Should there be a liquidity observation convention such as `cash_available + repo that matures soon`?
- Before maturity, should reverse repo be forbidden from being treated as immediately available buy cash?
- Does the user want maturity date, expected available date, or product tenor displayed in the portfolio view?

Recommended boundary before confirmation:

- Reverse repo can be observed as short-term low-risk liquidity reserve.
- Before maturity, reverse repo should not be fully equivalent to immediately tradable cash.
- Final convention must be confirmed by the user.

## 5. Conditions Before Real Account Trial

Minimum confirmations before a small real manually entered portfolio trial:

- Single-position limit convention confirmed.
- Theme-limit convention confirmed.
- Cash-floor convention confirmed.
- Reverse repo cash-equivalent convention confirmed.
- User understands Packet is generated locally and only leaves the machine if copied/exported/submitted manually.
- User agrees to start with a small subset of holdings rather than the full account.
- User accepts that unavailable Tushare facts remain visible as missing/unavailable boundaries.

## 6. Not Confirmed Yet

Current state:

- `risk_parameter_source = system_default_placeholder`
- `unconfirmed_by_user = true`
- `repo_policy.cash_equivalent_treatment = unconfirmed`
