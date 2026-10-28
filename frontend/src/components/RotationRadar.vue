<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  getRotationSectorResearch,
  getRotationSummary,
  refreshRotationSummary,
  type RotationSectorResearch,
  type RotationSummary,
} from '../api/client'
import RotationResearchChart from './RotationResearchChart.vue'

const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const data = ref<RotationSummary | null>(null)
const research = ref<RotationSectorResearch | null>(null)
const researchLoading = ref(false)
const researchError = ref('')
let researchRequestId = 0
const activeCategory = ref('全部')
const onlyAccountRelated = ref(false)
const selectedId = ref<string | null>(null)

const emit = defineEmits<{
  (e: 'select-symbol', symbol: string): void
}>()

const categories = computed(() => {
  const names = new Set((data.value?.sectors || []).map((item) => item.category).filter(Boolean))
  return ['全部', ...Array.from(names)]
})

const sectors = computed(() => {
  let rows = data.value?.sectors || []
  if (activeCategory.value !== '全部') rows = rows.filter((item) => item.category === activeCategory.value)
  if (onlyAccountRelated.value) {
    rows = rows.filter((item) => (item.account_exposure?.related_holdings || []).length > 0)
  }
  return rows
})

const selectedSector = computed(() => {
  const rows = data.value?.sectors || []
  return rows.find((item) => item.sector_id === selectedId.value) || rows[0] || null
})

const representativeStocks = computed(() =>
  research.value?.securities.filter((item) => item.role === 'representative_stock') || [],
)

const directionEtfs = computed(() =>
  research.value?.securities.filter((item) => item.role === 'direction_etf') || [],
)

const loadResearch = async (sectorId: string | null) => {
  if (!sectorId) return
  const requestId = ++researchRequestId
  researchLoading.value = true
  researchError.value = ''
  try {
    const nextResearch = await getRotationSectorResearch(sectorId)
    if (requestId === researchRequestId) research.value = nextResearch
  } catch (e: any) {
    if (requestId === researchRequestId) {
      research.value = null
      researchError.value = e?.message || String(e)
    }
  } finally {
    if (requestId === researchRequestId) researchLoading.value = false
  }
}

const load = async (force = false) => {
  loading.value = true
  error.value = ''
  try {
    data.value = await getRotationSummary(force)
    if (!selectedId.value && data.value.sectors.length) selectedId.value = data.value.sectors[0].sector_id
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

const refresh = async () => {
  refreshing.value = true
  error.value = ''
  try {
    data.value = await refreshRotationSummary()
    await loadResearch(selectedId.value)
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    refreshing.value = false
  }
}

const fmt = (value: number | null | undefined, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  return `${Number(value).toFixed(2)}${suffix}`
}

const signedFmt = (value: number | null | undefined, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}${suffix}`
}

const scoreTone = (score: number) => {
  if (score >= 75) return 'text-positive'
  if (score >= 55) return 'text-warning'
  return 'text-muted-foreground'
}

const deltaTone = (value: number | null | undefined) => {
  if (value === null || value === undefined) return 'text-muted-foreground'
  if (value > 0) return 'text-market-up'
  if (value < 0) return 'text-market-down'
  return 'text-muted-foreground'
}

const maturityLabel = (value: string) => ({
  leading: '领涨',
  spreading: '扩散',
  emerging: '萌芽',
  cooling: '降温',
  declining: '走弱',
  neutral: '中性',
  unavailable: '不可用',
}[value] || value)

const opportunityLabel = (row: RotationSummary['sectors'][number]) => row.action_label || ({
  potential_opportunity: '潜在机会',
  early_turning: '早期转强',
  wait_pullback: '强势但等回踩',
  avoid_now: '暂不参与',
}[row.opportunity_stage || ''] || maturityLabel(row.maturity))

const opportunityTone = (value?: string) => ({
  potential_opportunity: 'border-positive/50 bg-positive/10 text-positive',
  early_turning: 'border-sky-500/40 bg-sky-500/10 text-sky-200',
  wait_pullback: 'border-warning/50 bg-warning/10 text-warning',
  avoid_now: 'border-border bg-secondary/30 text-muted-foreground',
}[value || ''] || 'border-border bg-secondary/30 text-muted-foreground')

const chasingRiskLabel = (value?: string) => ({
  low: '追高风险低',
  medium: '追高风险中',
  high: '追高风险高',
  unknown: '风险未知',
  none: '不适用',
}[value || ''] || value || '--')

const qualityLabel = (value: string) => ({
  available: '可用',
  stale: '滞后',
  partial: '部分',
  unavailable: '缺失',
}[value] || value)

const proxyLabel = (sector: RotationSummary['sectors'][number]) => {
  if (sector.proxy_type === 'synthetic') return `${sector.proxy_components?.length || 0} 个龙头等权`
  return sector.selected_symbol || sector.primary_symbol || 'ETF'
}

const openSymbol = (symbol?: string | null) => {
  if (!symbol) return
  emit('select-symbol', symbol)
}

watch(selectedId, (value) => loadResearch(value))

onMounted(() => load(false))
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-foreground">轮动雷达</h1>
        <p class="mt-1 text-xs text-muted-foreground">
          {{ data?.market_style?.benchmark_note || '宽基作风格参照，方向池参与排名。' }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">截至 {{ data?.as_of || '--' }}</span>
        <button
          class="h-9 rounded border border-border px-3 text-xs text-foreground hover:bg-secondary/60 disabled:opacity-50"
          :disabled="refreshing || loading"
          @click="refresh"
        >
          {{ refreshing ? '刷新中...' : '手动刷新' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="rounded border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{{ error }}</div>
    <div v-if="loading && !data" class="rounded border border-border bg-card p-4 text-sm text-muted-foreground">正在读取本地轮动缓存...</div>

    <template v-if="data">
      <div class="grid gap-3 lg:grid-cols-4">
        <div class="rounded border border-border bg-card p-3">
          <div class="text-xs text-muted-foreground">潜在机会</div>
          <div class="mt-2 font-mono text-lg font-semibold text-positive">{{ data.summary.potential_opportunity_count || 0 }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-xs text-muted-foreground">早期转强</div>
          <div class="mt-2 font-mono text-lg font-semibold text-sky-200">{{ data.summary.early_turning_count || 0 }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-xs text-muted-foreground">强势但等回踩</div>
          <div class="mt-2 font-mono text-lg font-semibold text-warning">{{ data.summary.wait_pullback_count || 0 }}</div>
        </div>
        <div class="rounded border border-border bg-card p-3">
          <div class="text-xs text-muted-foreground">暂不参与</div>
          <div class="mt-2 font-mono text-lg font-semibold text-muted-foreground">{{ data.summary.avoid_now_count || 0 }}</div>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div class="space-y-3">
          <div class="flex flex-wrap items-center gap-2">
            <button
              v-for="category in categories"
              :key="category"
              :class="[
                'h-8 rounded border px-3 text-xs',
                activeCategory === category ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
              ]"
              @click="activeCategory = category"
            >
              {{ category }}
            </button>
            <label class="ml-auto hidden h-8 items-center gap-2 rounded border border-border px-3 text-xs text-muted-foreground">
              <input v-model="onlyAccountRelated" type="checkbox" class="h-3 w-3" />
              仅看组合相关
            </label>
          </div>

          <div class="overflow-hidden rounded border border-border bg-card">
            <table class="w-full text-left text-xs">
              <thead class="bg-secondary/50 text-muted-foreground">
                <tr>
                  <th class="px-3 py-2 font-medium">方向</th>
                  <th class="px-3 py-2 text-right font-medium">总分</th>
                  <th class="px-3 py-2 text-right font-medium">5日</th>
                  <th class="px-3 py-2 text-right font-medium">趋势</th>
                  <th class="px-3 py-2 text-right font-medium">动量</th>
                  <th class="px-3 py-2 text-right font-medium">相对</th>
                  <th class="px-3 py-2 text-right font-medium">量能</th>
                  <th class="px-3 py-2 text-right font-medium">MA20偏离</th>
                  <th class="px-3 py-2 font-medium">机会阶段</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sectors"
                  :key="row.sector_id"
                  :class="[
                    'cursor-pointer border-t border-border/60 hover:bg-secondary/30',
                    selectedId === row.sector_id ? 'bg-secondary/40' : '',
                  ]"
                  @click="selectedId = row.sector_id"
                >
                  <td class="px-3 py-2">
                    <div class="font-medium text-foreground">{{ row.name }}</div>
                    <div class="mt-0.5 text-[11px] text-muted-foreground">
                      {{ row.category }} · {{ proxyLabel(row) }}
                    </div>
                  </td>
                  <td class="px-3 py-2 text-right font-mono font-semibold" :class="scoreTone(row.score.total)">{{ fmt(row.score.total) }}</td>
                  <td class="px-3 py-2 text-right font-mono" :class="deltaTone(row.score_delta_5d)">{{ signedFmt(row.score_delta_5d) }}</td>
                  <td class="px-3 py-2 text-right font-mono">{{ fmt(row.score.trend) }}</td>
                  <td class="px-3 py-2 text-right font-mono">{{ fmt(row.score.momentum) }}</td>
                  <td class="px-3 py-2 text-right font-mono">{{ fmt(row.score.relative_strength) }}</td>
                  <td class="px-3 py-2 text-right font-mono">{{ fmt(row.score.flow) }}</td>
                  <td class="px-3 py-2 text-right font-mono" :class="deltaTone(row.ma20_distance_pct)">{{ signedFmt(row.ma20_distance_pct, '%') }}</td>
                  <td class="px-3 py-2">
                    <span :class="['inline-flex rounded border px-2 py-0.5 text-[11px]', opportunityTone(row.opportunity_stage)]">
                      {{ opportunityLabel(row) }}
                    </span>
                  </td>
                </tr>
                <tr v-if="sectors.length === 0">
                  <td colspan="9" class="px-3 py-6 text-center text-muted-foreground">当前筛选下暂无方向。</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <aside v-if="selectedSector" class="space-y-3">
          <div class="rounded border border-border bg-card p-3">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-base font-semibold text-foreground">{{ selectedSector.name }}</div>
                <div class="mt-1 text-xs text-muted-foreground">
                  {{ selectedSector.category }} · {{ qualityLabel(selectedSector.data_quality) }} · {{ selectedSector.latest_date || '--' }}
                </div>
              </div>
              <span :class="['shrink-0 rounded border px-2 py-0.5 text-[11px]', opportunityTone(selectedSector.opportunity_stage)]">
                {{ opportunityLabel(selectedSector) }}
              </span>
            </div>
            <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div class="rounded border border-border/70 p-2">
                <div class="text-muted-foreground">5日涨跌</div>
                <div class="mt-1 font-mono text-sm" :class="deltaTone(selectedSector.returns.return_5d)">{{ signedFmt(selectedSector.returns.return_5d, '%') }}</div>
              </div>
              <div class="rounded border border-border/70 p-2">
                <div class="text-muted-foreground">20日相对沪深300</div>
                <div class="mt-1 font-mono text-sm" :class="deltaTone(selectedSector.relative_strength.relative_strength_20d)">
                  {{ signedFmt(selectedSector.relative_strength.relative_strength_20d, '%') }}
                </div>
              </div>
              <div class="rounded border border-border/70 p-2">
                <div class="text-muted-foreground">5日量能</div>
                <div class="mt-1 font-mono text-sm">{{ signedFmt(selectedSector.flow.amount_ratio_5d, '%') }}</div>
              </div>
              <div class="rounded border border-border/70 p-2">
                <div class="text-muted-foreground">追高风险</div>
                <div class="mt-1 text-sm text-warning">{{ chasingRiskLabel(selectedSector.chasing_risk) }}</div>
              </div>
            </div>
            <div v-if="selectedSector.opportunity_reason" class="mt-3 rounded border border-border/70 bg-secondary/20 p-2 text-xs leading-5 text-muted-foreground">
              {{ selectedSector.opportunity_reason }}
            </div>
          </div>

          <div class="rounded border border-border bg-card p-3">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-xs font-medium text-muted-foreground">判断依据</div>
                <div class="mt-1 text-xs text-muted-foreground">
                  {{ selectedSector.proxy_type === 'synthetic' ? '由若干代表性龙头合成，便于观察细分方向。' : '由代表性 ETF 作为板块代理。' }}
                </div>
              </div>
              <button
                v-if="selectedSector.proxy_type !== 'synthetic' && (selectedSector.selected_symbol || selectedSector.primary_symbol)"
                class="shrink-0 rounded border border-border px-2 py-1 text-xs text-foreground hover:bg-secondary/60"
                @click="openSymbol(selectedSector.selected_symbol || selectedSector.primary_symbol)"
              >
                分析 ETF
              </button>
            </div>
            <div class="mt-3 space-y-2">
              <button
                v-for="component in selectedSector.proxy_components || []"
                :key="`${selectedSector.sector_id}-${component.symbol}`"
                class="flex w-full items-center justify-between rounded border border-border/70 px-2 py-1.5 text-left text-xs hover:bg-secondary/50"
                @click="openSymbol(component.symbol)"
              >
                <span class="min-w-0 truncate text-foreground">
                  <span class="font-mono">{{ component.symbol }}</span>
                  <span class="ml-2">{{ component.name || component.symbol }}</span>
                </span>
                <span class="shrink-0 font-mono text-muted-foreground">{{ fmt((component.weight || 0) * 100, '%') }}</span>
              </button>
            </div>
          </div>

          <div class="rounded border border-border bg-card p-3">
            <div class="text-xs font-medium text-muted-foreground">关联持仓</div>
            <div v-if="selectedSector.account_exposure?.related_holdings?.length" class="mt-2 space-y-2">
              <div
                v-for="holding in selectedSector.account_exposure.related_holdings"
                :key="`${selectedSector.sector_id}-${holding.symbol}-${holding.relation}`"
                class="flex items-center justify-between rounded border border-border/70 px-2 py-1.5 text-xs"
              >
                <span class="min-w-0 truncate text-foreground">{{ holding.symbol }} {{ holding.name }}</span>
                <span class="shrink-0 text-muted-foreground">{{ holding.relation === 'main' ? '主关联' : '弱关联' }}</span>
              </div>
            </div>
            <div v-else class="mt-2 text-xs text-muted-foreground">当前组合未发现直接或弱关联持仓。</div>
          </div>

          <div class="rounded border border-border bg-card p-3 text-xs leading-5 text-muted-foreground">
            {{ data.boundary }}
          </div>
        </aside>
      </div>

      <section class="border-y border-border bg-card">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <div class="text-xs text-muted-foreground">方向深挖</div>
            <h2 class="mt-1 text-base font-semibold text-foreground">
              {{ selectedSector?.name || '--' }} · ETF 与代表股交叉验证
            </h2>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ research?.research_universe.selection_note || '正在读取方向代理池与代表股行情。' }}
            </p>
          </div>
          <div v-if="research" class="text-right text-xs text-muted-foreground">
            <div>数据覆盖 {{ fmt(research.objective_metrics.data_coverage_pct, '%') }}</div>
            <div class="mt-1">规则判断置信度 {{ research.evidence_analysis.confidence }}</div>
          </div>
        </div>

        <div v-if="researchLoading" class="px-4 py-8 text-center text-sm text-muted-foreground">
          正在计算代表标的走势、市场广度与风险指标...
        </div>
        <div v-else-if="researchError" class="px-4 py-4 text-sm text-negative">{{ researchError }}</div>

        <template v-else-if="research">
          <div class="grid grid-cols-2 gap-px border-b border-border bg-border md:grid-cols-4 xl:grid-cols-8">
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">代表股站上 MA20</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.breadth.above_ma20_pct, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">代表股站上 MA60</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.breadth.above_ma60_pct, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">20日跑赢沪深300</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.breadth.outperform_hs300_20d_pct, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">滚动相对胜率</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.objective_metrics.relative_win_rate_5d, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">代表股20日中位收益</div>
              <div class="mt-1 font-mono text-base" :class="deltaTone(research.breadth.median_return_20d)">
                {{ signedFmt(research.breadth.median_return_20d, '%') }}
              </div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">内部收益离散度</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.breadth.return_dispersion_20d, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">20日年化波动率</div>
              <div class="mt-1 font-mono text-base text-foreground">{{ fmt(research.objective_metrics.volatility_20d, '%') }}</div>
            </div>
            <div class="bg-card px-3 py-3">
              <div class="text-[11px] text-muted-foreground">60日最大回撤</div>
              <div class="mt-1 font-mono text-base" :class="deltaTone(research.objective_metrics.max_drawdown_60d)">
                {{ signedFmt(research.objective_metrics.max_drawdown_60d, '%') }}
              </div>
            </div>
          </div>

          <div class="grid border-b border-border xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
            <div class="border-b border-border p-4 xl:border-b-0 xl:border-r">
              <div class="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-foreground">近120日标准化走势</div>
                  <div class="mt-1 text-[11px] text-muted-foreground">起点统一为 100，用于比较方向代理与沪深300，不代表实际净值。</div>
                </div>
                <div class="flex gap-3 text-[11px] text-muted-foreground">
                  <span><i class="mr-1 inline-block h-2 w-2 bg-sky-400"></i>方向代理</span>
                  <span><i class="mr-1 inline-block h-2 w-2 bg-slate-400"></i>沪深300</span>
                </div>
              </div>
              <RotationResearchChart :points="research.trend_series" />
            </div>

            <div class="p-4">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-foreground">证据综合</div>
                <span class="text-[11px] text-muted-foreground">{{ research.evidence_analysis.method }}</span>
              </div>
              <p class="mt-3 text-sm leading-6 text-foreground">{{ research.evidence_analysis.conclusion }}</p>
              <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-1">
                <div>
                  <div class="text-xs font-medium text-positive">支持证据</div>
                  <ul class="mt-2 space-y-1 text-xs leading-5 text-muted-foreground">
                    <li v-for="item in research.evidence_analysis.supports" :key="item">+ {{ item }}</li>
                    <li v-if="!research.evidence_analysis.supports.length">暂无形成一致支持的证据。</li>
                  </ul>
                </div>
                <div>
                  <div class="text-xs font-medium text-warning">风险与反证</div>
                  <ul class="mt-2 space-y-1 text-xs leading-5 text-muted-foreground">
                    <li v-for="item in research.evidence_analysis.cautions" :key="item">- {{ item }}</li>
                    <li v-if="!research.evidence_analysis.cautions.length">当前未触发显著风险阈值。</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <div class="p-4">
            <div class="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h3 class="text-sm font-medium text-foreground">主要标的与近期走势</h3>
                <p class="mt-1 text-[11px] text-muted-foreground">
                  {{ directionEtfs.length }} 只方向 ETF · {{ representativeStocks.length }} 只代表股；点击标的进入个股或 ETF 分析。
                </p>
              </div>
              <div class="text-[11px] text-muted-foreground">收益和风险均基于本地冷数据，截止 {{ research.research_as_of || research.latest_date || '--' }}</div>
            </div>
            <div class="mt-3 overflow-x-auto border border-border">
              <table class="w-full min-w-[960px] text-left text-xs">
                <thead class="bg-secondary/50 text-muted-foreground">
                  <tr>
                    <th class="px-3 py-2 font-medium">标的</th>
                    <th class="px-3 py-2 font-medium">角色</th>
                    <th class="px-3 py-2 font-medium">趋势结构</th>
                    <th class="px-3 py-2 text-right font-medium">5日</th>
                    <th class="px-3 py-2 text-right font-medium">20日</th>
                    <th class="px-3 py-2 text-right font-medium">60日</th>
                    <th class="px-3 py-2 text-right font-medium">20日超额</th>
                    <th class="px-3 py-2 text-right font-medium">成交额确认</th>
                    <th class="px-3 py-2 text-right font-medium">20日波动</th>
                    <th class="px-3 py-2 text-right font-medium">60日回撤</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="security in research.securities"
                    :key="`${research.sector_id}-${security.symbol}`"
                    class="cursor-pointer border-t border-border/60 hover:bg-secondary/30"
                    @click="openSymbol(security.symbol)"
                  >
                    <td class="px-3 py-2">
                      <div class="font-medium text-foreground">{{ security.name }}</div>
                      <div class="mt-0.5 font-mono text-[11px] text-muted-foreground">{{ security.symbol }}</div>
                    </td>
                    <td class="px-3 py-2 text-muted-foreground">{{ security.role === 'direction_etf' ? '方向 ETF' : '代表股' }}</td>
                    <td class="px-3 py-2 text-foreground">{{ security.trend_state || '--' }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.returns?.return_5d)">{{ signedFmt(security.returns?.return_5d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.returns?.return_20d)">{{ signedFmt(security.returns?.return_20d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.returns?.return_60d)">{{ signedFmt(security.returns?.return_60d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.relative_strength_20d)">{{ signedFmt(security.relative_strength_20d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.amount_ratio_5d)">{{ signedFmt(security.amount_ratio_5d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono">{{ fmt(security.volatility_20d, '%') }}</td>
                    <td class="px-3 py-2 text-right font-mono" :class="deltaTone(security.max_drawdown_60d)">{{ signedFmt(security.max_drawdown_60d, '%') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </section>
    </template>
  </section>
</template>
