<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Play, CircleStop, Trash2, RefreshCw, Check, ClipboardList, ExternalLink, Undo2 } from 'lucide-vue-next'
import { API_BASE_URL, investmentAgentRequest } from '../api/client'
import { refreshAssistantStatus } from '../composables/useAssistantStatus'

const emit = defineEmits(['updated'])
const data = ref<any>(null)
const question = ref('审视当前账户的实质风险、持仓与观察标的机会，结合技术面、财报与外部环境给出下一步计划。')
const provider = ref('codex')
const refreshSources = ref(true)
const consent = ref(false)
const calls = ref(3)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const selectedEvidence = ref<any>(null)
const localPdf = computed(() => {
  const file = selectedEvidence.value?.local_pdf
  const matched = typeof file === 'string' && file.match(/^(\d{6})-(\d+)\.pdf$/)
  return matched ? `${API_BASE_URL}/api/investment-agents/documents/${matched[1]}/${matched[2]}` : null
})
const history = ref<any[]>([])
const settingsDraft = ref<any>(null)
const settingsDirty = ref(false)
const symbolsExpanded = ref(false)
const discussionLevel = ref('account')
const discussionTabs = [{ key: 'account', label: '账户建议', hint: '整体风险与资金安排' }, { key: 'direction', label: '行业方向', hint: '主线判断与潜在机会' }, { key: 'symbol', label: '标的计划', hint: '持仓立场与行动条件' }]
const clock = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
let fetching = false
let disposed = false
const run = computed(() => data.value?.run)
const active = computed(() => !!run.value && !['awaiting_confirmation', 'confirmed', 'failed', 'cancelled', 'stale'].includes(run.value.status))
const display = computed(() => run.value?.report ? { ...run.value, report: run.value.report } : data.value?.confirmed?.[0])
const report = computed(() => display.value?.report)
const stale = computed(() => !!display.value && display.value.account_fingerprint !== data.value?.account_fingerprint)
const roleData = computed(() => run.value?.data_summary)
const elapsed = computed(() => run.value ? Math.max(0, Math.round(((active.value ? clock.value : Date.parse(run.value.updated_at)) - Date.parse(run.value.created_at)) / 1000)) : 0)
const heartbeatAge = computed(() => run.value?.heartbeat_at ? Math.max(0, Math.round((clock.value - Date.parse(run.value.heartbeat_at)) / 1000)) : null)
const phase: Record<string, string> = { queued: '排队中', collecting: '正在整理分析资料', analyzing: '正在形成投资判断', supplementing: '正在补充证据', awaiting_confirmation: '分析完成 · 待确认', confirmed: '已记录', failed: '未完成', cancelled: '已停止' }
const actions: Record<string, string> = { hold: '维持持仓', increase: '考虑增持', reduce: '考虑减持', avoid: '暂不参与', watch: '持续观察', wait: '等待条件' }
const states: Record<string, string> = { stable: '暂未发现明显实质风险', attention: '存在需要调整或跟踪的问题', high_risk: '存在显著风险', insufficient_data: '资料不足，判断受限' }
const confidence: Record<string, string> = { high: '高', medium: '中', low: '低', unknown: '未确定' }
const roleNames: Record<string, string> = { agent1: '资料采集', agent2: '投资分析', coordinator: '任务管理' }
const userText = (value?: string) => (value || '').replace(/Agent\s*1/gi, '资料采集').replace(/Agent\s*2/gi, '投资分析')
const sourceNames: Record<string, string> = { cold: '日K与交易日历', market: '行情与技术指标', references: '重要参考指数', disclosures: '年报、季报与公告', rotation: '行业代理走势', breadth: '广义市场广度', public: '官方宏观与商品参考', backfill: '全市场日K后台续传' }
const at = (v?: string) => v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '--'
const fmt = (v: number | null | undefined) => v == null ? '--' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const targetName = (target: string) => {
  const position = roleData.value?.positions.find((p: any) => p.symbol.split('.')[0] === target)
  return position ? `${position.name} ${target}` : target
}
const visibleFindings = (level: string) => {
  const items = report.value?.findings.filter((item: any) => item.level === level) || []
  return level === 'symbol' && !symbolsExpanded.value ? items.slice(0, 3) : items
}
function moveDiscussion(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const index = discussionTabs.findIndex(tab => tab.key === discussionLevel.value)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? discussionTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + discussionTabs.length) % discussionTabs.length
  discussionLevel.value = discussionTabs[next]!.key
  nextTick(() => document.getElementById(`discussion-tab-${discussionLevel.value}`)?.focus())
}

async function poll() {
  if (fetching || disposed) return
  fetching = true
  try { data.value = await investmentAgentRequest(); if (!settingsDirty.value) settingsDraft.value = { ...data.value.settings } }
  catch (e: any) { error.value = e.response?.data?.detail || e.message }
  finally { fetching = false }
}
async function act(task: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await task(); await poll(); await refreshAssistantStatus() }
  catch (e: any) { error.value = e.response?.data?.detail || e.message || '操作未完成' }
  finally { busy.value = false }
}
function start() {
  return act(async () => { await investmentAgentRequest('/runs', { question: question.value, provider: provider.value, refresh: refreshSources.value, consent: consent.value, max_model_calls: calls.value }) })
}
function stop() { return act(async () => { await investmentAgentRequest(`/runs/${run.value.run_id}/cancel`, {}); notice.value = '已停止；已完成的资料仍保留' }) }
function confirm() { return act(async () => { await investmentAgentRequest(`/runs/${run.value.run_id}/confirm`, { digest: run.value.report_digest }); emit('updated') }) }
function saveSettings() { return act(async () => { await investmentAgentRequest('/settings', settingsDraft.value, 'PUT'); settingsDirty.value = false; notice.value = '运行设置已保存' }) }
function evidence(refId: string) {
  return act(async () => {
    const external = report.value?.external_sources?.find((s: any) => s.id === refId)
    selectedEvidence.value = external || await investmentAgentRequest(`/runs/${display.value.run_id}/evidence/${encodeURIComponent(refId)}`)
  })
}
async function accountFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await act(async () => {
    if (file.size > 1_000_000) throw new Error('账户 JSON 超过1MB')
    const value = JSON.parse(await file.text())
    const current = await investmentAgentRequest()
    const result = await investmentAgentRequest('/account-import', { ...value, expected_fingerprint: current.account_fingerprint })
    notice.value = `账户已校验入账，记录 ${result.id}；未新增任何交易成交记录`
    emit('updated')
  })
  input.value = ''
}
function undo(id: string) { return act(async () => { await investmentAgentRequest(`/account-import/${id}/undo`, {}); notice.value = '已撤销账户入账；保留审计记录'; emit('updated') }) }
function loadHistory() { return act(async () => { history.value = await investmentAgentRequest('/history') }) }
onMounted(() => { poll(); timer = setInterval(() => { clock.value = Date.now(); if (!document.hidden && !busy.value) poll() }, 2500) })
onUnmounted(() => { disposed = true; if (timer) clearInterval(timer) })
</script>

<template>
  <section class="investment-workspace space-y-5">
    <form class="flex flex-wrap items-end gap-3 border-b border-border pb-4" @submit.prevent="start">
      <label class="min-w-0 grow basis-full space-y-2 text-sm lg:basis-1/2">本次投资议题<textarea v-model="question" aria-label="投资分析议题" maxlength="4000" class="block min-h-20 w-full rounded border border-border bg-background p-3" /></label>
      <label class="space-y-2 text-xs">分析模型<select v-model="provider" aria-label="分析模型" class="block rounded border border-border bg-background px-3 py-2 text-sm"><option value="codex">本机 Codex</option><option value="api" :disabled="!data?.providers?.api?.enabled || !data?.providers?.api?.configured">模型 API{{ data?.providers?.api?.enabled ? '' : '（未启用）' }}</option></select></label>
      <label class="space-y-2 text-xs">本次最多调用<input v-model.number="calls" aria-label="本次最多模型调用次数" type="number" min="1" max="4" class="block w-24 rounded border border-border bg-background px-3 py-2 text-sm" /></label>
      <button type="submit" class="bg-primary text-primary-foreground" :disabled="busy || active || run?.status === 'awaiting_confirmation' || !consent"><Play :size="16" />更新资料并分析</button>
      <button type="button" title="读取任务状态" aria-label="读取任务状态" :disabled="busy" @click="poll"><RefreshCw :size="16" /></button>
      <label class="flex items-center gap-2 text-xs"><input v-model="refreshSources" type="checkbox" />检查并更新来源</label>
      <label class="flex basis-full items-start gap-2 text-xs text-muted-foreground"><input v-model="consent" type="checkbox" />允许向所选模型发送本次账户、证据与历史结论，使用相应模型额度；不会执行交易。</label>
    </form>
    <p v-if="error" role="alert" class="text-sm text-amber-300">{{ error }}</p>
    <p v-if="notice" role="status" class="text-sm text-sky-300">{{ notice }}</p>

    <section v-if="run" class="space-y-3 border-b border-border pb-4" aria-live="polite">
      <div class="flex flex-wrap items-center justify-between gap-3"><div><strong class="text-sm">{{ phase[run.status] || run.status }}</strong><span class="ml-3 text-xs text-muted-foreground">{{ elapsed }}秒 · 模型 {{ run.model_calls }}/{{ run.max_model_calls }} · 补证 {{ run.tool_requests }}/{{ run.max_tool_requests }}</span></div><button v-if="active || run.status === 'awaiting_confirmation'" type="button" class="discard-button" :disabled="busy" @click="stop"><CircleStop v-if="active" :size="16" /><Trash2 v-else :size="16" />{{ active ? '停止任务' : '放弃本次结果' }}</button></div>
      <p class="text-xs text-sky-300">{{ userText(run.activity) }} · {{ at(run.updated_at) }}</p>
      <p v-if="active && heartbeatAge !== null" :class="['text-xs', heartbeatAge > 30 ? 'text-amber-300' : 'text-muted-foreground']">心跳 {{ heartbeatAge }}秒前<span v-if="run.status === 'analyzing'"> · 单轮模型最长300秒</span><span v-if="run.source_progress?.stage"> · 来源 {{ sourceNames[run.source_progress.stage] || run.source_progress.stage }}，已返回 {{ run.source_progress.items || 0 }}项 / {{ run.source_progress.documents || 0 }}份文档，失败 {{ run.source_progress.failures || 0 }}项</span></p>
      <p v-if="run.tokens?.input_tokens || run.tokens?.prompt_tokens" class="text-xs text-muted-foreground">累计模型输入 {{ fmt(run.tokens.input_tokens ?? run.tokens.prompt_tokens) }} Token · 输出 {{ fmt(run.tokens.output_tokens ?? run.tokens.completion_tokens) }} Token</p>
      <p v-if="run.error" class="text-sm text-amber-300">{{ run.error }}</p>
      <details><summary>执行记录 · {{ run.events.length }}条</summary><ol class="mt-3 space-y-2"><li v-for="item in [...run.events].reverse()" :key="item.id" class="border-l-2 border-border pl-3 text-xs"><span class="text-muted-foreground">{{ at(item.at) }} · {{ roleNames[item.actor] || item.actor }}</span><p>{{ userText(item.title) }}</p><p class="text-muted-foreground">{{ userText(item.detail) }}</p></li></ol></details>
    </section>

    <section class="analysis-results">
      <header class="flex flex-wrap items-center justify-between gap-2"><h2 class="flex items-center gap-2 text-base font-semibold"><ClipboardList :size="18" />投资判断与行动计划</h2><span v-if="display" class="text-xs text-muted-foreground">{{ display.provider }} · {{ at(display.confirmed_at || display.updated_at) }}</span></header>
      <p v-if="!report" class="py-6 text-sm text-muted-foreground">尚无分析结果。选择本次议题后可更新资料并开始分析。</p>
      <template v-else>
        <p v-if="stale" role="status" class="stale-notice">这是账户变更前的判断，请更新分析后再用于当前决策。</p>
        <div class="account-conclusion"><span class="section-caption">账户结论</span><h3>{{ states[report.account_state] }}</h3><p>{{ report.summary }}</p></div>
        <div role="tablist" aria-label="投资讨论层级" class="discussion-tabs" @keydown="moveDiscussion">
          <button v-for="tab in discussionTabs" :id="`discussion-tab-${tab.key}`" :key="tab.key" role="tab" type="button" :tabindex="discussionLevel === tab.key ? 0 : -1" :aria-selected="discussionLevel === tab.key" :aria-controls="`discussion-panel-${tab.key}`" @click="discussionLevel = tab.key"><span>{{ tab.label }}</span><span class="tab-count">{{ report.findings.filter((f: any) => f.level === tab.key).length }}</span></button>
        </div>
        <section v-for="tab in discussionTabs" v-show="discussionLevel === tab.key" :id="`discussion-panel-${tab.key}`" :key="tab.key" role="tabpanel" :aria-labelledby="`discussion-tab-${tab.key}`" class="discussion-panel">
          <header class="discussion-heading"><h3>{{ tab.label }}</h3><p>{{ tab.hint }}</p></header>
          <p v-if="!visibleFindings(tab.key).length" class="py-6 text-sm text-muted-foreground">本轮未形成这一层级的计划。</p>
          <article v-for="(item, index) in visibleFindings(tab.key)" :key="index" class="finding-row">
            <div class="finding-meta"><span class="finding-number">{{ String(Number(index) + 1).padStart(2, '0') }}</span><h4>{{ targetName(item.target) }}</h4><span :class="['action-label', `action-${item.action}`]">{{ actions[item.action] }}</span><p>信心 {{ confidence[item.confidence] }}<br />{{ item.horizon }}</p></div>
            <div class="finding-content"><p class="finding-conclusion">{{ item.conclusion }}</p><dl class="finding-condition"><dt>执行 / 观察条件</dt><dd>{{ item.trigger }}</dd></dl>
              <details class="finding-reasoning"><summary>判断依据、信心与反证</summary><div class="reasoning-body"><dl><div><dt>判断依据</dt><dd>{{ item.reasoning }}</dd></div><div><dt>信心依据</dt><dd>{{ item.confidence_reason }}</dd></div><div><dt>改变判断的条件</dt><dd>{{ item.invalidation }}</dd></div></dl><div class="evidence-links"><span>引用证据</span><button v-for="refId in item.evidence_refs" :key="refId" type="button" @click="evidence(refId)">{{ refId }}</button></div></div></details>
            </div>
          </article>
          <button v-if="tab.key === 'symbol' && report.findings.filter((f: any) => f.level === 'symbol').length > 3" class="mt-4" @click="symbolsExpanded = !symbolsExpanded">{{ symbolsExpanded ? '收起其他标的' : `展开其余 ${report.findings.filter((f: any) => f.level === 'symbol').length - 3} 个标的计划` }}</button>
        </section>
        <div class="analysis-appendix"><details v-if="report.unresolved.length"><summary>判断限制与未解决事项 · {{ report.unresolved.length }}</summary><ul class="mt-3 list-disc space-y-2 pl-5 text-xs text-amber-200"><li v-for="item in report.unresolved" :key="item">{{ item }}</li></ul></details><details v-if="report.lessons.length"><summary>本轮教训与后续复核</summary><ul class="mt-3 list-disc space-y-2 pl-5 text-xs"><li v-for="item in report.lessons" :key="item">{{ item }}</li></ul></details><details v-if="report.external_sources.length"><summary>外部消息来源 · 模型引用，未经本地逐条核验</summary><article v-for="source in report.external_sources" :key="source.id" class="py-2 text-xs"><a :href="source.url" target="_blank" rel="noopener noreferrer" class="text-sky-300">{{ source.title }} <ExternalLink :size="12" class="inline" /></a><p>{{ source.published_at }} · {{ source.excerpt }}</p></article></details></div>
        <footer v-if="run?.status === 'awaiting_confirmation'" class="confirmation-bar"><p>确认后保存本轮判断与计划，不修改持仓、不执行交易。</p><button class="bg-primary text-primary-foreground" :disabled="busy || stale" @click="confirm"><Check :size="16" />确认记录判断与计划</button></footer>
      </template>
    </section>

    <section v-if="selectedEvidence" class="space-y-3 border-y border-border py-4"><div class="flex items-center justify-between gap-3"><h3 class="text-sm font-semibold">原始证据 · {{ selectedEvidence.title || selectedEvidence.id }}</h3><button @click="selectedEvidence = null">收起</button></div><a v-if="localPdf" :href="localPdf" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 text-sm text-sky-300"><ExternalLink :size="14" />查看已存储公告全文 PDF</a><pre class="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-background p-3 text-xs">{{ JSON.stringify(selectedEvidence, null, 2) }}</pre></section>

    <details class="border-t border-border pt-4">
      <summary>运行设置与账户入账审计</summary>
      <div v-if="settingsDraft" class="mt-4 space-y-4 text-xs" @input="settingsDirty = true" @change="settingsDirty = true">
        <label class="flex items-center gap-2"><input v-model="settingsDraft.web_search" type="checkbox" />允许 Codex 公开网页检索</label>
        <label class="flex items-center gap-2">Codex 模型<input v-model="settingsDraft.codex_model" placeholder="留空使用默认" class="rounded border border-border bg-background p-2" /></label>
        <label class="flex items-center gap-2"><input v-model="settingsDraft.api_enabled" type="checkbox" />启用已配置的模型 API（当前配置不代表权限仍有效）</label>
        <label class="flex items-start gap-2"><input v-model="settingsDraft.auto_apply_verified_holdings" type="checkbox" />完整账户资料通过交叉校验后自动记账；可撤销，不执行交易，不把快照差额记成成交。</label>
        <button :disabled="busy || active" @click="saveSettings">保存运行设置</button>
        <label class="block space-y-2">导入完整账户 JSON<input type="file" accept="application/json,.json" :disabled="busy || active" class="block max-w-full" @change="accountFile" /></label>
        <p class="text-muted-foreground">只接收24小时内、带时区的完整快照；逐行市值与账户总额不符时拒绝自动更新。截图仍可从“更新持仓”入口形成草稿，不能把不完整识别结果直接入账。</p>
        <article v-for="entry in data.account_updates" :key="entry.id" class="flex flex-wrap items-center justify-between gap-2 border-b border-border py-2"><p>{{ at(entry.at) }} · {{ entry.source_id }} · {{ entry.status }}</p><button v-if="entry.status === 'applied' || entry.status === 'prepared'" :disabled="busy || active" @click="undo(entry.id)"><Undo2 :size="14" />撤销入账</button></article>
      </div>
    </details>
    <details class="border-t border-border pt-4" @toggle="(e: Event) => (e.target as HTMLDetailsElement).open && loadHistory()"><summary>已确认分析历史</summary><article v-for="entry in history" :key="entry.run_id" class="space-y-2 border-b border-border py-3 text-sm"><p class="text-xs text-muted-foreground">{{ at(entry.confirmed_at) }} · {{ entry.provider }}</p><p>{{ entry.report.summary }}</p><ul class="list-disc pl-5 text-xs"><li v-for="lesson in entry.report.lessons" :key="lesson">{{ lesson }}</li></ul></article></details>
  </section>
</template>

<style scoped>
.investment-workspace { min-width: 0; overflow-wrap: anywhere; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid var(--border); border-radius: 4px; padding: 8px 12px; font-size: 12px; min-height: 36px; transition: background-color .15s, border-color .15s; }
button:hover:not(:disabled) { background-color: #263d5c; border-color: #65809f; }
button:focus-visible, summary:focus-visible { outline: 2px solid #7dd3fc; outline-offset: 3px; }
.discard-button { background: #263044; border-color: #7e8da4; color: #f1f5f9; font-weight: 600; padding: 9px 16px; }
.discard-button:hover:not(:disabled) { background: #41333c; border-color: #fda4af; }
button:disabled { opacity: .45; cursor: not-allowed; }
button svg { flex-shrink: 0; }
summary { cursor: pointer; color: #7dd3fc; font-size: 12px; }
textarea, select, input { max-width: 100%; }
input[type=checkbox] { accent-color: #38bdf8; margin-top: 2px; flex-shrink: 0; }
.analysis-results { padding-top: 4px; }
.section-caption { font-size: 11px; color: #a9bed1; }
.account-conclusion { margin-top: 18px; border-left: 3px solid #66b3d3; padding: 4px 0 4px 20px; }
.account-conclusion h3 { margin: 6px 0 10px; font-size: 18px; font-weight: 600; }
.account-conclusion p { max-width: 1000px; font-size: 14px; line-height: 1.9; white-space: pre-wrap; color: #d5dfeb; }
.stale-notice { margin-top: 16px; padding: 10px 14px; border-left: 3px solid #facc15; background: #facc150c; font-size: 13px; color: #fde68a; }
.discussion-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; border-bottom: 1px solid #3a4661; }
.discussion-tabs button { border: 0; border-bottom: 2px solid transparent; border-radius: 0; min-height: 48px; padding: 10px 16px; font-size: 14px; color: #aebed0; }
.discussion-tabs button[aria-selected=true] { color: #e0f2fe; border-bottom-color: #7dd3fc; background: #233852; }
.tab-count { font-size: 11px; color: #aebed0; font-variant-numeric: tabular-nums; }
.discussion-panel { padding: 20px 0 4px; }
.discussion-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; padding-bottom: 8px; }
.discussion-heading h3 { font-size: 14px; font-weight: 600; }
.discussion-heading p { font-size: 12px; color: #aebed0; }
.finding-row { display: grid; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr); gap: 24px; padding: 24px 0; border-bottom: 1px solid #34405a; }
.finding-meta { position: relative; padding-left: 34px; }
.finding-number { position: absolute; left: 0; top: 2px; font-size: 11px; color: #94a3b8; font-variant-numeric: tabular-nums; }
.finding-meta h4 { font-size: 14px; font-weight: 600; line-height: 1.7; }
.finding-meta p { margin-top: 10px; font-size: 12px; color: #aebed0; line-height: 1.8; }
.action-label { display: inline-block; font-size: 12px; margin-top: 8px; padding-left: 8px; border-left: 2px solid #7dd3fc; color: #bae6fd; }
.action-reduce, .action-avoid { border-color: #fbbf24; color: #fde68a; }
.finding-content { min-width: 0; }
.finding-conclusion { font-size: 14px; font-weight: 500; line-height: 1.9; white-space: pre-wrap; }
.finding-condition { display: grid; grid-template-columns: 108px minmax(0, 1fr); gap: 12px; margin-top: 16px; padding-left: 14px; border-left: 2px solid #3f5872; font-size: 12px; line-height: 1.9; }
.finding-condition dt, .reasoning-body dt { color: #aebed0; }
.finding-condition dd { color: #d3dfed; }
.finding-reasoning { margin-top: 16px; }
.finding-reasoning summary { display: list-item; min-height: 28px; }
.reasoning-body { margin-top: 8px; padding: 12px 0 4px 18px; border-left: 1px solid #425470; }
.reasoning-body dl > div { display: grid; grid-template-columns: 108px minmax(0, 1fr); gap: 12px; margin-bottom: 14px; font-size: 12px; line-height: 1.9; }
.reasoning-body dd { white-space: pre-wrap; }
.evidence-links { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.evidence-links > span { color: #aebed0; font-size: 12px; margin-right: 8px; }
.evidence-links button { background: #172c43; color: #bae6fd; padding: 4px 8px; min-height: 30px; overflow-wrap: anywhere; }
.analysis-appendix { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 28px; margin-top: 20px; }
.analysis-appendix details { border-bottom: 1px solid #34405a; padding: 14px 0; line-height: 1.8; }
.confirmation-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; padding-top: 20px; }
.confirmation-bar p { color: #aebed0; font-size: 12px; }
@media (max-width: 640px) {
  .finding-row { grid-template-columns: minmax(0, 1fr); gap: 14px; padding: 20px 0; }
  .finding-meta { padding-left: 28px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; }
  .finding-meta h4 { width: 100%; } .finding-meta p, .action-label { margin-top: 0; }
  .finding-meta p br { display: none; }
  .finding-content { margin-left: 12px; }
  .finding-condition, .reasoning-body dl > div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .analysis-appendix { grid-template-columns: minmax(0, 1fr); }
  .account-conclusion { padding-left: 14px; }
  .discussion-tabs { gap: 2px; } .discussion-tabs button { padding: 8px 10px; font-size: 13px; }
}
</style>
