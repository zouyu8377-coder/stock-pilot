# Investment plan workflow

The cockpit now has account, direction and security discussion scopes. Plans are
versioned user-approved records, not orders. Holdings are never changed by these APIs.

1. Record constraints, original materials, observations or intent, preserving their types.
2. Export a research-planning or decision-discussion request. This refreshes the
   existing local evidence bundle without calling a model. The packet includes all
   level plans, non-archived memories, research needs and recent decision history.
3. Send the packet to an external model only deliberately: it includes private account data.
4. Paste or upload the structured response, preview changes, then explicitly confirm.
5. Supply missing material against research questions. Supplied does not mean verified.
6. Review plans when their date is due or the saved account changes. Lesson candidates
   require explicit user adoption; archive obsolete memories rather than rewriting history.

Requests expire after four hours and are invalidated by account or plan-memory changes.
Imports reject unknown evidence references and unexpected schema fields. Confirmation
requires the exact previewed response and is idempotent. Version/history/research/memory
updates are committed together in a single atomically replaced local state file under
`backend/data/agent_workbench/plans/`, excluded from Git.

## Deterministic monitoring

Approved structured conditions support daily close, price versus MA20, 5/20-day
returns, relative average volume, portfolio cash/position ratios and security weight.
Conditions use explicit AND/OR grouping. Stale or missing prices produce unknown,
not a negative investment judgment. Triggered conditions request discussion, never orders.

The local engine runs hourly on weekdays while the backend is alive, and picks up
plan/account changes on the scheduler tick. Manual runs expose item progress. A batch
handles up to five due research needs with retry backoff and collection cooldown.
Market questions can have deterministic answer conditions. Disclosures fetch up to
two index pages within 90 days and two PDF excerpts per symbol. External answers
must quote supplied text; quotation existence is validated before user confirmation.
No arbitrary URL fetching or user-supplied code execution is used for plan conditions.

The monitor records net position changes since plan confirmation and five-session
price/benchmark comparisons when available. These are not realized returns or causal
proof of success/failure. Lessons remain proposals until explicitly adopted.

External-only mode skips legacy scheduled model workflows and blocks review-model
requests. The main update-analysis action dispatches local monitoring in this mode.
Complex business logic, causal attribution and final plan revisions still require the
user/external model. Alerts are in-app, not push notifications. Natural-language
conditions without structured rules remain discussion topics, not executable monitors.

Validation: `pytest tests/test_investment_plans.py`; frontend build; mocked browser
workflow smoke test. No live holdings or model quota are needed for verification.
