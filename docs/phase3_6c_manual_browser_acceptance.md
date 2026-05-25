# Phase 3.6C Manual Browser Acceptance

Use a脱敏 or synthetic screenshot only until you are comfortable with the privacy boundary.

## A. Configuration

- [ ] Put Fire/Ark vision values in local `backend/.env`.
- [ ] Keep `backend/.env` out of `git status`.
- [ ] Set `VOLCENGINE_ARK_VISION_ENABLED=true`.
- [ ] Set `VOLCENGINE_ARK_VISION_BASE_URL`, `VOLCENGINE_ARK_VISION_API_KEY`, and `VOLCENGINE_ARK_VISION_MODEL`.
- [ ] Start backend and frontend.
- [ ] Confirm the page shows the cloud parser provider status without displaying the API key.

## B. Cloud Send Authorization

- [ ] Open the portfolio screenshot import area.
- [ ] Select `火山方舟云端视觉解析`.
- [ ] Confirm the privacy notice appears.
- [ ] Confirm the parse/upload button is disabled before consent.
- [ ] Check: `我理解该截图将发送至我配置的火山方舟视觉模型，并同意继续解析。`
- [ ] Confirm parsing only starts after consent.

## C. Sanitized Screenshot Parsing

- [ ] Upload `docs/acceptance_samples/phase3_6b/sanitized_broker_holdings_sample.png` or another synthetic image.
- [ ] Confirm a待确认草稿 is returned.
- [ ] Check warnings for uncertain fields.
- [ ] Verify code/name normalization locally, for example `601899.SH` and `002463.SZ`.
- [ ] Verify `quantity`, `available_quantity`, `avg_cost`, screenshot price, market value, and PnL are editable.
- [ ] Confirm model output is not described as guaranteed correct.

## D. Confirmation

- [ ] Before confirmation, current portfolio snapshot is unchanged.
- [ ] Correct any rows with warnings.
- [ ] Set `primary_theme`, `position_role`, `user_plan`, and `invalid_condition` as needed.
- [ ] Confirm save.
- [ ] Verify a new snapshot is created.
- [ ] Verify screenshot evidence defaults to excluded from Analysis Packet.

## E. Packet

- [ ] Generate portfolio Analysis Packet.
- [ ] Generate single-stock Packet for a confirmed holding.
- [ ] Confirm `manual_account.has_holding = true`.
- [ ] Confirm quantity, available quantity, and cost come from the user-confirmed draft.
- [ ] Confirm screenshot price and system quote price are separate.
- [ ] Confirm external drivers are visible where mapped.
- [ ] Confirm shared drivers are not double-counted.
- [ ] Confirm `data_coverage` does not present rule-inferred company business as hard fact.
- [ ] Confirm daily-K interval returns are marked as derived observations.
- [ ] Confirm no buy/sell conclusion is generated.
- [ ] Confirm no investment-analysis LLM is called automatically.

## F. Security

- [ ] Real screenshot directory is not in Git.
- [ ] Token does not appear in Git, logs, UI, exports, or reports.
- [ ] Packet does not include the raw screenshot or full cloud response by default.
- [ ] Full historical account data, existing Packets, and investment questions were not sent with the screenshot.

Do not mark real cloud acceptance complete until you have performed this workflow yourself with your own configured model.
