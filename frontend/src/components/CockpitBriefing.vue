<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getAgentMonthlyReport,
  getAgentAutomationStatus,
  getAgentOutcomes,
  getAgentReviewTasks,
  getLatestAgentReview,
  getRotationSummary,
  type AgentMonthlyReport,
  type AgentAutomationStatus,
  type AgentOutcomes,
  type AgentReviewRun,
  type AgentReviewTask,
  type RotationSector,
  type RotationSummary,
} from '../api/client'

const emit = defineEmits<{
  (event: 'open-review'): void
  (event: 'open-rotation'): void
  (event: 'open-import', kind: 'current_holdings' | 'trade_history'): void
  (event: 'select-symbol', symbol: string): void
}>()

const loading = ref(false)
const error = ref('')
const latest = ref<AgentReviewRun | null>(null)
const tasks = ref<AgentReviewTask[]>([])
const outcomes = ref<AgentOutcomes | null>(null)
const monthly = ref<AgentMonthlyReport | null>(null)
const rotation = ref<RotationSummary | null>(null)
const automation = ref<AgentAutomationStatus | null>(null)

const pendingTasks = computed(() =>
  tasks.value.filter((task) => ['pending', 'failed', 'manual_required'].includes(task.status)),
)

const reviewSignals = computed(() => ({
  opportunities: latest.value?.review?.opportunities?.length || 0,
  risks: latest.value?.review?.risks?.length || 0,
  watch: latest.value?.review?.watch_items?.length || 0,
}))

const reviewOrigin = computed(() => {
  const runId = latest.value?.run_id
  const automationRun = automation.value?.latest_run
  const belongsToLatestCycle = Boolean(
    runId
    && automationRun?.steps?.some((step) => step.run_id === runId),
  )
  if (!belongsToLatestCycle) return '最新 AI 复盘'
  return automationRun?.trigger === 'scheduled' ? '收盘自动复盘' : '手动复盘'
})

const opportunityRows = computed(() => {
  const ordered = [
    ...(rotation.value?.potential_opportunities || []),
    ...(rotation.value?.early_turning || []),
    ...(rotation.value?.wait_pullback || []),
  ]
  const seen = new Set<string>()
  return ordered
    .filter((row) => {
      if (seen.has(row.sector_id)) return false
      seen.add(row.sector_id)
      return true
    })
    .slice(0, 3)
})

const load = async () => {
  loading.value = true
  error.value = ''
  const results = await Promise.allSettled([
    getLatestAgentReview(),
    getAgentReviewTasks(),
    getAgentOutcomes(),
    getAgentMonthlyReport(),
    getRotationSummary(),
    getAgentAutomationStatus(),
  ])
  if (results[0].status === 'fulfilled') latest.value = results[0].value
  if (results[1].status === 'fulfilled') tasks.value = results[1].value
  if (results[2].status === 'fulfilled') outcomes.value = results[2].value
  if (results[3].status === 'fulfilled') monthly.value = results[3].value
  if (results[4].status === 'fulfilled') rotation.value = results[4].value
  if (results[5].status === 'fulfilled') automation.value = results[5].value
  const failedCount = results.filter((item) => item.status === 'rejected').length
  if (failedCount) error.value = `${failedCount} 项摘要暂时不可用，已保留其余结果。`
  loading.value = false
}

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

const formatPct = (value?: number | null) =>
  value === null || value === undefined ? '--' : `${Number(value).toFixed(1)}%`

const stageTone = (stage?: string) => ({
  potential_opportunity: 'text-positive',
  early_turning: 'text-sky-300',
  wait_pullback: 'text-warning',
}[stage || ''] || 'text-muted-foreground')

const stageLabel = (row: RotationSector) => row.action_label || ({
  potential_opportunity: '潜在机会',
  early_turning: '早期转强',
  wait_pullback: '强势但等回踩',
}[row.opportunity_stage || ''] || '观察')

const proxySymbols = (row: RotationSector) => {
  if (row.proxy_type === 'synthetic') return row.proxy_components || []
  const symbol = row.selected_symbol || row.primary_symbol
  return symbol ? [{ symbol, name: row.proxy_meta?.name || '' }] : []
}

const proxyLabel = (proxy: { symbol: string; name?: string }) => {
  const name = String(proxy.name || '').trim()
  return !name || name === proxy.symbol ? proxy.symbol : `${name} ${proxy.symbol}`
}

onMounted(load)
</script>

<template>
  <section class="overflow-hidden rounded-lg border border-border bg-card">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
      <div>
        <div class="text-sm font-semibold text-foreground">AI 决策摘要</div>
        <div class="mt-1 text-xs text-muted-foreground">建议、待办、结果验证与市场机会集中在这里。</div>
      </div>
      <div class="flex flex-wrap gap-2 text-xs">
        <button class="h-8 rounded border border-border px-3 text-foreground hover:bg-secondary" @click="emit('open-import', 'current_holdings')">
          更新持仓
        </button>
        <button class="h-8 rounded border border-border px-3 text-foreground hover:bg-secondary" @click="emit('open-import', 'trade_history')">
          记录交易
        </button>
        <button class="h-8 rounded bg-secondary px-3 text-foreground hover:bg-secondary/80" :disabled="loading" @click="load">
          {{ loading ? '读取中...' : '刷新摘要' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="border-b border-warning/30 bg-warning/10 px-4 py-2 text-xs text-warning">{{ error }}</div>

    <div class="grid lg:grid-cols-2">
      <div class="border-b border-border p-4 lg:border-b-0 lg:border-r">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs text-muted-foreground">{{ reviewOrigin }} · 上一次复盘 {{ formatTime(latest?.completed_at) }}</div>
            <h2 class="mt-1 text-base font-semibold text-foreground">
              {{ latest?.review?.headline || '尚未生成可用复盘' }}
            </h2>
          </div>
          <button class="shrink-0 text-xs font-medium text-sky-300 hover:text-sky-200 hover:underline" @click="emit('open-review')">完整复盘</button>
        </div>

        <p class="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
          {{ latest?.review?.summary || '自动复盘生成后，会在这里呈现最重要的账户判断。' }}
        </p>

        <div class="mt-4 grid grid-cols-4 divide-x divide-border border-y border-border py-3 text-center text-xs">
          <div>
            <div class="font-mono text-base text-positive">{{ reviewSignals.opportunities }}</div>
            <div class="mt-1 text-muted-foreground">机会</div>
          </div>
          <div>
            <div class="font-mono text-base text-negative">{{ reviewSignals.risks }}</div>
            <div class="mt-1 text-muted-foreground">风险</div>
          </div>
          <div>
            <div class="font-mono text-base text-warning">{{ pendingTasks.length }}</div>
            <div class="mt-1 text-muted-foreground">待处理</div>
          </div>
          <div>
            <div class="font-mono text-base text-foreground">{{ outcomes?.summary.recommendation_evaluated || 0 }}</div>
            <div class="mt-1 text-muted-foreground">已验证</div>
          </div>
        </div>

        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span class="text-muted-foreground">
            {{ monthly?.month || '本月' }}建议验证支持率
            <strong class="ml-1 font-mono font-medium text-foreground">{{ formatPct(monthly?.recommendations.support_rate_pct) }}</strong>
          </span>
          <span v-if="pendingTasks[0]" class="max-w-full truncate text-warning">
            下一项：{{ pendingTasks[0].subject }} · {{ pendingTasks[0].task }}
          </span>
        </div>
      </div>

      <div class="p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs text-muted-foreground">轮动机会 Top 3 · 截至 {{ rotation?.as_of || '--' }}</div>
            <h2 class="mt-1 text-base font-semibold text-foreground">值得继续核查的方向</h2>
          </div>
          <button class="shrink-0 text-xs font-medium text-sky-300 hover:text-sky-200 hover:underline" @click="emit('open-rotation')">完整雷达</button>
        </div>

        <div v-if="opportunityRows.length" class="mt-3 divide-y divide-border border-y border-border">
          <div v-for="row in opportunityRows" :key="row.sector_id" class="py-3">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <span class="font-medium text-foreground">{{ row.name }}</span>
                <span :class="['ml-2 text-xs', stageTone(row.opportunity_stage)]">{{ stageLabel(row) }}</span>
              </div>
              <span
                class="shrink-0 font-mono text-xs text-slate-200"
                title="机会分：轮动模型综合趋势、相对沪深300表现、量能和追高风险后的0-100分，用于排序，不代表预期收益率。"
              >
                机会分 {{ row.score.total.toFixed(1) }}/100
              </span>
            </div>
            <p class="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{{ row.opportunity_reason || '等待更多趋势与资金证据。' }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="proxy in proxySymbols(row)"
                :key="proxy.symbol"
                class="text-xs font-medium text-sky-300 hover:text-sky-200 hover:underline"
                @click="emit('select-symbol', proxy.symbol)"
              >
                {{ proxyLabel(proxy) }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="mt-3 border-y border-border py-6 text-center text-xs text-muted-foreground">
          当前没有进入前三的候选方向。
        </div>
      </div>
    </div>
  </section>
</template>
