# Phase 3.6B Manual Browser Acceptance

Use backend `http://127.0.0.1:8001` and frontend `http://127.0.0.1:5173`.

## A. Sanitized Screenshot Import

1. Open the app and expand "组合与本地账户快照".
2. Upload `docs/acceptance_samples/phase3_6b/sanitized_broker_holdings_sample.png` or another fully sanitized PNG/JPEG/WebP sample.
3. Confirm the page shows an OCR/import draft and does not immediately change the formal portfolio.
4. If local OCR is unavailable, confirm the page shows a manual-entry-required warning instead of pretending recognition succeeded.
5. Add or edit rows for:
   - 紫金矿业 / 601899
   - 深南电路 or 沪电股份
   - 中钨高新
   - ETF such as 159934 or 159382
6. Verify code/name matching and external driver profile context.

## B. Human Confirmation

1. Before confirmation, check the current portfolio summary has not changed.
2. Review and correct:
   - 标准代码
   - 标准名称
   - 持仓数量
   - 可用数量
   - 平均成本
   - 截图现价
   - 截图市值
   - 浮盈亏
   - primary_theme
   - theme_tags
   - position_role
3. Click "确认并保存为新的持仓快照".
4. Confirm the new snapshot is shown in the portfolio area.
5. Confirm older snapshot files are still present under the ignored local data directory.

## C. Portfolio Packet

1. Click "Generate Portfolio Packet".
2. Check the packet contains holdings, cash/repo, theme exposure, risk tag exposure, and external driver summary.
3. Check screenshot price fields are separate from system quote fields.
4. Check no buy/sell recommendation is generated.
5. Check screenshot evidence is not automatically included in manual evidence.

## D. Privacy

1. Confirm `backend/data/uploads/portfolio_screenshots/` is ignored.
2. Confirm `backend/data/portfolio/imports/` and `backend/data/portfolio/snapshots/` are ignored.
3. Confirm generated packets do not contain local screenshot binary data.
4. Confirm no external LLM request is made during upload, draft parse, edit, or confirm.

Do not mark browser acceptance complete until the user personally performs these steps.
