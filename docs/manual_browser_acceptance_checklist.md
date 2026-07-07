# Manual Browser Acceptance Checklist

Status before user action: `browser manual acceptance = pending_user_verification`

## Start Commands

Backend:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

Open: `http://localhost:5173`

Do not paste real tokens, full real account exports, or private attachments during this manual check.

## A. Page Open

- [ ] Frontend page is accessible.
- [ ] Portfolio entry is visible.
- [ ] Single-stock Packet entry is visible.
- [ ] Portfolio Packet entry is visible.

## B. Portfolio Display

- [ ] Cash is displayed separately.
- [ ] Reverse repo is displayed separately.
- [ ] Holdings list is visible.
- [ ] `primary_theme` unique attribution ratio looks correct.
- [ ] `theme_tags` are shown only as related risk observations.
- [ ] Composite exposure holding is not double-counted in formal theme weights.

## C. Packet Preview

- [ ] Single-stock Packet can be previewed.
- [ ] Portfolio Packet can be previewed.
- [ ] `market_price_as_of` does not fabricate quote time.
- [ ] Page clearly states portfolio snapshot time is not market quote time.
- [ ] Default risk parameters are marked as unconfirmed by user.
- [ ] Reverse repo is not automatically treated as cash.
- [ ] Privacy notice is visible.
- [ ] Content has no obvious mojibake.

## D. Manual Evidence

- [ ] Two include=true manual evidence records appear in Packet.
- [ ] One include=false manual evidence record does not appear in Packet.
- [ ] Manual evidence is categorized as `manual_evidence`.

## E. Markdown Copy

After clicking copy, paste into a plain text editor and check:

- [ ] Content is complete.
- [ ] No `[object Object]` appears.
- [ ] No obvious mojibake appears.
- [ ] No Token or secret appears.
- [ ] No unexpected local sensitive path appears.
- [ ] No automatic buy/sell conclusion appears.
- [ ] Privacy notice and data boundaries are included.

## F. Acceptance Result Notes

Passed items:

-

Failed items:

-

Blocking issues for real use:

-

Can defer to Phase 4:

-
