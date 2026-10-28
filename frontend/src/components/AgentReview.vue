<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DecisionReasoning from './DecisionReasoning.vue'
import {
  annotatePortfolioAction,
  executeAgentReviewTask,
  executePendingAgentReviewTasks,
  generateDailyAgentReview,
  getAgentAutomationStatus,
  getAgentMonthlyReport,
  getAgentLearningPolicies,
  getAgentOutcomes,
  getAgentReviewHistory,
  getAgentReviewStatus,
  getAgentReviewTasks,
  getLatestAgentReview,
  runAgentReviewCycle,
  refreshAgentConfidenceNow,
  runAgentAutomationNow,
  saveAgentAutomationSettings,
  updateAgentReviewTaskStatus,
  type AgentAutomationSettings,
  type AgentAutomationStatus,
  type AgentMonthlyReport,
  type AgentLearningPolicyRegistry,
  type AgentOutcomes,
  type AgentReviewItem,
  type AgentReviewRun,
  type AgentReviewStatus,
  type AgentReviewTask,
} from '../api/client'

const status = ref<AgentReviewStatus | null>(null)
const latest = ref<AgentReviewRun | null>(null)
const history = ref<AgentReviewRun[]>([])
const tasks = ref<AgentReviewTask[]>([])
const automation = ref<AgentAutomationStatus | null>(null)
const automationSettings = ref<AgentAutomationSettings | null>(null)
const outcomes = ref<AgentOutcomes | null>(null)
const monthlyReport = ref<AgentMonthlyReport | null>(null)
const learningPolicies = ref<AgentLearningPolicyRegistry | null>(null)
const actionReasons = ref<Record<string, string>>({})
const loading = ref(false)
const batchLoading = ref(false)
const cycleLoading = ref(false)
const taskBusyId = ref('')
const automationSaving = ref(false)
const automationRunning = ref(false)
const premarketRunning = ref(false)
const outcomeBusyId = ref('')
const initialLoading = ref(true)
const forceContext = ref(false)
const error = ref('')

const review = computed(() => latest.value?.review)
const pendingTaskCount = computed(() => tasks.value.filter((task) => task.status === 'pending' || task.status === 'retry_wait').length)
const completedTaskCount = computed(() => tasks.value.filter((task) => ['completed', 'partial'].includes(task.status)).length)
const sourceHealth = computed(() => automation.value?.task_health?.source_health || [])
const activePolicies = computed(() => learningPolicies.value?.policies.filter((policy) => policy.status === 'active') || [])
const monitoringPolicies = computed(() => learningPolicies.value?.policies.filter((policy) => policy.status === 'monitoring') || [])

const formatTime = (value?: string | null) => {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

const confidenceLabel = (confidence: AgentReviewItem['confidence']) => ({
  high: '高置信',
  medium: '中置信',
  low: '低置信',
}[confidence])

const confidenceClass = (confidence: AgentReviewItem['confidence']) => ({
  high: 'border-positive/30 bg-positive/10 text-positive',
  medium: 'border-warning/30 bg-warning/10 text-warning',
  low: 'border-border bg-secondary text-muted-foreground',
}[confidence])

const priorityClass = (priority: 'high' | 'medium' | 'low') => ({
  high: 'text-negative',
  medium: 'text-warning',
  low: 'text-muted-foreground',
}[priority])

const taskStatus = (value: AgentReviewTask['status']) => ({
  pending: { label: '待执行', class: 'border-warning/30 bg-warning/10 text-warning' },
  running: { label: '执行中', class: 'border-primary/30 bg-primary/10 text-primary' },
  retry_wait: { label: '等待重试', class: 'border-warning/30 bg-warning/10 text-warning' },
  completed: { label: '已取证', class: 'border-positive/30 bg-positive/10 text-positive' },
  partial: { label: '部分取证', class: 'border-warning/30 bg-warning/10 text-warning' },
  failed: { label: '失败', class: 'border-negative/30 bg-negative/10 text-negative' },
  manual_required: { label: '人工核查', class: 'border-border bg-secondary text-muted-foreground' },
  dismissed: { label: '已忽略', class: 'border-border bg-secondary text-muted-foreground' },
  superseded: { label: '已被新任务取代', class: 'border-border bg-secondary text-muted-foreground' },
}[value])

const verdictLabel = (value?: string | null) => ({
  supported: '得到支持',
  not_supported: '未得到支持',
  mixed: '结果混合',
  insufficient: '证据不足',
}[value || ''] || '观察中')

const verdictClass = (value?: string | null) => ({
  supported: 'text-positive',
  not_supported: 'text-negative',
  mixed: 'text-warning',
  insufficient: 'text-muted-foreground',
}[value || ''] || 'text-muted-foreground')

const lifecycleLabel = (value?: string | null) => ({
  proposed: '已提出',
  open: '观察中',
  tracking: '待补数据',
  evaluated: '已评价',
  invalidated: '已失效',
}[value || ''] || value || '观察中')

const strategyLabel = (value?: string | null) => ({
  aligned: '与当时建议一致',
  conflicted: '与当时建议冲突',
  mixed: '当时建议存在分歧',
  no_direct_recommendation: '当时无直接建议',
}[value || ''] || '尚未关联建议')

const strategyClass = (value?: string | null) => ({
  aligned: 'text-positive',
  conflicted: 'text-warning',
  mixed: 'text-warning',
  no_direct_recommendation: 'text-muted-foreground',
}[value || ''] || 'text-muted-foreground')

const formatMetric = (value?: number | null, suffix = '%') => (
  value === null || value === undefined ? '--' : `${value}${suffix}`
)

const formatQuantity = (value?: number | null) => {
  if (value === null || value === undefined) return '--'
  return `${value > 0 ? '+' : ''}${Number(value).toLocaleString('zh-CN')}`
}

const operationPatternLabel = (value?: string) => ({
  accumulation: '连续净买入',
  distribution: '连续净卖出',
  two_way_net_buy: '双向操作后净买入',
  two_way_net_sell: '双向操作后净卖出',
  round_trip_flat: '买卖往返后持仓不变',
}[value || ''] || value || '--')

const attributionPathLabel = (value?: string) => ({
  added_risk_then_adverse_move: '加仓后出现明显逆向波动',
  added_risk_with_follow_through: '加仓后获得趋势跟随',
  added_risk_without_clear_follow_through: '加仓后尚无明确跟随',
  risk_reduction_avoided_decline: '减仓规避了后续下跌',
  risk_reduction_missed_subsequent_gain: '减仓后标的继续上涨',
  risk_reduction_neutral_afterward: '减仓后走势基本中性',
}[value || ''] || value || '--')

const sourceLabel = (value?: string) => ({
  stock_snapshot: '标的行情',
  rotation_refresh: '轮动数据',
  event_snapshot: '事件雷达',
  disclosure_snapshot: '公告与调研',
}[value || ''] || value || '--')

const sourceStatusLabel = (value?: string) => ({
  completed: '成功',
  partial: '部分成功',
  retry_wait: '等待重试',
  failed: '失败',
}[value || ''] || value || '--')

const formatMoney = (value?: number | null) => {
  if (value === null || value === undefined) return '--'
  return `${value > 0 ? '+' : ''}${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
}

const errorMessage = (value: any) => {
  const detail = value?.response?.data?.detail
  return detail || value?.message || String(value)
}

const loadReview = async () => {
  initialLoading.value = true
  error.value = ''
  try {
    const [nextStatus, nextLatest, nextHistory, nextAutomation, nextOutcomes, nextMonthlyReport, nextLearningPolicies] = await Promise.all([
      getAgentReviewStatus(),
      getLatestAgentReview(),
      getAgentReviewHistory(),
      getAgentAutomationStatus(),
      getAgentOutcomes(),
      getAgentMonthlyReport(),
      getAgentLearningPolicies(),
    ])
    status.value = nextStatus
    latest.value = nextLatest
    history.value = nextHistory
    automation.value = nextAutomation
    automationSettings.value = { ...nextAutomation.settings }
    outcomes.value = nextOutcomes
    monthlyReport.value = nextMonthlyReport
    learningPolicies.value = nextLearningPolicies
    tasks.value = nextLatest ? await getAgentReviewTasks() : []
  } catch (value) {
    error.value = `复盘服务读取失败：${errorMessage(value)}`
  } finally {
    initialLoading.value = false
  }
}

const generateReview = async () => {
  loading.value = true
  error.value = ''
  try {
    latest.value = await generateDailyAgentReview(forceContext.value)
    const [nextStatus, nextHistory] = await Promise.all([
      getAgentReviewStatus(),
      getAgentReviewHistory(),
    ])
    status.value = nextStatus
    history.value = nextHistory
    tasks.value = await getAgentReviewTasks()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    loading.value = false
  }
}

const executeOneTask = async (task: AgentReviewTask) => {
  taskBusyId.value = task.task_id
  error.value = ''
  try {
    await executeAgentReviewTask(task.task_id)
    tasks.value = await getAgentReviewTasks()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    taskBusyId.value = ''
  }
}

const executeAllTasks = async () => {
  batchLoading.value = true
  error.value = ''
  try {
    await executePendingAgentReviewTasks()
    tasks.value = await getAgentReviewTasks()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    batchLoading.value = false
  }
}

const dismissTask = async (task: AgentReviewTask) => {
  taskBusyId.value = task.task_id
  try {
    await updateAgentReviewTaskStatus(task.task_id, 'dismissed')
    tasks.value = await getAgentReviewTasks()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    taskBusyId.value = ''
  }
}

const runReviewCycle = async () => {
  cycleLoading.value = true
  error.value = ''
  try {
    latest.value = await runAgentReviewCycle()
    const [nextStatus, nextHistory, nextTasks] = await Promise.all([
      getAgentReviewStatus(),
      getAgentReviewHistory(),
      getAgentReviewTasks(),
    ])
    status.value = nextStatus
    history.value = nextHistory
    tasks.value = nextTasks
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    cycleLoading.value = false
  }
}

const saveAutomation = async () => {
  if (!automationSettings.value) return
  automationSaving.value = true
  error.value = ''
  try {
    const saved = await saveAgentAutomationSettings(automationSettings.value)
    automationSettings.value = { ...saved }
    automation.value = await getAgentAutomationStatus()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    automationSaving.value = false
  }
}

const runAutomation = async () => {
  automationRunning.value = true
  error.value = ''
  try {
    await runAgentAutomationNow()
    await loadReview()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    automationRunning.value = false
  }
}

const runPremarket = async () => {
  premarketRunning.value = true
  error.value = ''
  try {
    await refreshAgentConfidenceNow()
    await loadReview()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    premarketRunning.value = false
  }
}

const confirmAction = async (actionId: string) => {
  outcomeBusyId.value = actionId
  error.value = ''
  try {
    await annotatePortfolioAction(actionId, {
      confirmed: true,
      reason: actionReasons.value[actionId] || '',
    })
    outcomes.value = await getAgentOutcomes()
    monthlyReport.value = await getAgentMonthlyReport()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    outcomeBusyId.value = ''
  }
}

const dismissAction = async (actionId: string) => {
  outcomeBusyId.value = actionId
  error.value = ''
  try {
    await annotatePortfolioAction(actionId, {
      confirmed: false,
      dismissed: true,
      reason: actionReasons.value[actionId] || '',
    })
    outcomes.value = await getAgentOutcomes()
    monthlyReport.value = await getAgentMonthlyReport()
  } catch (value) {
    error.value = errorMessage(value)
  } finally {
    outcomeBusyId.value = ''
  }
}

onMounted(loadReview)
</script>

<template>
  <section class="w-[calc(100vw-1.5rem)] max-w-full space-y-4 sm:w-[calc(100vw-3rem)]">
    <div class="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-semibold text-foreground">AI 复盘</h1>
          <span
            :class="[
              'inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px]',
              status?.enabled ? 'border-positive/30 bg-positive/10 text-positive' : 'border-negative/30 bg-negative/10 text-negative',
            ]"
          >
            <span :class="['h-1.5 w-1.5 rounded-full', status?.enabled ? 'bg-positive' : 'bg-negative']"></span>
            {{ status?.enabled ? '模型已连接' : '模型未配置' }}
          </span>
        </div>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ status?.model || 'DeepSeek' }} 基于本地账户、事件与轮动证据生成结构化复盘。
        </p>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-3">
        <label class="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input v-model="forceContext" type="checkbox" class="h-4 w-4 accent-primary" />
          生成前刷新本地上下文
        </label>
        <button
          class="flex h-9 items-center gap-2 rounded bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="loading || !status?.enabled"
          @click="generateReview"
        >
          <svg :class="['h-4 w-4', loading ? 'animate-spin' : '']" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ loading ? 'DeepSeek 正在复盘…' : '生成今日复盘' }}
        </button>
      </div>
    </div>

    <div class="flex items-start gap-2 border-l-2 border-primary/50 bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
      <svg class="mt-0.5 h-4 w-4 shrink-0 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 11c1.657 0 3-1.343 3-3V5a3 3 0 00-6 0v3c0 1.657 1.343 3 3 3zm-6 0h12v9H6v-9z" />
      </svg>
      <span>{{ status?.privacy_boundary || '仅在主动生成或已授权的自动循环中发送复盘上下文，不会自动执行交易或调仓。' }}</span>
    </div>

    <div v-if="automationSettings" class="border border-border bg-card">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2">
        <div>
          <h2 class="text-sm font-semibold text-foreground">自动任务循环</h2>
          <p class="mt-0.5 text-[11px] text-muted-foreground">
            开盘前核查低置信度结论；收盘后仅在有确认交易时复盘，每周最后交易日改为五交易日周复盘。
          </p>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <span :class="automationSettings.enabled ? 'text-positive' : 'text-muted-foreground'">
            {{ automationSettings.enabled ? '已启用' : '未启用' }}
          </span>
          <label class="relative inline-flex cursor-pointer items-center">
            <input v-model="automationSettings.enabled" type="checkbox" class="peer sr-only" />
            <span class="h-5 w-9 rounded-full bg-secondary transition peer-checked:bg-primary"></span>
            <span class="absolute left-0.5 h-4 w-4 rounded-full bg-foreground transition peer-checked:translate-x-4"></span>
          </label>
        </div>
      </div>
      <div class="grid gap-3 px-3 py-3 text-xs sm:grid-cols-2 lg:grid-cols-9">
        <label class="space-y-1 text-muted-foreground">
          <span>收盘触发时间</span>
          <input v-model="automationSettings.run_time" type="time" class="h-8 w-full rounded border border-border bg-background px-2 text-foreground" />
        </label>
        <label class="space-y-1 text-muted-foreground">
          <span>开盘前取证</span>
          <input v-model="automationSettings.premarket_time" type="time" class="h-8 w-full rounded border border-border bg-background px-2 text-foreground" />
        </label>
        <label class="space-y-1 text-muted-foreground">
          <span>自动模型调用日上限</span>
          <input v-model.number="automationSettings.max_model_calls_per_day" type="number" min="0" max="3" class="h-8 w-full rounded border border-border bg-background px-2 text-foreground" />
        </label>
        <label class="space-y-1 text-muted-foreground">
          <span>主动取证上限</span>
          <input v-model.number="automationSettings.max_proactive_tasks_per_day" type="number" min="1" max="8" class="h-8 w-full rounded border border-border bg-background px-2 text-foreground" />
        </label>
        <label class="flex items-end gap-2 pb-2 text-muted-foreground">
          <input v-model="automationSettings.weekdays_only" type="checkbox" class="h-4 w-4 accent-primary" />
          仅工作日
        </label>
        <label class="flex items-end gap-2 pb-2 text-muted-foreground">
          <input v-model="automationSettings.auto_model_review" type="checkbox" class="h-4 w-4 accent-primary" />
          自动调用 DeepSeek
        </label>
        <label class="flex items-end gap-2 pb-2 text-muted-foreground">
          <input v-model="automationSettings.premarket_enabled" type="checkbox" class="h-4 w-4 accent-primary" />
          启用晨间取证
        </label>
        <div class="flex items-end justify-end gap-2 lg:col-span-2">
          <button class="h-8 rounded border border-border px-3 text-foreground hover:bg-secondary disabled:opacity-50" :disabled="automationSaving" @click="saveAutomation">
            {{ automationSaving ? '保存中…' : '保存设置' }}
          </button>
          <button class="h-8 rounded border border-sky-400/50 px-3 text-sky-300 hover:bg-sky-400/10 disabled:opacity-50" :disabled="premarketRunning" @click="runPremarket">
            {{ premarketRunning ? '刷新中…' : '刷新置信度' }}
          </button>
          <button class="h-8 rounded bg-primary px-3 text-primary-foreground hover:bg-primary/90 disabled:opacity-50" :disabled="automationRunning" @click="runAutomation">
            {{ automationRunning ? '循环运行中…' : '立即运行' }}
          </button>
        </div>
      </div>
      <div class="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
        晨间取证 {{ automationSettings.premarket_enabled ? '已启用' : '未启用' }} · {{ automationSettings.premarket_time }}
        · 待核查低置信度 {{ automation?.premarket_trigger?.pending_low_confidence_count || 0 }} 项
        · 覆盖缺口待办 {{ automation?.coverage_planner?.pending_count || 0 }} 项 / {{ automation?.coverage_planner?.daily_budget || automationSettings.max_proactive_tasks_per_day }} 项
        · 上一次晨检 {{ formatTime(automation?.premarket_trigger?.latest_run_completed_at) }}
        <span class="text-slate-400">（有新证据才调用 DeepSeek；自动晨检每日最多 1 次，手动触发不受日限额约束）</span>
        <br />
        今日已确认交易 {{ automation?.trade_trigger?.today_confirmed_action_count || 0 }} 条
        <span :class="automation?.trade_trigger?.review_period === 'weekly' || automation?.trade_trigger?.has_confirmed_trade_today ? 'text-positive' : 'text-muted-foreground'">
          · {{ automation?.trade_trigger?.review_period === 'weekly'
            ? `本周有确认操作则于 ${automationSettings.run_time} 触发周复盘，不重复日复盘`
            : (automation?.trade_trigger?.has_confirmed_trade_today ? `${automationSettings.run_time} 将触发日复盘` : '无交易，不自动触发') }}
        </span>
        · 上一次复盘 {{ formatTime(automation?.latest_review_completed_at || latest?.completed_at) }}
        · 今日计划复盘模型调用 {{ automation?.scheduled_model_calls_today || 0 }} / {{ automationSettings.max_model_calls_per_day }}
        <span v-if="automation?.task_health">
          · 可重试任务 {{ automation.task_health.retryable_count }}
          <span v-if="automation.task_health.failure_counts.transient_source_error">
            · 临时源错误 {{ automation.task_health.failure_counts.transient_source_error }}
          </span>
        </span>
        <span v-if="automation?.latest_run"> · 最近循环 {{ formatTime(automation.latest_run.completed_at_local) }} · {{ automation.latest_run.status }}</span>
        <span v-if="automation?.coverage_planner?.last_plan?.coverage_before" class="block mt-1 text-slate-400">
          上次主动取证前覆盖：健康 {{ automation.coverage_planner.last_plan.coverage_before.health_coverage_pct ?? '--' }}%
          · 吸引力 {{ automation.coverage_planner.last_plan.coverage_before.attractiveness_coverage_pct ?? '--' }}%
          · 联合 {{ automation.coverage_planner.last_plan.coverage_before.joint_coverage_pct ?? '--' }}%
        </span>
      </div>
    </div>

    <div v-if="initialLoading" class="py-16 text-center text-sm text-muted-foreground">正在读取复盘记录…</div>
    <div v-else-if="error" class="border border-negative/30 bg-negative/10 px-4 py-3 text-sm text-negative">
      {{ error }}
    </div>

    <template v-if="!initialLoading && review">
      <div class="grid grid-cols-2 gap-px overflow-hidden rounded border border-border bg-border text-xs md:grid-cols-5">
        <div class="bg-card px-3 py-2"><span class="text-muted-foreground">模型</span><div class="mt-1 font-mono text-foreground">{{ latest?.model }}</div></div>
        <div class="bg-card px-3 py-2"><span class="text-muted-foreground">完成时间</span><div class="mt-1 text-foreground">{{ formatTime(latest?.completed_at) }}</div></div>
        <div class="bg-card px-3 py-2"><span class="text-muted-foreground">耗时</span><div class="mt-1 font-mono text-foreground">{{ ((latest?.elapsed_ms || 0) / 1000).toFixed(1) }}s</div></div>
        <div class="bg-card px-3 py-2"><span class="text-muted-foreground">证据</span><div class="mt-1 font-mono text-foreground">{{ latest?.context?.evidence_count || 0 }} 条</div></div>
        <div class="bg-card px-3 py-2"><span class="text-muted-foreground">Token</span><div class="mt-1 font-mono text-foreground">{{ latest?.usage?.total_tokens || 0 }}</div></div>
      </div>

      <div class="border-y border-border py-4">
        <div class="flex flex-wrap items-center gap-2">
          <span :class="['h-2 w-2 rounded-full', review.data_status.usable ? 'bg-positive' : 'bg-warning']"></span>
          <span class="text-xs font-medium uppercase text-muted-foreground">今日结论</span>
        </div>
        <h2 class="mt-2 text-lg font-semibold text-foreground">{{ review.headline }}</h2>
        <p class="mt-2 text-sm leading-6 text-muted-foreground">{{ review.summary }}</p>
        <p class="mt-2 text-xs text-muted-foreground">
          数据状态：{{ review.data_status.summary }}
          <span v-if="review.data_status.stale_evidence_refs.length"> · 陈旧 {{ review.data_status.stale_evidence_refs.length }}</span>
          <span v-if="review.data_status.missing_evidence_refs.length"> · 缺失 {{ review.data_status.missing_evidence_refs.length }}</span>
        </p>
      </div>

      <section v-if="review.daily_operation_review?.action_count" class="border-y border-border">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border py-3">
          <div>
            <h3 class="text-sm font-semibold text-foreground">当日交易整体复盘</h3>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ review.daily_operation_review.trading_date }}
              · {{ review.daily_operation_review.action_count }} 次已确认操作
            </p>
          </div>
          <span class="text-[11px] text-muted-foreground">完整台账保留 · 最多展开 3 项代表性操作</span>
        </div>
        <p class="py-3 text-sm leading-6 text-foreground">{{ review.daily_operation_review.overall_reflection }}</p>
        <div class="divide-y divide-border border-t border-border">
          <article v-for="item in review.daily_operation_review.items" :key="item.action_id" class="grid gap-3 py-3 md:grid-cols-[180px_minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <div class="font-medium text-foreground">{{ item.name }}</div>
              <div class="mt-1 font-mono text-xs text-muted-foreground">
                {{ item.symbol }} · {{ item.action_type === 'buy' ? '买入' : '卖出' }}
              </div>
            </div>
            <div>
              <div class="text-[10px] text-muted-foreground">本次操作</div>
              <p class="mt-1 text-xs leading-5 text-foreground">{{ item.operation_summary }}</p>
              <p class="mt-1 text-[11px] leading-5 text-muted-foreground">{{ item.strategy_reflection }}</p>
            </div>
            <div>
              <div class="text-[10px] text-muted-foreground">下一次复核条件</div>
              <p class="mt-1 text-xs leading-5 text-foreground">{{ item.next_review_condition }}</p>
              <div class="mt-1 font-mono text-[10px] text-muted-foreground">{{ item.evidence_refs.join(' · ') }}</div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="review.weekly_operation_review?.action_count" class="border-y border-border">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border py-3">
          <div>
            <h3 class="text-sm font-semibold text-foreground">五交易日周复盘</h3>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ review.weekly_operation_review.window_start }} 至 {{ review.weekly_operation_review.window_end }}
              · {{ review.weekly_operation_review.action_count }} 次操作
              · {{ review.weekly_operation_review.symbol_count }} 个标的
            </p>
          </div>
          <span class="text-[11px] text-muted-foreground">按标的合并 · 最多展开 3 个代表性标的</span>
        </div>
        <p class="py-3 text-sm leading-6 text-foreground">{{ review.weekly_operation_review.overall_reflection }}</p>
        <div class="divide-y divide-border border-t border-border">
          <article v-for="item in review.weekly_operation_review.items" :key="item.symbol" class="grid gap-3 py-3 md:grid-cols-[180px_minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <div class="font-medium text-foreground">{{ item.name }}</div>
              <div class="mt-1 font-mono text-xs text-muted-foreground">{{ item.symbol }}</div>
            </div>
            <div>
              <div class="text-[10px] text-muted-foreground">操作合并</div>
              <p class="mt-1 text-xs leading-5 text-foreground">{{ item.operation_summary }}</p>
              <p class="mt-1 text-[11px] leading-5 text-muted-foreground">{{ item.strategy_reflection }}</p>
            </div>
            <div>
              <div class="text-[10px] text-muted-foreground">下一次复核条件</div>
              <p class="mt-1 text-xs leading-5 text-foreground">{{ item.next_review_condition }}</p>
              <div class="mt-1 font-mono text-[10px] text-muted-foreground">{{ item.evidence_refs.join(' · ') }}</div>
            </div>
          </article>
        </div>
      </section>

      <div v-if="review.decision_focus?.length || review.changes_since_previous_review?.length" class="grid gap-4 lg:grid-cols-2">
        <section v-if="review.decision_focus?.length" class="border-y border-border">
          <div class="border-b border-border py-2 text-xs font-semibold text-foreground">今日决策焦点</div>
          <div class="divide-y divide-border">
            <div v-for="item in review.decision_focus" :key="`${item.subject}-${item.action}`" class="py-2 text-xs">
              <div class="flex items-center justify-between gap-2">
                <span class="font-medium text-foreground">{{ item.subject }}</span>
                <span :class="priorityClass(item.priority)">{{ item.action === 'no_action' ? '无需行动' : item.action }}</span>
              </div>
              <p class="mt-1 leading-5 text-muted-foreground">{{ item.reason }}</p>
            </div>
          </div>
        </section>
        <section v-if="review.changes_since_previous_review?.length" class="border-y border-border">
          <div class="border-b border-border py-2 text-xs font-semibold text-foreground">相比上一版</div>
          <div class="divide-y divide-border">
            <div v-for="item in review.changes_since_previous_review" :key="`${item.subject}-${item.change_type}`" class="py-2 text-xs">
              <div class="flex items-center justify-between gap-2">
                <span class="font-medium text-foreground">{{ item.subject }}</span>
                <span class="font-mono text-[10px] text-muted-foreground">{{ item.change_type }}</span>
              </div>
              <p class="mt-1 leading-5 text-muted-foreground">{{ item.summary }}</p>
            </div>
          </div>
        </section>
      </div>

      <div class="grid gap-4 xl:grid-cols-3">
        <div v-for="group in [
          { key: 'opportunities', title: '潜在机会', items: review.opportunities, tone: 'text-positive' },
          { key: 'risks', title: '风险审计', items: review.risks, tone: 'text-negative' },
          { key: 'watch', title: '继续观察', items: review.watch_items, tone: 'text-warning' },
        ]" :key="group.key" class="min-w-0">
          <div class="mb-2 flex items-center justify-between">
            <h3 :class="['text-sm font-semibold', group.tone]">{{ group.title }}</h3>
            <span class="font-mono text-xs text-muted-foreground">{{ group.items.length }}</span>
          </div>
          <div v-if="group.items.length" class="space-y-2">
            <article v-for="item in group.items" :key="item.item_id" class="rounded border border-border bg-card p-3">
              <div class="flex items-start justify-between gap-3">
                <h4 class="text-sm font-medium text-foreground">{{ item.subject }}</h4>
                <span :class="['shrink-0 rounded border px-1.5 py-0.5 text-[10px]', confidenceClass(item.confidence)]">
                  {{ confidenceLabel(item.confidence) }}
                </span>
              </div>
              <p class="mt-2 text-xs leading-5 text-muted-foreground">{{ item.conclusion }}</p>
              <div class="mt-3 border-t border-border/70 pt-2">
                <div class="text-[11px] font-medium text-foreground">行动语义</div>
                <p class="mt-1 text-xs leading-5 text-muted-foreground">{{ item.action_semantics }}</p>
              </div>
              <DecisionReasoning :item="item" />
              <div v-if="item.evidence_refs.length" class="mt-2 flex flex-wrap gap-1">
                <span v-for="evidence in item.evidence_refs" :key="evidence" class="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {{ evidence }}
                </span>
              </div>
              <details v-if="item.counter_evidence_refs.length || item.invalidation_conditions.length" class="mt-2 text-xs">
                <summary class="cursor-pointer text-muted-foreground hover:text-foreground">反证与失效条件</summary>
                <div class="mt-2 space-y-1 border-l border-border pl-2 text-muted-foreground">
                  <p v-if="item.counter_evidence_refs.length">反证：{{ item.counter_evidence_refs.join('、') }}</p>
                  <p v-for="condition in item.invalidation_conditions" :key="condition">{{ condition }}</p>
                </div>
              </details>
            </article>
          </div>
          <div v-else class="border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">暂无合格结论</div>
        </div>
      </div>

      <div>
        <div class="mb-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-foreground">复盘任务工作台</h3>
            <p class="mt-1 text-xs text-muted-foreground">
              白名单工具负责补证，DeepSeek 只在你主动更新复盘时读取新增结果。
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">
              待执行 {{ pendingTaskCount }} · 已取证 {{ completedTaskCount }}
            </span>
            <button
              class="h-8 rounded border border-border px-3 text-xs text-foreground hover:bg-secondary disabled:opacity-50"
              :disabled="batchLoading || pendingTaskCount === 0"
              @click="executeAllTasks"
            >
              {{ batchLoading ? '核查中…' : '执行自动核查' }}
            </button>
            <button
              class="h-8 rounded bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              :disabled="cycleLoading || (pendingTaskCount === 0 && completedTaskCount === 0)"
              @click="runReviewCycle"
            >
              {{ cycleLoading ? '正在更新复盘…' : '核查并更新复盘' }}
            </button>
          </div>
        </div>
        <div v-if="tasks.length" class="overflow-x-auto border border-border">
          <table class="w-full min-w-[920px] text-left text-xs">
            <thead class="bg-secondary/50 text-muted-foreground">
              <tr>
                <th class="px-3 py-2 font-medium">优先级</th>
                <th class="px-3 py-2 font-medium">对象与任务</th>
                <th class="px-3 py-2 font-medium">执行工具</th>
                <th class="px-3 py-2 font-medium">状态与结果</th>
                <th class="px-3 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr v-for="task in tasks" :key="task.task_id" class="bg-card align-top">
                <td :class="['px-3 py-3 font-medium', priorityClass(task.priority)]">{{ task.priority.toUpperCase() }}</td>
                <td class="max-w-[360px] px-3 py-3">
                  <div class="font-medium text-foreground">{{ task.subject }}</div>
                  <div class="mt-1 leading-5 text-muted-foreground">{{ task.task }}</div>
                  <div class="mt-1 text-[11px] text-muted-foreground/70">{{ task.reason }}</div>
                  <div v-if="task.coverage_gap" class="mt-1 text-[10px] leading-4 text-sky-300">
                    主动取证 · {{ task.coverage_gap.label || '覆盖缺口' }}
                    {{ task.coverage_gap.coverage_before_pct ?? '--' }}% → {{ task.coverage_gap.target_coverage_pct ?? '--' }}%
                    <span v-if="task.coverage_gap.account_weight_pct != null"> · 持仓权重 {{ task.coverage_gap.account_weight_pct }}%</span>
                  </div>
                  <div
                    v-if="task.target_symbols?.length || task.evidence_type"
                    class="mt-1 font-mono text-[10px] text-slate-400"
                  >
                    {{ task.evidence_type || 'manual' }}
                    <span v-if="task.target_symbols?.length"> · {{ task.target_symbols.join(', ') }}</span>
                  </div>
                  <div v-if="task.success_criteria" class="mt-1 text-[10px] leading-4 text-muted-foreground">
                    完成标准：{{ task.success_criteria }}
                  </div>
                </td>
                <td class="px-3 py-3">
                  <div class="text-foreground">{{ task.tool.label }}</div>
                  <div class="mt-1 font-mono text-[10px] text-muted-foreground">{{ task.tool.name }}</div>
                  <div v-if="task.tool.arguments.symbols?.length" class="mt-1 font-mono text-[11px] text-primary">
                    {{ task.tool.arguments.symbols.join(' / ') }}
                  </div>
                </td>
                <td class="max-w-[300px] px-3 py-3">
                  <span :class="['inline-flex rounded border px-1.5 py-0.5 text-[10px]', taskStatus(task.status).class]">
                    {{ taskStatus(task.status).label }}
                  </span>
                  <div v-if="task.result" class="mt-2 text-[11px] leading-5 text-muted-foreground">
                    证据 {{ task.result.evidence_ref }} · {{ formatTime(task.result.completed_at) }}
                  </div>
                  <div v-if="task.error" class="mt-2 text-[11px] leading-5 text-negative">{{ task.error }}</div>
                  <div v-if="task.next_retry_at" class="mt-1 text-[10px] text-warning">
                    {{ task.failure_category || '临时错误' }} · {{ formatTime(task.next_retry_at) }} 后重试
                    · {{ task.attempt_count }}/{{ task.max_attempts || 3 }}
                  </div>
                  <details v-if="task.result" class="mt-1">
                    <summary class="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">查看工具结果</summary>
                    <pre class="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-secondary/50 p-2 font-mono text-[10px] leading-4 text-muted-foreground">{{ JSON.stringify(task.result.payload, null, 2) }}</pre>
                  </details>
                </td>
                <td class="px-3 py-3 text-right">
                  <div class="flex justify-end gap-2">
                    <button
                      v-if="task.tool.auto_executable && ['pending', 'retry_wait', 'failed'].includes(task.status)"
                      class="h-7 rounded border border-border px-2 text-[11px] text-foreground hover:bg-secondary disabled:opacity-50"
                      :disabled="taskBusyId === task.task_id"
                      @click="executeOneTask(task)"
                    >
                      {{ taskBusyId === task.task_id ? '执行中…' : ['retry_wait', 'failed'].includes(task.status) ? '立即重试' : '执行' }}
                    </button>
                    <button
                      v-if="!['dismissed', 'completed', 'superseded'].includes(task.status)"
                      class="h-7 rounded px-2 text-[11px] text-muted-foreground hover:bg-secondary"
                      :disabled="taskBusyId === task.task_id"
                      @click="dismissTask(task)"
                    >
                      忽略
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">
          当前复盘没有生成核查任务
        </div>
      </div>

      <div v-if="outcomes" class="border-t border-border pt-4">
        <div class="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 class="text-sm font-semibold text-foreground">历史成效回顾</h3>
            <p class="mt-1 text-xs text-muted-foreground">固定规则评价建议与调仓结果，DeepSeek 不参与给自己打分。</p>
          </div>
          <div class="text-xs text-muted-foreground">
            建议 {{ outcomes.summary.recommendation_evaluated }}/{{ outcomes.summary.recommendation_count }} 已评价
            · 调仓 {{ outcomes.summary.action_evaluated }}/{{ outcomes.summary.action_count }} 已评价
            <span v-if="outcomes.summary.snapshot_change_count"> · 快照变化 {{ outcomes.summary.snapshot_change_count }}</span>
            <span v-if="outcomes.summary.action_candidates"> · 待确认候选 {{ outcomes.summary.action_candidates }}</span>
          </div>
        </div>
        <div v-if="outcomes.loop_health" class="mb-4 grid grid-cols-2 border-y border-border md:grid-cols-4">
          <div class="border-b border-r border-border px-3 py-3 md:border-b-0">
            <div class="text-[10px] text-muted-foreground">操作样本</div>
            <div class="mt-1 text-base font-semibold text-foreground">{{ outcomes.summary.action_count }}</div>
          </div>
          <div class="border-b border-border px-3 py-3 md:border-b-0 md:border-r">
            <div class="text-[10px] text-muted-foreground">策略上下文覆盖</div>
            <div class="mt-1 text-base font-semibold text-foreground">{{ formatMetric(outcomes.loop_health.strategy_context_coverage_pct) }}</div>
          </div>
          <div class="border-r border-border px-3 py-3">
            <div class="text-[10px] text-muted-foreground">直接建议匹配</div>
            <div class="mt-1 text-base font-semibold text-foreground">{{ formatMetric(outcomes.loop_health.direct_strategy_match_rate_pct) }}</div>
          </div>
          <div class="px-3 py-3">
            <div class="text-[10px] text-muted-foreground">到期评价覆盖</div>
            <div class="mt-1 text-base font-semibold text-foreground">{{ formatMetric(outcomes.loop_health.matured_evaluation_rate_pct) }}</div>
          </div>
        </div>
        <div v-if="sourceHealth.length" class="mb-4 border-y border-border">
          <div class="flex flex-wrap items-start justify-between gap-2 border-b border-border py-3">
            <div>
              <div class="text-xs font-semibold text-foreground">自主取证来源健康度</div>
              <p class="mt-1 text-xs text-muted-foreground">来源不稳定只会降低相关结论置信度，不会被误判为投资逻辑的反证。</p>
            </div>
            <span class="font-mono text-[10px] text-muted-foreground">按历史执行结果动态统计</span>
          </div>
          <div class="grid sm:grid-cols-2 xl:grid-cols-4">
            <div
              v-for="(source, index) in sourceHealth"
              :key="source.tool_name"
              class="px-3 py-3"
              :class="index < sourceHealth.length - 1 ? 'border-b border-border sm:border-b-0 sm:border-r' : ''"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-foreground">{{ sourceLabel(source.tool_name) }}</span>
                <span :class="(source.reliability_pct ?? 0) >= 80 ? 'text-positive' : (source.reliability_pct ?? 0) >= 50 ? 'text-warning' : 'text-negative'" class="font-mono text-xs">
                  {{ formatMetric(source.reliability_pct) }}
                </span>
              </div>
              <div class="mt-1 text-[10px] text-muted-foreground">
                {{ source.attempt_count }} 次取证 · 最近 {{ sourceStatusLabel(source.last_status) }}
              </div>
            </div>
          </div>
        </div>
        <div v-if="learningPolicies?.policies.length" class="mb-4 border-y border-border">
          <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border py-3">
            <div>
              <div class="text-xs font-semibold text-foreground">可验证学习规则</div>
              <p class="mt-1 text-xs text-muted-foreground">规则由历史结果的确定性门槛生成；模型负责应用和解释，不能自行改写。</p>
            </div>
            <span class="text-[11px] text-muted-foreground">生效 {{ activePolicies.length }} · 观察 {{ monitoringPolicies.length }}</span>
          </div>
          <div class="divide-y divide-border">
            <div v-for="policy in learningPolicies.policies" :key="policy.policy_id" class="grid gap-2 py-3 md:grid-cols-[180px_1fr_auto] md:items-start">
              <div>
                <div class="text-xs font-medium text-foreground">{{ policy.title }}</div>
                <div class="mt-1 font-mono text-[10px] text-muted-foreground">v{{ policy.version }} · {{ policy.confidence === 'high' ? '高置信' : policy.confidence === 'medium' ? '中置信' : '低置信' }}</div>
              </div>
              <div>
                <div class="text-xs leading-5 text-foreground">{{ policy.adjustment }}</div>
                <div class="mt-1 text-[10px] text-muted-foreground">样本 {{ policy.sample_count }} · 不利样本 {{ policy.adverse_count }} · 比例 {{ formatMetric(policy.adverse_rate_pct) }}</div>
              </div>
              <span
                class="w-fit rounded border px-2 py-1 text-[10px]"
                :class="policy.status === 'active' ? 'border-positive/30 bg-positive/10 text-positive' : 'border-border bg-secondary text-muted-foreground'"
              >
                {{ policy.status === 'active' ? '已生效' : '继续观察' }}
              </span>
            </div>
          </div>
          <div v-if="learningPolicies.boundary" class="border-t border-border py-2 text-[10px] text-muted-foreground">{{ learningPolicies.boundary }}</div>
        </div>
        <div v-if="outcomes.weekly_operations?.action_count" class="mb-4 border-y border-border">
          <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border py-3">
            <div>
              <div class="text-xs font-semibold text-foreground">本周操作合并事实</div>
              <p class="mt-1 text-xs text-muted-foreground">
                {{ outcomes.weekly_operations.window_start }} 至 {{ outcomes.weekly_operations.window_end }}
                · {{ outcomes.weekly_operations.action_count }} 次操作
                · {{ outcomes.weekly_operations.symbol_count }} 个标的
              </p>
            </div>
            <span class="font-mono text-[10px] text-muted-foreground">按标的合并 · 固定规则 · 不调用模型</span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[900px] text-left text-xs">
              <thead class="text-muted-foreground">
                <tr>
                  <th class="px-2 py-2 font-medium">标的</th>
                  <th class="px-2 py-2 font-medium">操作结构</th>
                  <th class="px-2 py-2 text-right font-medium">买入</th>
                  <th class="px-2 py-2 text-right font-medium">卖出</th>
                  <th class="px-2 py-2 text-right font-medium">净变化</th>
                  <th class="px-2 py-2 text-right font-medium">反向次数</th>
                  <th class="px-2 py-2 font-medium">当时策略</th>
                  <th class="px-2 py-2 text-right font-medium">临时超额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in outcomes.weekly_operations.items" :key="item.symbol" class="border-t border-border">
                  <td class="px-2 py-2">
                    <div class="font-medium text-foreground">{{ item.name }}</div>
                    <div class="mt-0.5 font-mono text-[10px] text-muted-foreground">{{ item.symbol }} · {{ item.operation_count }} 次</div>
                  </td>
                  <td class="px-2 py-2 text-foreground">{{ operationPatternLabel(item.pattern) }}</td>
                  <td class="px-2 py-2 text-right font-mono text-market-up">{{ formatQuantity(item.buy_quantity) }}</td>
                  <td class="px-2 py-2 text-right font-mono text-market-down">{{ formatQuantity(-item.sell_quantity) }}</td>
                  <td class="px-2 py-2 text-right font-mono" :class="item.net_quantity > 0 ? 'text-market-up' : item.net_quantity < 0 ? 'text-market-down' : 'text-muted-foreground'">{{ formatQuantity(item.net_quantity) }}</td>
                  <td class="px-2 py-2 text-right font-mono text-foreground">{{ item.reversal_count }}</td>
                  <td class="px-2 py-2 text-muted-foreground">
                    一致 {{ item.strategy_comparison_counts.aligned || 0 }}
                    · 冲突 {{ item.strategy_comparison_counts.conflicted || 0 }}
                    · 无直接建议 {{ item.strategy_comparison_counts.no_direct_recommendation || 0 }}
                  </td>
                  <td class="px-2 py-2 text-right font-mono text-muted-foreground">{{ formatMetric(item.provisional_market_result.excess_return_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="border-t border-border py-2 text-[11px] text-muted-foreground">{{ outcomes.weekly_operations.boundary }}</div>
        </div>
        <div v-if="monthlyReport" class="mb-4 border-y border-border">
          <div class="flex flex-wrap items-start justify-between gap-3 py-3">
            <div>
              <div class="text-xs font-semibold text-foreground">{{ monthlyReport.month }} 决策月报</div>
              <p class="mt-1 text-xs leading-5 text-muted-foreground">{{ monthlyReport.summary }}</p>
            </div>
            <span class="font-mono text-[10px] text-muted-foreground">规则评分 · 不调用模型</span>
          </div>
          <div class="grid grid-cols-2 border-t border-border md:grid-cols-4">
            <div class="border-b border-r border-border px-3 py-3 md:border-b-0">
              <div class="text-[10px] text-muted-foreground">到期建议</div>
              <div class="mt-1 text-base font-semibold text-foreground">{{ monthlyReport.recommendations.evaluated }}</div>
            </div>
            <div class="border-b border-border px-3 py-3 md:border-b-0 md:border-r">
              <div class="text-[10px] text-muted-foreground">建议支持率</div>
              <div class="mt-1 text-base font-semibold text-foreground">{{ formatMetric(monthlyReport.recommendations.support_rate_pct) }}</div>
            </div>
            <div class="border-r border-border px-3 py-3">
              <div class="text-[10px] text-muted-foreground">建议平均超额</div>
              <div class="mt-1 text-base font-semibold text-foreground">{{ formatMetric(monthlyReport.recommendations.average_excess_return_pct) }}</div>
            </div>
            <div class="px-3 py-3">
              <div class="text-[10px] text-muted-foreground">待确认调仓</div>
              <div class="mt-1 text-base font-semibold text-foreground">{{ monthlyReport.unconfirmed_action_count }}</div>
            </div>
          </div>
          <div v-if="monthlyReport.reason_categories.length" class="flex flex-wrap gap-2 border-t border-border py-2">
            <span v-for="reason in monthlyReport.reason_categories" :key="reason.key" class="text-[11px] text-muted-foreground">
              {{ reason.label }} {{ reason.count }}
            </span>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <div>
            <div class="mb-2 text-xs font-medium text-muted-foreground">建议台账</div>
            <div class="divide-y divide-border border border-border">
              <div v-for="item in outcomes.recommendations.slice(0, 8)" :key="item.recommendation_id" class="bg-card px-3 py-2 text-xs">
                <div class="flex items-start justify-between gap-2">
                  <span class="font-medium text-foreground">{{ item.subject }}</span>
                  <div class="flex shrink-0 items-center gap-2">
                    <span class="text-[10px] text-muted-foreground">{{ lifecycleLabel(item.lifecycle?.state || item.status) }}</span>
                    <span :class="verdictClass(item.outcome?.verdict)">{{ verdictLabel(item.outcome?.verdict) }}</span>
                  </div>
                </div>
                <p class="mt-1 line-clamp-2 leading-5 text-muted-foreground">{{ item.outcome?.reason || item.conclusion }}</p>
                <div v-if="item.outcome?.decision_quality?.assessment" class="mt-1 font-mono text-[10px] text-muted-foreground">
                  {{ item.outcome.decision_quality.assessment }}
                </div>
                <div class="mt-1 font-mono text-[10px] text-muted-foreground">{{ item.target_symbols.join(' / ') || '无可评价标的' }}</div>
                <details v-if="item.decision_snapshot" class="mt-2">
                  <summary class="cursor-pointer text-[11px] text-primary">查看当时证据与失效条件</summary>
                  <div class="mt-2 space-y-1 border-l border-border pl-2 text-[11px] leading-5 text-muted-foreground">
                    <div v-if="item.decision_snapshot.notice" class="text-warning">{{ item.decision_snapshot.notice }}</div>
                    <div>模型：{{ item.decision_snapshot.model || '--' }} · 证据 {{ item.decision_snapshot.evidence.length }} 条</div>
                    <div v-if="item.decision_snapshot.action_semantics">行动语义：{{ item.decision_snapshot.action_semantics }}</div>
                    <div v-if="item.decision_snapshot.invalidation_conditions.length">
                      失效条件：{{ item.decision_snapshot.invalidation_conditions.join('；') }}
                    </div>
                  </div>
                </details>
              </div>
              <div v-if="!outcomes.recommendations.length" class="px-3 py-8 text-center text-xs text-muted-foreground">等待新复盘建议进入台账</div>
            </div>
          </div>
          <div>
            <div class="mb-2 text-xs font-medium text-muted-foreground">持仓变化台账</div>
            <div class="max-h-[420px] divide-y divide-border overflow-auto border border-border">
              <div v-for="action in outcomes.portfolio_actions.slice(0, 12)" :key="action.action_id" class="bg-card px-3 py-2 text-xs">
                <div class="flex items-start justify-between gap-2">
                  <span class="font-medium text-foreground">{{ action.name || action.symbol }} · {{ action.action_type }}</span>
                  <span :class="verdictClass(action.outcome?.verdict)">{{ verdictLabel(action.outcome?.verdict) }}</span>
                </div>
                <div class="mt-1 text-muted-foreground">
                  {{ action.quantity_before ?? '--' }} → {{ action.quantity_after ?? '--' }} · {{ formatTime(action.snapshot_time) }}
                </div>
                <div
                  class="mt-1 text-[11px]"
                  :class="strategyClass(action.ai_strategy_comparison?.status)"
                >
                  {{ strategyLabel(action.ai_strategy_comparison?.status) }}
                  <span v-if="action.ai_strategy_comparison?.matched_recommendations?.length">
                    · {{ action.ai_strategy_comparison.matched_recommendations.map((item) => item.subject).filter(Boolean).join('、') }}
                  </span>
                </div>
                <p v-if="action.outcome" class="mt-1 leading-5 text-muted-foreground">{{ action.outcome.reason }}</p>
                <div v-if="action.outcome?.decision_quality?.assessment" class="mt-1 font-mono text-[10px] text-muted-foreground">
                  {{ action.outcome.decision_quality.assessment }}
                </div>
                <div v-if="action.outcome?.attribution" class="mt-2 border-l border-border pl-2 text-[11px] leading-5 text-muted-foreground">
                  <div>{{ attributionPathLabel(action.outcome.attribution.path_interpretation) }}</div>
                  <div>
                    估算仓位贡献 {{ formatMoney(action.outcome.attribution.estimated_position_effect_pnl) }} 元
                    · 相对基准贡献 {{ formatMoney(action.outcome.attribution.estimated_benchmark_adjusted_pnl) }} 元
                  </div>
                  <div v-if="action.outcome.attribution.reason_capture === 'missing'" class="text-warning">本次操作未记录理由，只作为低置信度学习样本。</div>
                </div>
                <div v-if="!action.user_confirmed" class="mt-2 flex gap-2">
                  <input v-model="actionReasons[action.action_id]" placeholder="补充本次调仓原因" class="h-7 min-w-0 flex-1 rounded border border-border bg-background px-2 text-foreground" />
                  <button class="h-7 rounded border border-border px-2 text-foreground hover:bg-secondary disabled:opacity-50" :disabled="outcomeBusyId === action.action_id" @click="confirmAction(action.action_id)">确认记录</button>
                  <button class="h-7 rounded border border-border px-2 text-muted-foreground hover:bg-secondary disabled:opacity-50" :disabled="outcomeBusyId === action.action_id" @click="dismissAction(action.action_id)">忽略</button>
                </div>
                <div v-else class="mt-1 text-[11px] text-positive">用户已确认<span v-if="action.user_reason"> · {{ action.user_reason }}</span></div>
              </div>
              <div v-if="!outcomes.portfolio_actions.length" class="px-3 py-8 text-center text-xs text-muted-foreground">尚未识别到持仓数量变化</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else-if="!initialLoading && !error" class="border border-dashed border-border py-16 text-center">
      <h2 class="text-base font-medium text-foreground">尚未生成复盘</h2>
      <p class="mt-2 text-sm text-muted-foreground">点击“生成今日复盘”，DeepSeek 将读取当前证据快照并完成第一次结构化复盘。</p>
    </div>

    <div v-if="history.length" class="border-t border-border pt-3">
      <div class="mb-2 text-xs font-medium text-muted-foreground">最近运行</div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="run in history"
          :key="run.run_id"
          :class="[
            'rounded border px-2 py-1 text-[11px]',
            run.status === 'completed' ? 'border-border text-muted-foreground' : 'border-negative/30 text-negative',
          ]"
          :title="run.error || run.run_id"
        >
          {{ formatTime(run.completed_at) }} · {{ run.model }} · {{ run.status === 'completed' ? '完成' : '失败' }}
        </span>
      </div>
    </div>
  </section>
</template>
  type AgentAutomationSettings,
  type AgentAutomationStatus,
  type AgentOutcomes,
