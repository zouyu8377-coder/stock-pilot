# Research Workbench

## Daily entry points

- Update account: reuse the holding/trade screenshot import and explicit confirmation. A confirmed import returns to the cockpit; manual maintenance retains a return link.
- Update analysis: one tracked workflow collects missing research evidence, refreshes the account context, analyzes, publishes advice and evaluates historical actions. Identical account and evidence fingerprints on the same day reuse the last report without an additional review-model call. Data timestamps remain separate from analysis timestamps.
- Advanced tool execution, external-model exchange and historical review remain available but do not compete with the primary entry points.

## Consent and scheduling

`analysis_after_account_update` defaults to false. The cockpit checkbox explicitly authorizes sending account context to the configured model after a save/import confirmation. Saves coalesce into a local pending queue, including record-only trade imports. The existing background loop picks up the queue when idle. Automatic quota/backoff still apply; manual analysis remains quota-exempt. Disabling the setting prevents pending work from starting.

The former standalone disclosure-model loop is no longer started. Disclosure collection runs through tracked workflows and the existing morning cycle. This prevents a second invisible model process from bypassing task progress. The service must be running; this does not wake a powered-off computer.

## Research dossiers

`GET /api/agent/review/workbench` reads local holdings, disclosure findings and task records without fetching external sources. Research questions are shared with the disclosure verifier and grouped by business direction. A changed question signature invalidates the old verification cache.

The UI distinguishes not checked, index checked with no new materials, material obtained, question answered by verified text, and blocked sources. A source document is not an answer: verified, current findings must match the actual question. Source publication date, check time, quotation and document link remain visible. Older findings stay in the underlying disclosure archive. Financial/macro/ETF questions that available sources cannot answer remain explicit gaps; this release does not claim exhaustive web or commodity coverage.

## Decisions and safety

Holdings merge model risks, observations and opportunities by security code. User responses have stable security IDs and advice-version checks; materially changed text reopens a previously handled item. Rejections require a reason. Responses feed subsequent analysis as user feedback, not market facts or trades. Historical/stale-account advice cannot be confirmed as current. The generation path rejects publication if the account changed while the model was running.

The read-only trade simulator previews cash, total exposure and position weight at a user-entered price and quantity. No order, trade ledger write or position update occurs. Only the existing confirmed trade/screenshot paths update actual holdings. The simulator does not include actual trading fees.

Repeated unchanged transaction ledgers are not reviewed again during market-only analysis. The complete operation evidence remains in the local catalog.

## Verification

Focused regressions cover dossier provenance, unmatched/unverified quotes, per-security deduplication, decision history/version conflicts, unchanged analysis reuse, account mutation during generation, repeated operation suppression, and opt-in account-update queuing. UI checks use mocked responses and read-only simulation; no test trades or paid model calls are required.
