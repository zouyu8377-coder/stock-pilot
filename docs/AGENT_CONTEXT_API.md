# Agent Context API

Stock-Pilot exposes local, read-only review contexts for Codex or another
user-invoked analysis tool. These endpoints assemble local data and derived
signals; they do not call an external LLM.

Default backend URL: `http://127.0.0.1:8001`

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/agent/context/daily-review` | Combined daily portfolio and rotation review |
| `GET /api/agent/context/portfolio` | Portfolio facts, evidence, risks and opportunities |
| `GET /api/agent/context/rotation` | Sector proxy evidence and opportunity-stage assessments |
| `GET /api/agent/context/stock/{symbol}` | Single-stock facts, signals and research gaps |
| Add `/markdown` to any endpoint above | Human- and agent-readable Markdown export |

Examples:

```text
GET /api/agent/context/daily-review/markdown
GET /api/agent/context/stock/000001/markdown
```

The portfolio, rotation and daily-review JSON endpoints accept `force=true`.
Use it only when a fresh local recomputation is needed. The stock endpoints
accept an optional `user_question` query parameter.

## Contract

All JSON contexts use `agent_context.v1`:

```json
{
  "meta": {
    "contract_version": "agent_context.v1",
    "context_type": "daily_review",
    "generated_at": "...",
    "data_time": {},
    "sources": [],
    "freshness": {},
    "privacy_boundary": {
      "processing": "local_only",
      "external_llm_called": false,
      "contains_sensitive_account_data": true,
      "export_rule": "..."
    }
  },
  "facts": {},
  "inferences": {},
  "missing_data": [],
  "suggested_questions_for_llm": []
}
```

- `facts` contains source observations and locally recorded account facts.
- `inferences` contains Stock-Pilot scores, stages, queues and other derived judgments.
- `missing_data` must be reviewed before relying on an inference.
- `freshness` reports source status without silently treating stale data as current.

## Privacy Boundary

Portfolio and daily-review contexts can contain real holdings, costs and account
structure. They remain local unless the user explicitly copies or exports them.
Calling these endpoints never sends data to Volcengine, OpenAI or another model
provider.
