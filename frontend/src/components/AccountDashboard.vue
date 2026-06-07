<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  createPortfolioAnalysisPacket,
  getPortfolioDashboard,
  getPortfolio,
  type PortfolioDashboard,
  type PortfolioPosition,
  type PortfolioState,
} from '../api/client'

const emit = defineEmits<{
  (event: 'select-symbol', symbol: string): void
}>()

const loading = ref(false)
const contextLoading = ref(false)
const packetLoading = ref(false)
const error = ref('')
const notice = ref('')
const state = ref<PortfolioState | null>(null)
const dashboard = ref<PortfolioDashboard | null>(null)
const packetMarkdown = ref('')
const marketValueSort = ref<'desc' | 'asc'>('desc')

const fmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const signedFmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const prefix = Number(value) > 0 ? '+' : ''
  return `${prefix}${fmt(value, suffix)}`
}

const compactSymbol = (symbol: string) => symbol.split('.', 1)[0].padStart(6, '0')
const activeHoldings = computed(() => (state.value?.snapshot.positions || []).filter((item) => Number(item.quantity || 0) > 0))
const watchlist = computed(() => (state.value?.snapshot.positions || []).filter((item) => Number(item.quantity || 0) === 0))
const holdings = computed(() => dashboard.value?.positions || [...activeHoldings.value, ...watchlist.value])
const sortByMarketValue = <T extends { market_value?: number | null; quantity?: number | null }>(items: T[]) =>
  [...items].sort((a, b) => {
    const diff = Number(b.market_value || 0) - Number(a.market_value || 0)
    return marketValueSort.value === 'desc' ? diff : -diff
  })
const activePool = computed(() => sortByMarketValue(holdings.value.filter((item) => Number(item.quantity || 0) > 0)))
const watchPool = computed(() => sortByMarketValue(holdings.value.filter((item) => Number(item.quantity || 0) === 0)))
const account = computed(() => dashboard.value?.account_facts || state.value?.metrics || {})
const weightBySymbol = computed(() => {
  const map = new Map<string, number>()
  for (const item of state.value?.metrics.position_weights || []) {
    if (item?.symbol) map.set(compactSymbol(item.symbol), Number(item.weight_pct || 0))
  }
  for (const item of dashboard.value?.positions || []) {
    if (item?.symbol && item.portfolio_weight_pct !== null && item.portfolio_weight_pct !== undefined) {
      map.set(compactSymbol(item.symbol), Number(item.portfolio_weight_pct || 0))
    }
  }
  return map
})
const trendBySymbol = computed(() => {
  const map = new Map<string, Record<string, any>>()
  for (const item of dashboard.value?.positions || []) {
    if (item?.symbol) map.set(compactSymbol(item.symbol), item.trend || {})
  }
  return map
})

const primaryGroups = computed(() => dashboard.value?.primary_direction_grouping || state.value?.metrics.primary_theme_exposures || [])
const riskGroups = computed(() => {
  const fromContext = dashboard.value?.risk_observations?.risk_observations
  return fromContext || state.value?.metrics.risk_tag_exposures || []
})
const dataGaps = computed(() => dashboard.value?.data_gaps || state.value?.metrics.missing_data || [])
const eventRadar = computed(() => dashboard.value?.market_event_radar)
const marketEvents = computed(() => eventRadar.value?.events || [])
const nextMarketEvent = computed(() => eventRadar.value?.next_event)
const strategyRows = computed(() => dashboard.value?.strategy_matrix || [])
const decisionRows = computed<Array<Record<string, any>>>(() => {
  const positionMap = new Map(holdings.value.map((item) => [compactSymbol(item.symbol), item]))
  return strategyRows.value
    .map((row) => {
      const position = positionMap.get(compactSymbol(row.symbol)) as any
      const trend = trendBySymbol.value.get(compactSymbol(row.symbol)) || {}
      const risk = dashboard.value?.risk_queue?.find((item) => compactSymbol(item.symbol) === compactSymbol(row.symbol))
      const opportunity = dashboard.value?.opportunity_queue?.find((item) => compactSymbol(item.symbol) === compactSymbol(row.symbol))
      return {
        ...row,
        symbol: row.symbol,
        name: row.name,
        short_term: row.short_term,
        medium_term: row.medium_term,
        long_term: row.long_term,
        position,
        trend,
        risk_score: risk?.score || 0,
        opportunity_score: opportunity?.score || 0,
        market_value: position?.market_value || 0,
        quantity: position?.quantity || 0,
        portfolio_weight_pct: position?.portfolio_weight_pct ?? positionWeight(position || row),
        unrealized_pnl: position?.unrealized_pnl,
        unrealized_pnl_pct: position?.unrealized_pnl_pct,
        primary_direction: position?.directions?.[0] || row.primary_direction,
        position_role: position?.position_role,
      }
    })
    .sort((a, b) => {
      const activeDiff = Number(b.quantity > 0) - Number(a.quantity > 0)
      if (activeDiff) return activeDiff
      const mvDiff = Number(b.market_value || 0) - Number(a.market_value || 0)
      return marketValueSort.value === 'desc' ? mvDiff : -mvDiff
    })
})

const decisionAction = (row: Record<string, any>) => {
  const quantity = Number(row.quantity || 0)
  const riskScore = Number(row.risk_score || 0)
  const opportunityScore = Number(row.opportunity_score || 0)
  const pnl = Number(row.unrealized_pnl || 0)
  const weight = Number(row.portfolio_weight_pct || 0)
  if (quantity === 0) return 'watch'
  if (riskScore >= 5 || (riskScore >= opportunityScore + 2 && pnl < 0)) return 'reduce'
  if (opportunityScore >= riskScore + 2 && weight < 18) return 'add'
  return 'hold'
}

const actionMeta: Record<string, { title: string; label: string; tone: string; empty: string }> = {
  add: { title: '加仓候选', label: '可加仓观察', tone: 'text-positive', empty: '暂无明确加仓候选' },
  hold: { title: '继续持有', label: '持有跟踪', tone: 'text-primary', empty: '暂无继续持有标的' },
  reduce: { title: '风险处理', label: '减仓/止损观察', tone: 'text-warning', empty: '暂无优先风险处理' },
  watch: { title: '观察候选', label: '仅观察', tone: 'text-muted-foreground', empty: '暂无观察候选' },
}

const decisionReason = (row: Record<string, any>) => {
  if (Number(row.quantity || 0) === 0) return '观察仓成员，不占用当前仓位。'
  if (Number(row.risk_score || 0) >= 5) return '风险分较高，需要优先确认回撤、趋势和仓位压力。'
  if (Number(row.opportunity_score || 0) > Number(row.risk_score || 0)) return '机会分占优，可等待趋势或价格触发。'
  if (Number(row.unrealized_pnl || 0) > 0) return '已有盈利，重点保护利润和跟踪趋势延续。'
  return '当前机会与风险接近，维持观察并等待更清晰触发。'
}

const decisionTrigger = (row: Record<string, any>) => {
  const trend = row.trend || {}
  if (decisionAction(row) === 'watch') return '补齐趋势、方向和外部事实后再进入仓位决策。'
  if (decisionAction(row) === 'reduce') return '跌破 MA20、亏损扩大或风险标签升高时优先处理。'
  if (decisionAction(row) === 'add') return '站稳 MA20、20 日收益转强且方向逻辑延续时再行动。'
  return trend.trend_state ? `趋势状态变化：${trend.trend_state}` : '继续跟踪 MA5/MA20、账户权重和方向驱动。'
}

const decisionImpact = (row: Record<string, any>) => {
  if (Number(row.quantity || 0) === 0) return '不影响当前仓位'
  return `${fmt(row.market_value)} / ${fmt(row.portfolio_weight_pct, '%')}`
}

const actionGroups = computed(() => {
  const groups = ['add', 'hold', 'reduce', 'watch'].map((key) => ({
    key,
    ...actionMeta[key],
    rows: [] as Array<Record<string, any>>,
  }))
  for (const row of decisionRows.value) {
    const group = groups.find((item) => item.key === decisionAction(row))
    group?.rows.push(row)
  }
  return groups
})

const topDirections = computed(() => primaryGroups.value.slice(0, 3))
const topRisks = computed(() => riskGroups.value.slice(0, 3))
const accountPosture = computed(() => {
  const cashRatio = Number(account.value.cash_ratio_pct || 0)
  const topWeight = Math.max(...activePool.value.map((item) => positionWeight(item)), 0)
  const riskWeight = topRisks.value.reduce((sum: number, item: Record<string, any>) => sum + Number(item.weight_pct || 0), 0)
  if (cashRatio < 15 && (topWeight >= 18 || riskWeight >= 45)) return { label: '偏激进', detail: '现金缓冲较低，单一方向或风险标签对账户影响更大。' }
  if (cashRatio >= 30) return { label: '偏稳健', detail: '现金缓冲较高，后续可以更挑剔地等待触发条件。' }
  return { label: '均衡', detail: '现金和持仓暴露相对均衡，重点在结构优化。' }
})

const exposureSummary = computed(() => {
  const direction = topDirections.value[0]
  const risk = topRisks.value[0]
  return {
    mainDirection: direction ? `${labelOf(direction.direction || direction.theme)} ${fmt(direction.weight_pct, '%')}` : '-',
    mainRisk: risk ? `${labelOf(risk.risk_flag || risk.theme)} ${fmt(risk.weight_pct, '%')}` : '-',
    cash: fmt(account.value.cash_ratio_pct, '%'),
  }
})


const directionLabel: Record<string, string> = {
  AI: 'AI',
  GOLD: '黄金',
  COPPER: '铜',
  TUNGSTEN: '钨',
  PCB: 'PCB',
  SEMICONDUCTOR_EQUIPMENT: '半导体设备',
  OTHER: '其他',
  UNCLASSIFIED: '待分类',
  HIGH_VOLATILITY: '高波动',
}

const labelOf = (value?: string | null) => directionLabel[value || ''] || value || '-'

const eventTone = (level?: string) => {
  if (level === 'high') return 'border-negative/50 bg-negative/10 text-negative'
  if (level === 'medium') return 'border-warning/50 bg-warning/10 text-warning'
  return 'border-border bg-secondary/20 text-muted-foreground'
}

const eventStatusLabel = (event: Record<string, any>) => {
  const days = Number(event.days_until)
  if (days < 0) return `已发布 ${Math.abs(days)} 天`
  if (days === 0) return '今日'
  return `${days} 天后`
}

const eventCategoryLabel: Record<string, string> = {
  macro_inflation: '通胀',
  macro_fed: '美联储',
  macro_jobs: '就业',
}

const trendLabel = (position: PortfolioPosition) => {
  const trend = trendBySymbol.value.get(compactSymbol(position.symbol))
  return trend?.trend_state || trend?.data_status || '-'
}

const positionWeight = (position: any) => weightBySymbol.value.get(compactSymbol(position.symbol)) || 0
const toggleMarketValueSort = () => {
  marketValueSort.value = marketValueSort.value === 'desc' ? 'asc' : 'desc'
}


const load = async () => {
  loading.value = true
  contextLoading.value = false
  error.value = ''
  notice.value = ''
  try {
    const portfolio = await getPortfolio()
    state.value = portfolio
    loading.value = false
    contextLoading.value = true
    dashboard.value = await getPortfolioDashboard()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '驾驶舱加载失败'
  } finally {
    loading.value = false
    contextLoading.value = false
  }
}

const generatePacket = async () => {
  packetLoading.value = true
  notice.value = ''
  try {
    const result = await createPortfolioAnalysisPacket()
    packetMarkdown.value = result.markdown
    dashboard.value = await getPortfolioDashboard()
    notice.value = '已刷新组合证据包和驾驶舱数据。'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '组合证据包生成失败'
  } finally {
    packetLoading.value = false
  }
}


onMounted(load)
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-foreground">账户驾驶舱</h1>
        <p class="mt-1 text-xs text-muted-foreground">聚合已保存组合快照、持仓池、观察池、趋势证据、方向暴露和数据缺口。</p>
      </div>
      <div class="flex gap-2 text-xs">
        <button class="h-9 rounded bg-secondary px-3 text-foreground" :disabled="loading" @click="load">刷新</button>
        <button class="h-9 rounded bg-primary px-3 text-primary-foreground" :disabled="packetLoading" @click="generatePacket">
          {{ packetLoading ? '生成中...' : '生成组合证据包' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="rounded border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{{ error }}</div>
    <div v-if="notice" class="rounded border border-positive/40 bg-positive/10 p-3 text-sm text-positive">{{ notice }}</div>
      <div v-if="loading" class="rounded border border-border bg-card p-4 text-sm text-muted-foreground">驾驶舱加载中...</div>
      <div v-else-if="contextLoading" class="rounded border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
        正在补齐趋势证据、持仓池、观察池和个股策略。
      </div>

    <template v-if="!loading && state">
      <div class="grid gap-3 text-xs lg:grid-cols-6">
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">当前估算总资产</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ fmt(account.total_assets) }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">持仓市值</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ fmt(account.total_market_value) }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">可用现金</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ fmt(account.cash_available) }}</div>
          <div class="mt-1 text-muted-foreground">{{ fmt(account.cash_ratio_pct, '%') }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">持仓浮盈亏</div>
          <div :class="['mt-2 font-mono text-lg font-semibold', Number(account.current_holding_unrealized_pnl || 0) >= 0 ? 'text-negative' : 'text-positive']">
            {{ signedFmt(account.current_holding_unrealized_pnl) }}
          </div>
          <div class="mt-1 text-muted-foreground">{{ signedFmt(account.current_holding_unrealized_pnl_pct, '%') }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">实际账户盈亏</div>
          <div :class="['mt-2 font-mono text-lg font-semibold', Number(account.account_total_pnl || 0) >= 0 ? 'text-negative' : 'text-positive']">
            {{ signedFmt(account.account_total_pnl) }}
          </div>
          <div class="mt-1 text-muted-foreground">{{ signedFmt(account.account_total_pnl_pct, '%') }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">持仓 / 观察</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ activeHoldings.length }} / {{ watchlist.length }}</div>
          <div class="mt-1 text-muted-foreground">观察标的不计入仓位</div>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_240px]">
        <div class="space-y-4">
          <div class="space-y-4">
            <div class="rounded border border-border bg-card">
              <div class="flex items-center justify-between border-b border-border px-3 py-2">
                <div>
                  <h2 class="text-sm font-semibold">持仓池</h2>
                  <p class="text-[11px] text-muted-foreground">按当前持仓市值排序，聚焦账户主要暴露。</p>
                </div>
                <button class="rounded bg-secondary px-2 py-1 text-[11px]" @click="toggleMarketValueSort">
                  市值 {{ marketValueSort === 'desc' ? '↓' : '↑' }}
                </button>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[760px] table-fixed text-xs">
                  <colgroup>
                    <col class="w-[170px]" />
                    <col class="w-[90px]" />
                    <col class="w-[100px]" />
                    <col class="w-[90px]" />
                    <col class="w-[110px]" />
                    <col class="w-[130px]" />
                    <col class="w-[62px]" />
                  </colgroup>
                  <thead class="bg-secondary/30 text-muted-foreground">
                    <tr>
                      <th class="px-3 py-2 text-left">标的</th>
                      <th class="px-3 py-2 text-right">数量</th>
                      <th class="px-3 py-2 text-right">市值</th>
                      <th class="px-3 py-2 text-right">权重</th>
                      <th class="px-3 py-2 text-right">浮盈亏</th>
                      <th class="px-3 py-2">方向 / 趋势</th>
                      <th class="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="position in activePool" :key="position.symbol" class="border-t border-border/60">
                      <td class="px-3 py-2">
                        <div class="font-mono text-foreground">{{ position.symbol }}</div>
                        <div class="truncate text-muted-foreground">{{ position.name || position.symbol }}</div>
                      </td>
                      <td class="px-3 py-2 text-right font-mono">{{ fmt(position.quantity) }}</td>
                      <td class="px-3 py-2 text-right font-mono">{{ fmt(position.market_value) }}</td>
                      <td class="px-3 py-2 text-right font-mono">{{ fmt(positionWeight(position), '%') }}</td>
                      <td :class="['px-3 py-2 text-right font-mono', Number(position.unrealized_pnl || 0) >= 0 ? 'text-negative' : 'text-positive']">
                        {{ signedFmt(position.unrealized_pnl) }}
                      </td>
                      <td class="px-3 py-2">
                        <div>{{ labelOf(position.directions?.[0]) }}</div>
                        <div class="text-muted-foreground">{{ trendLabel(position) }}</div>
                      </td>
                      <td class="px-3 py-2 text-right">
                        <button class="rounded bg-secondary px-2 py-1 text-[11px]" @click="emit('select-symbol', compactSymbol(position.symbol))">查看</button>
                      </td>
                    </tr>
                    <tr v-if="!activePool.length"><td colspan="7" class="px-3 py-4 text-center text-muted-foreground">暂无持仓成员</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="rounded border border-border bg-card">
              <div class="flex items-center justify-between border-b border-border px-3 py-2">
                <div>
                  <h2 class="text-sm font-semibold">观察池</h2>
                  <p class="text-[11px] text-muted-foreground">组合维护中持仓数量为 0 的标的会进入观察池。</p>
                </div>
                <button class="rounded bg-secondary px-2 py-1 text-[11px]" @click="toggleMarketValueSort">
                  市值 {{ marketValueSort === 'desc' ? '↓' : '↑' }}
                </button>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[620px] table-fixed text-xs">
                  <colgroup>
                    <col class="w-[180px]" />
                    <col class="w-[90px]" />
                    <col class="w-[120px]" />
                    <col class="w-[150px]" />
                    <col class="w-[62px]" />
                  </colgroup>
                  <thead class="bg-secondary/30 text-muted-foreground">
                    <tr>
                      <th class="px-3 py-2 text-left">标的</th>
                      <th class="px-3 py-2 text-right">参考价</th>
                      <th class="px-3 py-2">方向</th>
                      <th class="px-3 py-2">趋势状态</th>
                      <th class="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="position in watchPool" :key="position.symbol" class="border-t border-border/60">
                      <td class="px-3 py-2">
                        <div class="font-mono text-foreground">{{ position.symbol }}</div>
                        <div class="truncate text-muted-foreground">{{ position.name || position.symbol }}</div>
                      </td>
                      <td class="px-3 py-2 text-right font-mono">{{ fmt(position.market_price || position.system_quote_price) }}</td>
                      <td class="px-3 py-2">{{ labelOf(position.directions?.[0]) }}</td>
                      <td class="px-3 py-2 text-muted-foreground">{{ trendLabel(position) }}</td>
                      <td class="px-3 py-2 text-right">
                        <button class="rounded bg-secondary px-2 py-1 text-[11px]" @click="emit('select-symbol', compactSymbol(position.symbol))">查看</button>
                      </td>
                    </tr>
                    <tr v-if="!watchPool.length"><td colspan="5" class="px-3 py-4 text-center text-muted-foreground">暂无观察池成员</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div class="rounded border border-border bg-card">
            <div class="flex items-center justify-between border-b border-border px-3 py-2">
              <div>
                <h2 class="text-sm font-semibold">个股策略动作队列</h2>
                <p class="text-[11px] text-muted-foreground">按后续动作聚合，先看该做什么，再看涉及哪些标的。</p>
              </div>
              <button class="rounded bg-secondary px-2 py-1 text-[11px]" @click="toggleMarketValueSort">
                按市值 {{ marketValueSort === 'desc' ? '降序' : '升序' }}
              </button>
            </div>
            <div class="grid gap-3 p-3 xl:grid-cols-2">
              <section v-for="group in actionGroups" :key="group.key" class="rounded border border-border/70 bg-secondary/10">
                <div class="flex items-center justify-between border-b border-border/60 px-3 py-2">
                  <div>
                    <h3 class="text-sm font-semibold">{{ group.title }}</h3>
                    <p class="text-[11px] text-muted-foreground">{{ group.rows.length }} 标的</p>
                  </div>
                  <span :class="['text-[11px] font-medium', group.tone]">{{ group.label }}</span>
                </div>
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[760px] table-fixed text-xs">
                    <colgroup>
                      <col class="w-[150px]" />
                      <col class="w-[110px]" />
                      <col class="w-[210px]" />
                      <col class="w-[220px]" />
                      <col class="w-[90px]" />
                    </colgroup>
                    <thead class="bg-secondary/20 text-muted-foreground">
                      <tr>
                        <th class="px-3 py-2 text-left">标的</th>
                        <th class="px-3 py-2 text-left">主动作</th>
                        <th class="px-3 py-2 text-left">原因</th>
                        <th class="px-3 py-2 text-left">触发条件</th>
                        <th class="px-3 py-2 text-right">仓位影响</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="row in group.rows" :key="group.key + '-' + row.symbol" class="border-t border-border/50 align-top">
                        <td class="px-3 py-2">
                          <div class="font-mono text-foreground">{{ row.symbol }}</div>
                          <div class="truncate text-muted-foreground">{{ row.name }}</div>
                          <div class="mt-1 text-[11px] text-muted-foreground">机会 {{ row.opportunity_score }} / 风险 {{ row.risk_score }}</div>
                        </td>
                        <td class="px-3 py-2">
                          <span :class="['font-medium', actionMeta[group.key].tone]">{{ actionMeta[group.key].label }}</span>
                          <div v-if="Number(row.quantity || 0) === 0" class="mt-1 text-[11px] text-warning">观察</div>
                        </td>
                        <td class="px-3 py-2 text-muted-foreground">{{ decisionReason(row) }}</td>
                        <td class="px-3 py-2 text-muted-foreground">{{ decisionTrigger(row) }}</td>
                        <td class="px-3 py-2 text-right font-mono text-muted-foreground">{{ decisionImpact(row) }}</td>
                      </tr>
                      <tr v-if="!group.rows.length">
                        <td colspan="5" class="px-3 py-4 text-center text-muted-foreground">{{ group.empty || '暂无该类动作' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <div class="rounded border border-border bg-card">
            <div class="border-b border-border px-3 py-2">
              <div class="flex items-center justify-between gap-2">
                <h2 class="text-sm font-semibold">市场事件雷达</h2>
                <span class="rounded bg-secondary/40 px-2 py-0.5 text-[11px] text-muted-foreground">
                  {{ eventRadar?.window_days || 45 }} 天
                </span>
              </div>
              <p class="mt-1 text-[11px] text-muted-foreground">确定会发生、可能放大组合波动的宏观节点。</p>
            </div>
            <div class="space-y-3 p-3 text-xs">
              <div v-if="nextMarketEvent" class="rounded border border-warning/50 bg-warning/10 p-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-medium text-warning">下一事件</span>
                  <span class="font-mono text-warning">{{ eventStatusLabel(nextMarketEvent) }}</span>
                </div>
                <div class="mt-1 font-semibold text-foreground">{{ nextMarketEvent.title }}</div>
                <div class="mt-1 text-muted-foreground">{{ nextMarketEvent.date }} {{ nextMarketEvent.time_et }} ET</div>
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div class="rounded bg-secondary/25 p-2">
                  <div class="text-muted-foreground">高影响事件</div>
                  <div class="mt-1 font-mono text-lg font-semibold text-foreground">{{ eventRadar?.high_impact_count || 0 }}</div>
                </div>
                <div class="rounded bg-secondary/25 p-2">
                  <div class="text-muted-foreground">已匹配事件</div>
                  <div class="mt-1 font-mono text-lg font-semibold text-foreground">{{ marketEvents.length }}</div>
                </div>
              </div>
              <div class="space-y-2">
                <div
                  v-for="event in marketEvents.slice(0, 5)"
                  :key="event.event_id"
                  class="rounded border border-border/70 bg-secondary/10 p-2"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="flex items-center gap-2">
                        <span class="truncate font-medium text-foreground">{{ event.title }}</span>
                        <span class="shrink-0 rounded bg-secondary/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {{ eventCategoryLabel[event.category] || event.category }}
                        </span>
                      </div>
                      <div class="mt-1 text-muted-foreground">{{ event.date }} {{ event.time_et }} ET</div>
                    </div>
                    <div :class="['shrink-0 rounded border px-2 py-1 text-right font-mono text-[11px]', eventTone(event.impact_level)]">
                      {{ event.impact_score }}
                    </div>
                  </div>
                  <p class="mt-2 text-muted-foreground">{{ event.portfolio_readout }}</p>
                  <div v-if="event.related_positions?.length" class="mt-2 flex flex-wrap gap-1">
                    <span
                      v-for="position in event.related_positions.slice(0, 3)"
                      :key="`${event.event_id}-${position.symbol}`"
                      class="rounded bg-secondary/50 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                    >
                      {{ position.symbol }} {{ fmt(position.portfolio_weight_pct, '%') }}
                    </span>
                  </div>
                </div>
                <div v-if="!marketEvents.length" class="rounded border border-border/70 bg-secondary/10 p-3 text-muted-foreground">
                  未来窗口内暂无已配置事件。
                </div>
              </div>
              <div class="text-[11px] text-muted-foreground">{{ eventRadar?.boundary }}</div>
            </div>
          </div>

          <div class="rounded border border-border bg-card">
            <div class="border-b border-border px-3 py-2">
              <h2 class="text-sm font-semibold">账户暴露摘要</h2>
            </div>
            <div class="space-y-4 p-3 text-xs">
              <div class="space-y-2">
                <div class="text-muted-foreground">账户风格</div>
                <div class="text-lg font-semibold text-foreground">{{ accountPosture.label }}</div>
                <p class="text-muted-foreground">{{ accountPosture.detail }}</p>
              </div>
              <div class="grid gap-2">
                <div class="rounded bg-secondary/25 p-2">
                  <div class="text-muted-foreground">主要暴露</div>
                  <div class="mt-1 font-mono text-foreground">{{ exposureSummary.mainDirection }}</div>
                </div>
                <div class="rounded bg-secondary/25 p-2">
                  <div class="text-muted-foreground">主要风险</div>
                  <div class="mt-1 font-mono text-warning">{{ exposureSummary.mainRisk }}</div>
                </div>
                <div class="rounded bg-secondary/25 p-2">
                  <div class="text-muted-foreground">现金缓冲</div>
                  <div class="mt-1 font-mono text-foreground">{{ exposureSummary.cash }}</div>
                </div>
              </div>
              <div>
                <div class="mb-2 font-medium text-foreground">暴露方向</div>
                <div class="space-y-2">
                  <div v-for="group in topDirections" :key="group.direction || group.theme" class="space-y-1">
                    <div class="flex justify-between gap-2">
                      <span class="truncate">{{ labelOf(group.direction || group.theme) }}</span>
                      <span class="font-mono">{{ fmt(group.weight_pct, '%') }}</span>
                    </div>
                    <div class="h-2 overflow-hidden rounded bg-secondary">
                      <div class="h-full bg-primary" :style="{ width: `${Math.min(Number(group.weight_pct || 0), 100)}%` }"></div>
                    </div>
                  </div>
                  <div v-if="!topDirections.length" class="text-muted-foreground">暂无方向暴露</div>
                </div>
              </div>
              <div>
                <div class="mb-2 font-medium text-foreground">风险来源</div>
                <div class="space-y-2">
                  <div v-for="group in topRisks" :key="group.risk_flag || group.theme" class="flex items-center justify-between gap-2">
                    <span class="truncate">{{ labelOf(group.risk_flag || group.theme) }}</span>
                    <span class="font-mono text-warning">{{ fmt(group.weight_pct, '%') }}</span>
                  </div>
                  <div v-if="!topRisks.length" class="text-muted-foreground">暂无风险来源</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="rounded border border-border bg-card">
        <div class="border-b border-border px-3 py-2">
          <h2 class="text-sm font-semibold">数据缺口</h2>
        </div>
        <div class="grid gap-2 p-3 text-xs text-muted-foreground md:grid-cols-2 xl:grid-cols-3">
          <p v-for="(gap, idx) in dataGaps.slice(0, 12)" :key="idx">
            {{ typeof gap === 'string' ? gap : `${gap.symbol ? gap.symbol + ' - ' : ''}${gap.key || 'gap'}：${gap.reason || gap.raw_reason || '-'}` }}
          </p>
          <div v-if="!dataGaps.length">暂无数据缺口</div>
        </div>
      </div>

      <details v-if="packetMarkdown" class="rounded border border-border bg-card p-3 text-xs">
        <summary class="cursor-pointer text-muted-foreground">最近生成的组合证据包 Markdown</summary>
        <pre class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-3">{{ packetMarkdown }}</pre>
      </details>
    </template>
  </section>
</template>
