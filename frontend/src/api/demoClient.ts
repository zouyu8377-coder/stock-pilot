export interface DemoEvidence {
  id: string; tool: string; retrieved_at: string
  data: { kind: string; source: string; synthetic: boolean; stale: boolean; observed_at: string; note: string; rows?: Array<{ symbol: string; price: number; account_weight_pct: number | null }>; [key: string]: unknown }
}
export interface DemoRun {
  run_id: string; revision: number; scenario: string; mode: string; phase: string; public_market: boolean
  created_at: string; updated_at: string; error: string | null
  context: { version: number; fingerprint: string; payload: { account: { name: string; cash: number; positions: Array<{ symbol: string; name: string; quantity: number }> }; evidence: DemoEvidence[] } }
  events: Array<{ id: string; sequence: number; sender: string; receiver: string; kind: string; title: string; detail: string; at: string; context_version: number }>
  versions: Array<{ version: number; fingerprint: string; at: string }>
  analyst_turns: number; tool_calls: number; repairs: number; model_calls: number; tokens: number
  limits: { analyst_turns: number; tool_calls: number; repairs: number; attempts: number }
  preview_digest: string | null
  pending_report: null | { provider: string; report: { summary: string; findings: Array<{ title: string; conclusion: string; reasoning: string; confidence: string; evidence_refs: string[] }>; unresolved: string[] } }
  confirmed_report: unknown
}
export interface DemoScenario { id: string; name: string; description: string }

const devPort = /^517\d$/.test(window.location.port)
export const DEMO_API = (import.meta.env.VITE_DEMO_API_BASE_URL || (devPort ? `${window.location.protocol}//${window.location.hostname}:8010` : window.location.origin)).replace(/\/$/, '')

export async function demoRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${DEMO_API}/api/demo/collaboration${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `请求失败（${response.status}）`)
  return value.data as T
}
