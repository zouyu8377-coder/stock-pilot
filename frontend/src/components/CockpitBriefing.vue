<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import ExternalAnalysis from './ExternalAnalysis.vue'
import DecisionReasoning from './DecisionReasoning.vue'
import HoldingActions from './HoldingActions.vue'
import InvestmentPlans from './InvestmentPlans.vue'
import { getAgentAutomationStatus, saveAgentAutomationSettings } from '../api/client'
import { sectorIdentity, uniqueModelOpportunities } from '../utils/decisionIdentity'
import { getLatestAgentReview, getRotationSummary, getAnalysisWorkflow, startAnalysisWorkflow, cancelAnalysisWorkflow,
  getAgentReviewTasks, executeAgentReviewTask, updateAgentReviewTaskStatus,
  type AgentReviewRun, type AnalysisWorkflow, type RotationSummary, type AgentReviewItem, type AgentReviewTask } from '../api/client'

const props = defineProps<{ accountOverview?: {
  status: string; reason: string; missing: boolean; pnl?: number | null; pnlPct?: number | null;
  positionPct?: number; cashPct?: number; exposure: string; asOf?: string;
  issues: { subject: string; reason: string; action: string; symbol?: string; kind?: string; source?: string; sourceUrl?: string }[];
  historicalNotes?: { subject: string; reason: string; source: string; sourceUrl: string }[];
} }>()
const emit = defineEmits<{
  (event: 'open-review'): void; (event: 'open-rotation'): void;
  (event: 'open-import', kind: 'current_holdings' | 'trade_history'): void;
  (event: 'select-symbol', symbol: string): void; (event: 'refresh-dashboard'): void;
}>()
const latest = ref<AgentReviewRun | null>(null)
const rotation = ref<RotationSummary | null>(null)
const workflow = ref<AnalysisWorkflow>({ status: 'idle', steps: [] })
const error = ref('')
const starting = ref(false)
const taskOpen = ref(false)
const tasks = ref<AgentReviewTask[]>([])
const taskError = ref('')
const executing = ref('')
const showAllTasks = ref(false)
const autoAfterSave = ref(false)
const consentSaving = ref(false)
async function setAutoAfterSave(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked
  consentSaving.value = true
  try { autoAfterSave.value = !!(await saveAgentAutomationSettings({ analysis_after_account_update: enabled })).analysis_after_account_update }
  catch { error.value = '自动分析授权未保存'; (event.target as HTMLInputElement).checked = autoAfterSave.value }
  finally { consentSaving.value = false }
}
const busy = computed(() => ['running', 'cancelling'].includes(workflow.value.status))
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const stageLabels: Record<string, string> = { inspect: '巡检取证', analyze: '模型分析', validate: '校验结果', advise: '形成建议', review: '历史回顾' }
const sourceLabels: Record<string, string> = { account_update: '账户更新后分析', workflow: '手动巡检分析', premarket: '每日巡检', scheduled: '收盘复盘', manual_confidence: '证据复核', manual_review: '手动复盘', manual_followup: '后续核查', manual: '手动任务循环', manual_evidence: '单项取证', external_export: '外部分析请求', external_import: '外部结果校验' }
const statusLabels: Record<string, string> = { idle: '尚未运行', running: '运行中', cancelling: '取消中', cancelled: '已取消', failed: '失败', completed: '已完成', interrupted: '已中断' }
const actionLabels: Record<string, string> = { hold: '继续持有', increase: '条件增持', reduce: '条件减持', watch: '证据复核', wait: '条件监控' }
const taskLabels: Record<string, string> = { pending: '待执行', running: '取证中', retry_wait: '等待重试', completed: '已取得证据', partial: '部分完成', failed: '取证受阻', manual_required: '需人工补充', dismissed: '已暂缓', superseded: '已替代' }
const fmt = (value?: number | null, suffix = '') => value == null ? '--' : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}${suffix}`
const time = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '--'
const day = (value: string) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date(value))
const historical = computed(() => !latest.value?.completed_at || day(latest.value.completed_at) !== day(new Date().toISOString()))
const allSectors = computed(() => [...(rotation.value?.potential_opportunities || []), ...(rotation.value?.early_turning || []), ...(rotation.value?.wait_pullback || [])])
const modelOpportunities = computed(() => historical.value ? [] : uniqueModelOpportunities(latest.value?.review?.opportunities || [], allSectors.value).slice(0, 3))
const activeTasks = computed(() => tasks.value.filter(t => !['dismissed', 'superseded'].includes(t.status)).sort((a, b) => Number(a.status === 'completed') - Number(b.status === 'completed')))
const monitors = computed(() => historical.value ? [] : [...(latest.value?.review?.risks || []), ...(latest.value?.review?.watch_items || []), ...modelOpportunities.value].filter(i => i.suggested_action === 'wait'))
function relatedTasks(item: AgentReviewItem) {
  return activeTasks.value.filter(t => t.subject === item.subject || (t.target_symbols || []).some(s => (item.target_symbols || []).includes(s)))
}
function taskSummary(item: AgentReviewItem) {
  const linked = relatedTasks(item)
  if (!linked.length) return item.suggested_action === 'wait' ? `监控条件：${item.trigger_condition || item.action_semantics}` : '尚无关联核查结果，巡检时补充任务'
  return linked.map(t => `${taskLabels[t.status]}：${t.task}`).join('；')
}
function canExecute(task: AgentReviewTask) {
  return task.tool.auto_executable && ['pending', 'retry_wait', 'partial', 'failed'].includes(task.status)
    && task.attempt_count < (task.max_attempts || 3) && (!task.next_retry_at || Date.parse(task.next_retry_at) <= Date.now())
}
async function runTask(task: AgentReviewTask) {
  executing.value = task.task_id; taskError.value = ''
  try { await executeAgentReviewTask(task.task_id); await load(); emit('refresh-dashboard') }
  catch (e: any) { taskError.value = e.response?.data?.detail || '核查未完成，请查看任务状态' }
  finally { executing.value = '' }
}
async function dismissTask(task: AgentReviewTask) {
  try { await updateAgentReviewTaskStatus(task.task_id, 'dismissed'); await load() }
  catch { taskError.value = '未能更新任务' }
}
function imported() { void load(); emit('refresh-dashboard') }
const opportunities = computed(() => {
  const seen = new Set<string>(modelOpportunities.value.map(i => sectorIdentity(i, allSectors.value)))
  return [...(rotation.value?.potential_opportunities || []), ...(rotation.value?.early_turning || []), ...(rotation.value?.wait_pullback || [])]
    .filter(item => { const key = `sector:${item.sector_id}`; if (seen.has(key) || ['unavailable', 'stale'].includes(item.data_quality)) return false; seen.add(key); return true }).slice(0, 3)
})
const oldRotation = computed(() => {
  const local = new Date(Date.now() + 8 * 3600000)
  if (local.getUTCHours() < 15 || (local.getUTCHours() === 15 && local.getUTCMinutes() < 10)) local.setUTCDate(local.getUTCDate() - 1)
  while ([0, 6].includes(local.getUTCDay())) local.setUTCDate(local.getUTCDate() - 1)
  // Conservative on exchange holidays until the shared trading calendar is available.
  return !rotation.value?.as_of || rotation.value.as_of.slice(0, 10) < local.toISOString().slice(0, 10)
})

async function load() {
  const result = await Promise.allSettled([getLatestAgentReview(), getRotationSummary()])
  if (result[0].status === 'fulfilled') latest.value = result[0].value
  if (result[1].status === 'fulfilled') rotation.value = result[1].value
  if (latest.value) {
    try { tasks.value = await getAgentReviewTasks(); taskError.value = '' }
    catch { taskError.value = '任务列表暂不可达，不能确认核查状态' }
  }
}
async function poll() {
  if (disposed) return
  try {
    const previous = workflow.value
    workflow.value = await getAnalysisWorkflow()
    if ((['running', 'cancelling'].includes(previous.status) && !busy.value) || (previous.job_id && workflow.value.job_id !== previous.job_id)) {
      void load(); emit('refresh-dashboard')
    }
  } catch { error.value = '任务状态暂不可达；无法确认进展，后台可能仍在运行。' }
  finally { if (!disposed) timer = setTimeout(poll, busy.value ? 2500 : 10000) }
}
async function start() {
  taskOpen.value = true
  if (busy.value || starting.value) return
  starting.value = true; error.value = ''
  try { workflow.value = await startAnalysisWorkflow() }
  catch (value: any) { error.value = value?.response?.data?.detail || '启动状态未确认，请查看任务状态。' }
  finally { starting.value = false; clearTimeout(timer); void poll() }
}
async function cancel() {
  try { workflow.value = await cancelAnalysisWorkflow() }
  catch { error.value = '取消请求未确认，请稍后查看状态。' }
}
onMounted(() => { void load(); void poll(); void getAgentAutomationStatus().then(v => { autoAfterSave.value = !!v.settings.analysis_after_account_update }).catch(() => {}) })
onUnmounted(() => { disposed = true; clearTimeout(timer) })
</script>

<template>
  <section class="min-w-0 space-y-4 [overflow-wrap:anywhere]">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
      <h2 class="text-base font-semibold text-foreground">决策工作台</h2>
      <div class="flex flex-wrap gap-2 text-xs">
        <button class="h-9 rounded bg-primary px-3 font-medium text-primary-foreground disabled:opacity-60" :disabled="starting" @click="start">{{ busy ? '查看运行进度' : '更新分析' }}</button>
        <button class="h-9 rounded border border-border px-3 text-foreground" @click="emit('open-import', 'current_holdings')">更新账户</button>
        <button class="h-9 px-2 text-sky-300" @click="emit('open-review')">复盘与记录</button>
      </div>
    </div>
    <InvestmentPlans />
    <label class="flex items-start gap-2 text-xs text-muted-foreground"><input type="checkbox" class="mt-0.5" :checked="autoAfterSave" :disabled="consentSaving" @change="setAutoAfterSave" />确认保存账户后自动分析（将账户与相关证据发送至已配置模型，受自动任务预算约束）</label>
    <p v-if="workflow.unchanged" class="text-xs text-sky-300">本次已检查，无新增变化；保留上次分析，不重复消耗模型调用。</p>
    <p v-if="error" role="alert" class="text-sm text-warning">{{ error }}</p>
    <details :open="taskOpen || busy" class="border-y border-border py-2" @toggle="taskOpen = ($event.target as HTMLDetailsElement).open">
      <summary class="cursor-pointer text-xs text-sky-300">{{ sourceLabels[workflow.source || 'workflow'] }} · {{ statusLabels[workflow.status] || workflow.status }}<span v-if="busy"> · {{ stageLabels[workflow.stage || 'inspect'] }} · 已用 {{ fmt(workflow.elapsed_seconds) }} 秒</span></summary>
      <div class="mt-2 flex flex-wrap items-start justify-between gap-3 text-xs">
        <div class="space-y-1 text-muted-foreground">
          <p class="text-foreground">{{ workflow.detail || '等待开始巡检' }}<span v-if="workflow.total_items != null"> · {{ workflow.completed_items }}/{{ workflow.total_items }} 项</span></p>
          <p>开始 {{ time(workflow.started_at_local) }} · 最近进展 {{ time(workflow.last_progress_at) }}</p>
          <p>模型请求 {{ workflow.model_requests || 0 }} 次 · 已返回 Token {{ fmt(workflow.tokens || 0) }}</p>
          <p v-if="workflow.overdue" class="text-warning">当前阶段超过预期等待时间，尚未确认卡死；可取消后续步骤。</p>
          <p v-if="workflow.error" role="alert" class="text-warning">{{ workflow.error }} · {{ workflow.review_run_id ? '新建议已保存，后续回顾未完成。' : '本次未发布新结论，保留历史分析。' }}</p>
          <p v-if="workflow.retry?.paused_today" class="text-warning">今日自动重试已暂停；失败请求也占用预算。</p>
          <p v-else-if="workflow.retry?.next_retry_at">最早自动重试 {{ time(workflow.retry.next_retry_at) }}</p>
          <p v-if="workflow.status === 'cancelling'">当前网络请求需返回或超时后才会释放，不再启动后续步骤。</p>
          <p v-if="workflow.new_task_results">新任务取证 {{ workflow.new_task_results.executed }} 项，可用 {{ workflow.new_task_results.usable }} 项</p>
          <p v-if="workflow.followup_pending" class="text-warning">{{ workflow.followup_note || '新证据已保存，结论尚待下一次模型分析更新。' }}</p>
        </div>
        <button v-if="busy" class="h-8 rounded border border-border px-3 text-foreground disabled:opacity-50" :disabled="workflow.status === 'cancelling'" @click="cancel">取消后续步骤</button>
        <button v-else-if="['failed', 'interrupted', 'cancelled'].includes(workflow.status)" class="h-8 rounded border border-border px-3 text-foreground" @click="start">重新巡检（复用有效证据）</button>
      </div>
    </details>
    <section class="border-b border-border pb-4">
      <div class="flex flex-wrap items-baseline justify-between gap-2"><h3 class="text-sm font-medium text-muted-foreground">账户概览</h3><span class="text-xs text-muted-foreground">规则检查 {{ time(accountOverview?.asOf) }}</span></div>
      <div class="mt-2 text-xl font-semibold" :class="accountOverview?.status === '暂无明显异常' ? 'text-foreground' : 'text-warning'">{{ accountOverview?.status || '证据不足' }}</div>
      <p class="mt-1 text-sm text-foreground">{{ accountOverview?.reason || '尚未取得完整账户数据。' }}</p>
      <p v-if="accountOverview?.missing && accountOverview?.issues.length" class="mt-1 text-xs text-warning">另有证据缺口，以上异常不是完整风险清单。</p>
      <div class="mt-4 grid grid-cols-2 gap-4 text-xs lg:grid-cols-4">
        <div><div class="text-muted-foreground">账户总盈亏</div><div class="mt-1 font-mono text-base" :class="accountOverview?.pnl == null ? 'text-muted-foreground' : Number(accountOverview.pnl) >= 0 ? 'text-red-400' : 'text-emerald-400'">{{ fmt(accountOverview?.pnl) }} <span class="text-xs">{{ fmt(accountOverview?.pnlPct, '%') }}</span></div></div>
        <div><div class="text-muted-foreground">仓位</div><div class="mt-1 font-mono text-base text-foreground">{{ fmt(accountOverview?.positionPct, '%') }}</div></div>
        <div><div class="text-muted-foreground">现金比例</div><div class="mt-1 font-mono text-base text-foreground">{{ fmt(accountOverview?.cashPct, '%') }}</div></div>
        <div><div class="text-muted-foreground">最大主方向暴露</div><div class="mt-1 text-base text-foreground">{{ accountOverview?.exposure || '--' }}</div></div>
      </div>
    </section>
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section class="min-w-0">
        <div class="flex items-baseline justify-between gap-2"><h3 class="text-base font-semibold">账户调整建议</h3><button class="shrink-0 text-xs text-sky-300" @click="emit('open-review')">分析记录</button></div>
        <p class="mt-1 text-xs text-muted-foreground">{{ historical ? '历史 AI 分析，不作为今日操作建议' : '最新 AI 分析' }} · {{ time(latest?.completed_at) }}</p>
        <HoldingActions :revision="`${latest?.run_id || ''}:${workflow.status}:${accountOverview?.asOf || ''}`" :issues="accountOverview?.issues" @select-symbol="emit('select-symbol', $event)" @update-analysis="start" />
      </section>
      <section class="min-w-0">
        <div class="flex items-baseline justify-between gap-2"><h3 class="text-base font-semibold">潜在机会</h3><button class="shrink-0 text-xs text-sky-300" @click="emit('open-rotation')">发现与研究</button></div>
        <p class="mt-1 text-xs text-muted-foreground">方向证据截至 {{ rotation?.as_of || '--' }}</p>
        <div v-for="item in modelOpportunities" :key="item.item_id" class="border-b border-border py-3 text-sm">
          <div class="font-medium">{{ item.subject }} <span class="ml-2 text-xs text-sky-300">{{ actionLabels[item.suggested_action || 'watch'] }}</span></div>
          <p class="mt-1 text-muted-foreground">{{ item.conclusion }}</p>
          <p class="mt-1 font-medium">当前建议：{{ item.action_semantics }}</p>
          <DecisionReasoning :item="item" />
          <p class="mt-1 text-xs text-foreground">确认条件：{{ item.trigger_condition || '尚未形成可执行条件，不作为买入建议' }}</p>
          <p class="mt-2 text-xs text-sky-300">{{ taskSummary(item) }}</p>
          <details class="mt-2 text-xs"><summary class="cursor-pointer text-sky-300">账户影响与证据</summary><p class="mt-1">{{ item.account_impact || '账户约束尚待确认' }}</p><p>失效：{{ item.invalidation_conditions.join('；') || '尚待明确' }}</p><p>{{ item.evidence_refs.join(' · ') }}</p></details>
          <button v-if="item.target_symbols?.[0]" class="mt-2 text-xs text-sky-300" @click="emit('select-symbol', item.target_symbols[0])">研究标的</button>
        </div>
        <p v-if="oldRotation" class="mt-3 text-sm text-warning">方向数据未就绪或较旧，暂不呈现为当前机会。</p>
        <template v-else>
          <div v-for="row in opportunities.slice(0, 3 - modelOpportunities.length)" :key="row.sector_id" class="border-b border-border py-3 text-sm">
            <div class="font-medium">{{ row.name }} <span class="ml-2 text-xs text-sky-300">{{ row.action_label || '待核查方向' }}</span></div>
            <p class="mt-1 text-muted-foreground">{{ row.opportunity_reason }}</p>
            <p class="mt-1 text-xs text-muted-foreground">下一步：核验代表标的趋势、量能与近期事件；条件未确认前不形成买入建议。</p>
            <button class="mt-2 text-xs text-sky-300" @click="emit('open-rotation')">查看代表标的与证据</button>
          </div>
          <p v-if="!opportunities.length && !modelOpportunities.length" class="py-4 text-sm text-muted-foreground">当前没有证据足够的候选方向，不强行推荐。</p>
        </template>
      </section>
    </div>
    <details v-if="accountOverview?.historicalNotes?.length" class="border-t border-border pt-3 text-xs text-muted-foreground"><summary class="cursor-pointer">历史经营风险背景 · 不作为当前减持触发条件</summary><div v-for="note in accountOverview.historicalNotes" :key="note.subject" class="space-y-1 py-2"><p>{{ note.subject }}：{{ note.reason }}</p><a v-if="note.sourceUrl?.startsWith('https://')" :href="note.sourceUrl" target="_blank" rel="noopener noreferrer" class="text-sky-300">{{ note.source }}</a></div></details>
    <details class="border-t border-border pt-3">
      <summary class="cursor-pointer text-sm text-sky-300">高级操作 · 取证任务与运行记录</summary>
      <p v-if="taskError" class="mt-2 text-sm text-warning">{{ taskError }}</p>
      <div v-for="issue in accountOverview?.issues" :key="issue.subject" class="border-b border-border py-2 text-sm"><p class="font-medium">{{ issue.subject }} · 用户确认</p><p class="text-xs text-muted-foreground">{{ issue.action }}</p><button class="mt-1 text-xs text-sky-300" @click="emit('open-import', 'current_holdings')">持仓与账户设置</button></div>
      <div v-for="task in activeTasks.slice(0, showAllTasks ? activeTasks.length : 4)" :key="task.task_id" class="flex flex-wrap items-start justify-between gap-3 border-b border-border py-3 text-sm">
        <div class="min-w-0 flex-1 space-y-1">
          <p class="font-medium">{{ task.subject }} · {{ taskLabels[task.status] || task.status }}</p>
          <p>{{ task.task }}</p><p class="text-xs text-muted-foreground">负责人：{{ task.tool.auto_executable ? 'Agent' : '用户' }} · 完成标准：{{ task.success_criteria || '尚未定义，需明确后执行' }}</p>
          <p v-if="task.missing_evidence?.length" class="text-xs text-muted-foreground">{{ task.status === 'completed' ? '本次核查事实' : '缺失事实' }}：{{ task.missing_evidence.join('；') }}</p>
          <p v-if="task.error || !task.tool.auto_executable" class="text-xs text-warning">{{ task.error || task.tool.mapping_reason }}</p>
          <p v-if="task.result" class="text-xs text-sky-300">证据：{{ task.result.evidence_ref }} · {{ time(task.completed_at) }} · 已取证不代表建议已更新</p>
          <details v-if="task.result" class="text-xs"><summary class="cursor-pointer text-sky-300">核查结果</summary><pre class="max-h-48 overflow-auto whitespace-pre-wrap break-all">{{ JSON.stringify(task.result.payload, null, 2) }}</pre></details>
          <p v-if="task.next_retry_at" class="text-xs text-muted-foreground">下次可重试：{{ time(task.next_retry_at) }}</p>
        </div>
        <div class="flex gap-2 text-xs"><button v-if="canExecute(task)" class="rounded border border-border px-3 py-2 disabled:opacity-50" :disabled="busy || !!executing" @click="runTask(task)">{{ executing === task.task_id ? '核查中' : '立即核查' }}</button><button v-if="task.status === 'manual_required'" class="px-2 text-sky-300" @click="emit('open-review')">查看人工核查</button><button v-if="!['running', 'completed'].includes(task.status)" class="px-2 text-muted-foreground disabled:opacity-50" :disabled="busy || !!executing" @click="dismissTask(task)">暂缓</button></div>
      </div>
      <button v-if="activeTasks.length > 4" class="mt-2 text-xs text-sky-300" @click="showAllTasks = !showAllTasks">{{ showAllTasks ? '收起任务' : `展开全部 ${activeTasks.length} 项` }}</button>
      <div v-for="item in monitors" :key="item.item_id" class="border-b border-border py-2 text-sm"><span class="font-medium">{{ item.subject }} · 条件监控</span><p class="text-xs text-muted-foreground">{{ item.trigger_condition || item.action_semantics }} · {{ item.horizon || '下次巡检复核' }}</p></div>
      <p v-if="!activeTasks.length && !monitors.length && !taskError" class="py-3 text-sm text-muted-foreground">暂无已登记任务。</p>
    </details>
    <details class="border-t border-border pt-3"><summary class="cursor-pointer text-sm text-sky-300">外部模型分析</summary><ExternalAnalysis @imported="imported" /></details>
  </section>
</template>
