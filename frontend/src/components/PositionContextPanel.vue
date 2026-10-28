<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getPortfolioDashboard, type PortfolioDashboard } from '../api/client'

const props = defineProps<{
  symbol: string
  decisionContext?: Record<string, any> | null
  refreshKey?: number
}>()
const emit = defineEmits<{
  (event: 'verify-disclosure', symbol: string): void
}>()

const dashboard = ref<PortfolioDashboard | null>(null)
const loading = ref(false)
const error = ref('')

const compactSymbol = (symbol: string) => symbol.split('.', 1)[0].padStart(6, '0')
const fmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}
const scoreTone = (score?: number | null) => {
  const value = Number(score)
  if (!Number.isFinite(value)) return 'text-muted-foreground'
  if (value >= 75) return 'text-positive'
  if (value >= 55) return 'text-sky-200'
  return 'text-warning'
}
const actionTone = (action?: string) => {
  if (String(action || '').includes('减')) return 'border-negative/50 bg-negative/10 text-negative'
  if (String(action || '').includes('增') || String(action || '').includes('候选')) return 'border-positive/50 bg-positive/10 text-positive'
  return 'border-sky-400/50 bg-sky-400/10 text-sky-100'
}

const load = async () => {
  if (!props.symbol) return
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await getPortfolioDashboard()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '组合决策上下文加载失败'
  } finally {
    loading.value = false
  }
}

const position = computed(() => {
  const key = compactSymbol(props.symbol)
  return (dashboard.value?.positions || []).find((item: any) => compactSymbol(item.symbol) === key)
})
const decision = computed(() => {
  const context = props.decisionContext
  if (context && compactSymbol(context.symbol) === compactSymbol(props.symbol)) return context
  return null
})
const presentationPosition = computed(() => decision.value || position.value)
const attractiveness = computed(() => decision.value?.attractiveness || position.value?.attractiveness || {})
const health = computed(() => {
  const snapshot = decision.value?.health
  if (!snapshot) return null
  const latest = (position.value as Record<string, any> | undefined)?.announcement_verification || {}
  if (latest.status !== 'verified' || snapshot.verification?.status === 'verified') return snapshot

  const supportedCount = (latest.items || []).filter((item: any) => item.status === 'supported').length
  const partialCount = (latest.items || []).filter((item: any) => item.status === 'partially_supported').length
  const contradictedCount = (latest.items || []).filter((item: any) => item.status === 'contradicted').length
  const gain = Math.min(30, supportedCount * 10 + partialCount * 5)
  const dimensions = (snapshot.dimensions || []).map((item: any) => {
    if (item.key !== 'thesis') return item
    const reasons = (item.coverageReasons || [])
      .filter((reason: string) => !reason.startsWith('公告正文尚未核验'))
    reasons.push(`公告正文核验：+${gain}%（支持 ${supportedCount}，部分支持 ${partialCount}，反证 ${contradictedCount}）`)
    return { ...item, coverage: Math.min(100, Number(item.coverage || 0) + gain), coverageReasons: reasons }
  })
  const coverage = Math.round(dimensions.reduce(
    (total: number, item: any) => total + Number(item.coverage || 0) * Number(item.weight || 0) / 100,
    0,
  ))
  return {
    ...snapshot,
    coverage,
    dimensions,
    verification: {
      status: latest.status,
      supportedCount,
      partialCount,
      contradictedCount,
      documents: latest.documents || [],
      summary: latest.overall_summary || '',
    },
  }
})
const conclusion = computed(() => decision.value?.conclusion || null)
const healthDimensions = computed(() => health.value?.dimensions || [])
const attractivenessDimensions = computed(() => attractiveness.value?.dimensions || [])
const confidenceReasons = computed(() => conclusion.value?.confidenceReasons || [])
const confidenceCalculation = computed(() => conclusion.value?.confidenceCalculation || null)
const constraints = computed(() => attractiveness.value?.account_constraints || {})
const verification = computed(() => health.value?.verification || {})
const aiClassification = computed(() => (presentationPosition.value as Record<string, any> | undefined)?.ai_direction_classification || {})
const relatedEvents = computed(() => {
  const key = compactSymbol(props.symbol)
  return (dashboard.value?.market_event_radar?.events || []).filter((event: any) =>
    (event.related_positions || []).some((item: any) => compactSymbol(item.symbol) === key),
  ).slice(0, 3)
})
const researchMode = computed(() => !decision.value)
const fallbackChangeCondition = computed(() => {
  const row = position.value as Record<string, any> | undefined
  return row?.invalid_condition || row?.open_questions?.[0] || '补齐趋势、公告或催化相关的可追溯事实后重新评估。'
})

watch(() => [props.symbol, props.decisionContext, props.refreshKey], load, { immediate: true })
</script>

<template>
  <section class="border border-border bg-card">
    <header class="border-b border-border px-4 py-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-xs text-muted-foreground">账户决策展开</div>
          <h2 class="mt-1 text-base font-semibold text-foreground">{{ presentationPosition?.name || symbol }} · 持仓决策上下文</h2>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ researchMode ? '当前从个股研究进入，尚未携带驾驶舱决策快照；账户指标仅作辅助参考。' : '以下结论与驾驶舱同源，用于解释行动语义、评分、证据和改变条件。' }}
          </p>
        </div>
        <span v-if="conclusion" :class="['rounded border px-2.5 py-1 text-sm font-semibold', conclusion.tone || actionTone(conclusion.action)]">
          {{ conclusion.action }}
        </span>
      </div>
    </header>

    <div v-if="loading" class="p-4 text-sm text-muted-foreground">正在同步账户决策快照...</div>
    <div v-else-if="error" class="p-4 text-sm text-warning">{{ error }}</div>
    <div v-else class="space-y-4 p-4">
      <div v-if="conclusion" :class="['border p-3', conclusion.tone || actionTone(conclusion.action)]">
        <div class="text-xs opacity-80">当前行动语义 · {{ conclusion.status }}</div>
        <div class="mt-1 text-base font-semibold">{{ conclusion.summary }}</div>
        <div class="mt-2 text-sm leading-6">{{ conclusion.reasons?.[0] }}</div>
      </div>
      <div v-else class="border border-sky-400/30 bg-sky-400/5 p-3 text-sm text-slate-200">
        此标的尚未从驾驶舱打开。可先查看趋势、基本事实和吸引力维度；纳入持仓或观察池后会形成账户行动语义。
      </div>

      <div class="grid gap-px border border-border bg-border sm:grid-cols-2 xl:grid-cols-5">
        <div class="bg-card p-3">
          <div class="text-xs text-muted-foreground">健康度</div>
          <div :class="['mt-1 font-mono text-2xl font-semibold', scoreTone(health?.score)]">{{ health?.score ?? '-' }}</div>
          <div class="mt-1 text-xs text-muted-foreground">覆盖 {{ health?.coverage ?? '-' }}%</div>
        </div>
        <div class="bg-card p-3">
          <div class="text-xs text-muted-foreground">吸引力</div>
          <div :class="['mt-1 font-mono text-2xl font-semibold', scoreTone(attractiveness.score)]">{{ attractiveness.score ?? '-' }}</div>
          <div class="mt-1 text-xs text-muted-foreground">事实覆盖 {{ attractiveness.coverage ?? '-' }}%</div>
        </div>
        <div class="bg-card p-3">
          <div class="text-xs text-muted-foreground">账户准备度</div>
          <div :class="['mt-1 font-mono text-2xl font-semibold', scoreTone(attractiveness.account_readiness_score)]">{{ attractiveness.account_readiness_score ?? '-' }}</div>
          <div class="mt-1 text-xs text-muted-foreground">是否还有新增敞口空间</div>
        </div>
        <div class="bg-card p-3">
          <div class="text-xs text-muted-foreground">结论置信度</div>
          <div class="mt-1 text-2xl font-semibold text-foreground">{{ conclusion?.confidence || attractiveness.confidence || '-' }}</div>
          <div class="mt-1 text-xs text-muted-foreground">联合覆盖 {{ conclusion?.jointCoverage ?? '-' }}%</div>
        </div>
        <div class="bg-card p-3">
          <div class="text-xs text-muted-foreground">账户持仓权重</div>
          <div class="mt-1 font-mono text-2xl font-semibold text-foreground">{{ fmt(presentationPosition?.portfolio_weight_pct, '%') }}</div>
          <div class="mt-1 text-xs text-muted-foreground">用于账户风险与优先级判断</div>
        </div>
      </div>

      <div class="grid gap-3 xl:grid-cols-2">
        <div class="border border-border">
          <div class="border-b border-border px-3 py-2">
            <h3 class="text-sm font-semibold text-foreground">健康度拆解</h3>
            <p class="mt-1 text-xs text-muted-foreground">持仓逻辑、趋势、仓位集中度与事件环境。</p>
          </div>
          <div v-if="healthDimensions.length" class="divide-y divide-border/60">
            <div v-for="item in healthDimensions" :key="item.key" class="p-3">
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm text-foreground">{{ item.label }} · {{ item.weight > 0 ? `权重 ${item.weight}%` : '仅供参考，不计权重' }}</span>
                <span :class="['font-mono text-sm font-semibold', scoreTone(item.score)]">{{ item.score }}/100</span>
              </div>
              <div class="mt-1 text-xs text-muted-foreground">证据覆盖 {{ item.coverage }}%</div>
              <div v-if="item.coverageReasons?.length" class="mt-2 space-y-1 text-xs leading-5 text-muted-foreground">
                <div v-for="reason in item.coverageReasons" :key="reason">{{ reason }}</div>
              </div>
              <div v-if="item.autoEvidence" class="mt-2 border-t border-border/60 pt-2 text-xs leading-5 text-sky-200">
                <div>{{ item.autoEvidence.message }}</div>
                <button
                  v-if="item.autoEvidence.index_refreshable"
                  class="mt-2 border border-sky-400/50 px-2 py-1 text-xs font-medium text-sky-200 hover:bg-sky-400/10"
                  @click="emit('verify-disclosure', symbol)"
                >
                  核验公告正文
                </button>
              </div>
            </div>
          </div>
          <div v-else class="p-3 text-xs text-muted-foreground">从驾驶舱点击“重点持仓动作”后可显示同源健康度拆解。</div>
        </div>

        <div class="border border-border">
          <div class="border-b border-border px-3 py-2">
            <h3 class="text-sm font-semibold text-foreground">吸引力拆解</h3>
            <p class="mt-1 text-xs text-muted-foreground">新增风险敞口的证据、趋势、价格位置、催化与执行条件。</p>
          </div>
          <div v-if="attractivenessDimensions.length" class="divide-y divide-border/60">
            <div v-for="item in attractivenessDimensions" :key="item.key" class="p-3">
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm text-foreground">{{ item.label }} · 权重 {{ item.weight }}%</span>
                <span :class="['font-mono text-sm font-semibold', scoreTone(item.score)]">{{ item.score ?? '缺数据' }}<span v-if="item.score !== null && item.score !== undefined">/100</span></span>
              </div>
              <div class="mt-1 text-xs text-muted-foreground">事实覆盖 {{ item.coverage ?? 0 }}% · {{ item.reasons?.[0] || '等待补齐可追溯事实。' }}</div>
              <div v-if="item.components?.length" class="mt-2 flex flex-wrap gap-1.5">
                <span v-for="component in item.components" :key="component.label" class="border border-border/80 bg-secondary/30 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {{ component.label }} {{ component.score }}/100
                </span>
              </div>
              <div v-if="item.reasons?.length > 1" class="mt-2 space-y-1 text-xs leading-5 text-muted-foreground">
                <div v-for="reason in item.reasons.slice(1)" :key="reason">{{ reason }}</div>
              </div>
            </div>
          </div>
          <div v-else class="p-3 text-xs text-muted-foreground">当前没有可用的吸引力维度。</div>
        </div>
      </div>

      <div v-if="aiClassification.symbol" class="border border-sky-400/30 bg-sky-400/5 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-sm font-semibold text-foreground">AI 关联方向</div>
          <div class="text-xs text-sky-200">置信度 {{ Math.round(Number(aiClassification.confidence || 0) * 100) }}%</div>
        </div>
        <div class="mt-2 text-sm text-foreground">
          {{ (aiClassification.directions || []).join(' / ') || '待分类' }}
          <span v-if="aiClassification.theme_ids?.length" class="text-muted-foreground"> · {{ aiClassification.theme_ids.join(' / ') }}</span>
        </div>
        <div class="mt-2 text-xs leading-5 text-muted-foreground">{{ aiClassification.reason }}</div>
        <div v-if="aiClassification.evidence_basis?.length" class="mt-2 text-xs text-sky-200">依据：{{ aiClassification.evidence_basis.join('、') }}</div>
        <div class="mt-2 text-xs text-warning">此分类只用于主题关联与研究优先级；公告索引不等于公告正文核验，不能单独证明经营 Thesis。</div>
      </div>

      <div class="grid gap-3 xl:grid-cols-2">
        <div class="border border-border p-3">
          <div class="text-xs text-muted-foreground">结论置信度拆解</div>
          <div v-if="confidenceCalculation" class="mt-2 space-y-1 text-sm text-foreground">
            <div>基础联合覆盖：min(健康 {{ confidenceCalculation.health_coverage_pct }}%，吸引力 {{ confidenceCalculation.attractiveness_coverage_pct }}%) = {{ confidenceCalculation.base_joint_coverage_pct }}%</div>
            <div v-if="confidenceCalculation.thesis_gate_applied" class="text-warning">关键门槛：Thesis 覆盖 {{ confidenceCalculation.thesis_coverage_pct }}%，因此置信度上限为中低。</div>
            <div v-else class="text-muted-foreground">关键门槛：未触发 Thesis 证据上限。</div>
            <div v-if="confidenceCalculation.verified_conflict" class="text-warning">已检测到同一命题的支持与反证，需要优先复核。</div>
            <div v-else class="text-muted-foreground">价格位置、趋势和执行条件的分数差异属于行动权衡，不再被误判为证据冲突。</div>
          </div>
          <div v-if="confidenceReasons.length" class="mt-2 space-y-1 text-sm text-warning">
            <div v-for="reason in confidenceReasons" :key="reason">{{ reason }}</div>
          </div>
          <div v-else class="mt-2 text-sm text-muted-foreground">当前未发现额外的置信度限制。</div>
          <div v-if="constraints.blockers?.length" class="mt-3 border-t border-border pt-3 text-sm text-warning">账户约束：{{ constraints.blockers.join('；') }}</div>
          <div v-if="attractiveness.opportunity_cost?.dominated_by_symbol" class="mt-3 text-sm text-warning">
            同主题机会成本：优先级低于 {{ attractiveness.opportunity_cost.dominated_by_name || attractiveness.opportunity_cost.dominated_by_symbol }}，差 {{ fmt(attractiveness.opportunity_cost.priority_gap) }} 分。
          </div>
        </div>
        <div class="border border-border p-3">
          <div class="text-xs text-muted-foreground">下一步验证与改变条件</div>
          <div class="mt-2 text-sm leading-6 text-foreground">{{ conclusion?.change || fallbackChangeCondition }}</div>
          <div v-if="verification.status === 'verified'" class="mt-3 text-xs text-muted-foreground">公告验证：支持 {{ verification.supportedCount }} · 部分支持 {{ verification.partialCount }} · 反证 {{ verification.contradictedCount }}</div>
          <div v-if="relatedEvents.length" class="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">相关事件：{{ relatedEvents.map((event: any) => `${event.title}（${event.days_until}天）`).join('；') }}</div>
        </div>
      </div>
    </div>
  </section>
</template>
