<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { API_BASE_URL, analyzeStock, getColdDataStatus, searchStocks, type AnalyzeResponse, type ColdDataStatus, type StockSearchItem } from './api/client'
import {
  API_BASE_LABEL,
  DEFAULT_API_BASE_URL,
  normalizeApiBaseUrl,
  resetApiBaseUrl,
  saveApiBaseUrl,
} from './api/config'
import StockCard from './components/StockCard.vue'
import DeepAnalysisPanel from './components/DeepAnalysisPanel.vue'
import KLineChart from './components/KLineChart.vue'
import AutoFactsPanel from './components/AutoFactsPanel.vue'
import AnalysisPacketPanel from './components/AnalysisPacketPanel.vue'
import PortfolioPanel from './components/PortfolioPanel.vue'
import AccountDashboard from './components/AccountDashboard.vue'
import RotationRadar from './components/RotationRadar.vue'
import AgentReview from './components/AgentReview.vue'
import CockpitBriefing from './components/CockpitBriefing.vue'
import PositionContextPanel from './components/PositionContextPanel.vue'
import { getSearchHistory, updateSearchHistory, type SearchHistoryItem } from './utils/searchHistory'
import { APP_VERSION } from './version'

const activeView = ref<'dashboard' | 'portfolio' | 'discovery' | 'review'>('dashboard')
const discoveryMode = ref<'rotation' | 'research'>('rotation')
const portfolioPanelRef = ref<InstanceType<typeof PortfolioPanel> | null>(null)
const portfolioImportKind = ref<'current_holdings' | 'trade_history' | null>(null)
const portfolioImportRequest = ref(0)
const symbol = ref('600519')
const loading = ref(false)
const result = ref<AnalyzeResponse | null>(null)
const error = ref('')
const coldDataStatus = ref<ColdDataStatus | null>(null)
const coldDataError = ref(false)
let coldDataTimer: number | undefined
const apiSettingsOpen = ref(false)
const apiAddress = ref(API_BASE_URL)
const apiSettingsError = ref('')
const apiTestStatus = ref('')
const apiTesting = ref(false)

const testApiConnection = async () => {
  apiSettingsError.value = ''
  apiTestStatus.value = ''
  apiTesting.value = true
  try {
    const target = normalizeApiBaseUrl(apiAddress.value)
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 5000)
    try {
      const response = await fetch(`${target}/health`, { signal: controller.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      apiTestStatus.value = '连接正常'
    } finally {
      window.clearTimeout(timer)
    }
  } catch (nextError) {
    apiSettingsError.value = nextError instanceof Error && nextError.name === 'AbortError'
      ? '连接超时，请确认后端已启动'
      : `连接失败：${nextError instanceof Error ? nextError.message : '未知错误'}`
  } finally {
    apiTesting.value = false
  }
}

const applyApiSettings = () => {
  apiSettingsError.value = ''
  try {
    saveApiBaseUrl(apiAddress.value)
    window.location.reload()
  } catch (nextError) {
    apiSettingsError.value = nextError instanceof Error ? nextError.message : 'API 地址无效'
  }
}

const restoreDefaultApi = () => {
  resetApiBaseUrl()
  window.location.reload()
}

const showSuggestions = ref(false)
const activeIndex = ref(-1)
const searchContainerRef = ref<HTMLElement | null>(null)
const shouldFilterHistory = ref(false)

const allHistory = ref<SearchHistoryItem[]>([])
const stockMatches = ref<StockSearchItem[]>([])
let stockSearchTimer: number | undefined

type SearchSuggestion = SearchHistoryItem & {
  source: 'history' | 'search'
  industry?: string
  area?: string
  asset_type?: string
}

const suggestions = computed(() => {
  const term = shouldFilterHistory.value ? symbol.value.trim() : ''
  const historyMatches = allHistory.value
    .filter((item) => {
      const itemSymbol = item.symbol || ''
      const itemName = item.name || ''
      return !term || itemSymbol.includes(term) || itemName.includes(term)
    })
    .map((item) => ({
      ...item,
      symbol: item.symbol || '',
      name: item.name || item.symbol || '未知标的',
      source: 'history' as const,
      industry: undefined,
      area: undefined,
      asset_type: undefined,
    }))

  const seen = new Set(historyMatches.map((item) => item.symbol))
  const remoteMatches = stockMatches.value
    .filter((item) => item.symbol && !seen.has(item.symbol))
    .map((item) => ({
      symbol: item.symbol,
      name: item.name || item.symbol,
      lastViewed: 0,
      count: 0,
      source: 'search' as const,
      industry: item.industry,
      area: item.area,
      asset_type: item.asset_type,
    }))

  return [...historyMatches, ...remoteMatches].slice(0, 20)
})

const refreshHistory = () => {
  allHistory.value = getSearchHistory()
}

const fetchStockMatches = async () => {
  const term = symbol.value.trim()
  if (!term) {
    stockMatches.value = []
    return
  }
  try {
    stockMatches.value = await searchStocks(term, 12)
  } catch {
    stockMatches.value = []
  }
}

const scheduleStockSearch = () => {
  if (stockSearchTimer) window.clearTimeout(stockSearchTimer)
  stockSearchTimer = window.setTimeout(fetchStockMatches, 180)
}

const loadColdDataStatus = async () => {
  try {
    coldDataStatus.value = await getColdDataStatus()
    coldDataError.value = false
  } catch {
    coldDataError.value = true
  }
}

const coldDataDotClass = computed(() => {
  if (coldDataError.value) return 'bg-negative'
  const components = coldDataStatus.value?.components
  const statuses = [
    coldDataStatus.value?.status,
    components?.stock?.status,
    components?.etf?.status,
    components?.rotation?.status,
  ].filter(Boolean)
  if (statuses.some((status) => status === 'running' || status === 'checking')) return 'bg-warning animate-pulse'
  if (statuses.some((status) => status === 'partial_failed' || status === 'unavailable' || status === 'market_deferred' || status === 'stale')) return 'bg-warning'
  if (statuses.length > 0 && statuses.every((status) => status === 'complete')) return 'bg-positive'
  return 'bg-muted-foreground'
})

const formatColdComponent = (label: string, component?: ColdDataStatus) => {
  if (!component) return `${label} --`
  const status = component.status
  if (status === 'running' || status === 'checking') {
    const phase = component.phase
    const coreReadyText = component.core_total ? `核心完成 ${component.core_completed ?? 0}/${component.core_total}` : '核心已就绪'
    if (phase === 'core_running') {
      return `${label} 核心 ${component.core_completed ?? 0}/${component.core_total ?? 0}，全市场后台待补`
    }
    const progress = component.progress ?? 0
    const remaining = component.remaining_count ?? 0
    const failed = component.failed_count ?? 0
    const current = component.current_symbol ? ` ${component.current_symbol}` : ''
    if (phase === 'market_backfill' && component.core_total) {
      return `${label} 核心完成；全市场 ${progress.toFixed(1)}% / 剩 ${remaining}${current}`
    }
    if (phase === 'market_backfill') {
      return `${label} ${coreReadyText}；全市场 ${progress.toFixed(1)}% / 剩 ${remaining}${current}`
    }
    return `${label} ${progress.toFixed(1)}% / 剩 ${remaining} / 失败 ${failed}${current}`
  }
  if (status === 'market_deferred') {
    const coreReadyText = component.core_total ? `核心完成 ${component.core_completed ?? 0}/${component.core_total}` : '核心已就绪'
    return `${label} ${coreReadyText}；非持仓全市场未补齐 ${component.remaining_count ?? 0}`
  }
  if (status === 'complete') return `${label} 完成 ${component.completed_count}/${component.total_symbols}`
  if (status === 'stale') return `${label} 滞后 ${component.completed_count}/${component.total_symbols}`
  if (status === 'partial_failed') return `${label} 部分失败 ${component.completed_count}/${component.total_symbols}`
  if (status === 'unavailable') return `${label} 不可用`
  return `${label} ${status || '--'}`
}

const coldDataLabel = computed(() => {
  if (coldDataError.value) return '冷数据状态离线'
  const components = coldDataStatus.value?.components
  if (components?.stock || components?.etf || components?.rotation) {
    return [
      formatColdComponent('股票', components.stock),
      formatColdComponent('ETF', components.etf),
      formatColdComponent('轮动', components.rotation),
    ].join(' | ')
  }
  return formatColdComponent('冷数据', coldDataStatus.value || undefined)
})

const openSuggestions = () => {
  refreshHistory()
  shouldFilterHistory.value = false
  showSuggestions.value = true
  activeIndex.value = -1
  fetchStockMatches()
}

const closeSuggestions = () => {
  showSuggestions.value = false
  activeIndex.value = -1
}

const selectSuggestion = (item: SearchSuggestion) => {
  symbol.value = item.symbol
  closeSuggestions()
  handleAnalyze()
}

const handleSearchInput = () => {
  shouldFilterHistory.value = true
  showSuggestions.value = true
  activeIndex.value = -1
  scheduleStockSearch()
}

const onKeydown = (e: KeyboardEvent) => {
  if (!showSuggestions.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (suggestions.value.length === 0) return
    activeIndex.value = (activeIndex.value + 1) % suggestions.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (suggestions.value.length === 0) return
    activeIndex.value = (activeIndex.value - 1 + suggestions.value.length) % suggestions.value.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIndex.value >= 0 && activeIndex.value < suggestions.value.length) {
      selectSuggestion(suggestions.value[activeIndex.value])
    } else {
      closeSuggestions()
      handleAnalyze()
    }
  } else if (e.key === 'Escape') {
    closeSuggestions()
  }
}

const handleClickOutside = (e: MouseEvent) => {
  if (searchContainerRef.value && !searchContainerRef.value.contains(e.target as Node)) {
    closeSuggestions()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  loadColdDataStatus()
  coldDataTimer = window.setInterval(loadColdDataStatus, 10000)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  if (coldDataTimer) window.clearInterval(coldDataTimer)
  if (stockSearchTimer) window.clearTimeout(stockSearchTimer)
})

const resolveInputSymbol = async () => {
  const term = symbol.value.trim()
  if (/^\d{6}$/.test(term)) return term

  const exactSuggestion = suggestions.value.find(
    (item) => item.name === term || item.symbol === term,
  )
  if (exactSuggestion) return exactSuggestion.symbol

  const matches = await searchStocks(term, 1)
  if (matches.length > 0) return matches[0].symbol

  throw new Error('未找到匹配的股票或ETF')
}

const handleAnalyze = async () => {
  activeView.value = 'discovery'
  discoveryMode.value = 'research'
  loading.value = true
  error.value = ''
  result.value = null
  closeSuggestions()

  try {
    const resolvedSymbol = await resolveInputSymbol()
    symbol.value = resolvedSymbol
    result.value = await analyzeStock(resolvedSymbol)
    if (result.value?.stocks?.[0]) {
      updateSearchHistory({
        symbol: result.value.stocks[0].symbol,
        name: result.value.stocks[0].name,
      })
      refreshHistory()
    }
  } catch (e: any) {
    error.value = `请求失败：${e.message || e}`
  } finally {
    loading.value = false
  }
}

const openResearchForSymbol = async (nextSymbol: string) => {
  symbol.value = nextSymbol
  activeView.value = 'discovery'
  discoveryMode.value = 'research'
  await handleAnalyze()
}

const openPortfolioImport = async (kind: 'current_holdings' | 'trade_history') => {
  portfolioImportKind.value = kind
  portfolioImportRequest.value += 1
  activeView.value = 'portfolio'
  await nextTick()
  portfolioPanelRef.value?.openImport(kind)
}

const openRotation = () => {
  activeView.value = 'discovery'
  discoveryMode.value = 'rotation'
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div class="mx-auto flex h-14 min-w-0 max-w-[1600px] items-center justify-between overflow-hidden px-3 sm:px-6">
        <div class="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto sm:gap-3">
          <div class="hidden h-9 w-9 items-center justify-center rounded-lg bg-primary/10 sm:flex">
            <svg class="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <span class="shrink-0 whitespace-nowrap text-sm font-semibold tracking-tight text-foreground sm:text-lg">Stock-Pilot</span>
          <button
            class="hidden rounded bg-secondary/60 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:bg-secondary hover:text-foreground sm:inline-flex"
            :title="`修改 API 地址：${API_BASE_URL}`"
            @click="apiSettingsOpen = true"
          >
            {{ APP_VERSION }} · API {{ API_BASE_LABEL }}
          </button>
          <nav class="ml-1 flex shrink-0 whitespace-nowrap rounded border border-border bg-card p-1 text-xs sm:ml-3">
            <button
              :class="['h-8 rounded px-3', activeView === 'dashboard' || activeView === 'review' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground']"
              @click="activeView = 'dashboard'"
            >
              驾驶舱
            </button>
            <button
              :class="['h-8 rounded px-3', activeView === 'portfolio' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground']"
              @click="activeView = 'portfolio'"
            >
              持仓与交易
            </button>
            <button
              :class="['h-8 rounded px-3', activeView === 'discovery' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground']"
              @click="openRotation"
            >
              发现与研究
            </button>
          </nav>
        </div>

        <div class="hidden min-w-0 items-center gap-4 text-xs xl:flex">
          <div class="flex min-w-0 items-center gap-2" :title="coldDataStatus?.updated_at || ''">
            <div :class="['h-2 w-2 shrink-0 rounded-full', coldDataDotClass]"></div>
            <span class="max-w-[720px] truncate text-muted-foreground">{{ coldDataLabel }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div
              :class="[
                'h-2 w-2 rounded-full',
                result?.stocks?.[0]?.hot_status === 'ready' ? 'bg-positive'
                  : result?.stocks?.[0]?.hot_status === 'stale' ? 'bg-warning'
                    : result?.stocks?.[0]?.hot_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground',
              ]"
            ></div>
            <span class="text-muted-foreground">Hot {{ result?.stocks?.[0]?.hot_status || '--' }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div
              :class="[
                'h-2 w-2 rounded-full',
                result?.stocks?.[0]?.cold_status === 'ready' ? 'bg-positive'
                  : result?.stocks?.[0]?.cold_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground',
              ]"
            ></div>
            <span class="text-muted-foreground">K线 {{ result?.stocks?.[0]?.cold_status || '--' }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div
              :class="[
                'h-2 w-2 rounded-full',
                result?.stocks?.[0]?.ai_status === 'ready' ? 'bg-positive'
                  : result?.stocks?.[0]?.ai_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground',
              ]"
            ></div>
            <span class="text-muted-foreground">AI {{ result?.stocks?.[0]?.ai_status || '--' }}</span>
          </div>
        </div>
      </div>
    </header>

    <div v-if="apiSettingsOpen" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 px-4" @click.self="apiSettingsOpen = false">
      <section class="w-full max-w-md rounded border border-border bg-card shadow-2xl">
        <div class="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 class="text-sm font-semibold text-foreground">API 连接设置</h2>
            <p class="mt-1 text-[11px] text-muted-foreground">输入端口（如 8000）或完整 API 地址。</p>
          </div>
          <button class="h-8 w-8 text-lg text-muted-foreground hover:text-foreground" title="关闭" @click="apiSettingsOpen = false">×</button>
        </div>
        <div class="space-y-3 px-4 py-4">
          <label class="block space-y-1">
            <span class="text-xs text-muted-foreground">后端地址</span>
            <input
              v-model="apiAddress"
              class="h-9 w-full rounded border border-border bg-background px-3 font-mono text-sm text-foreground outline-none focus:border-primary"
              placeholder="8000 或 http://127.0.0.1:8000"
              @keyup.enter="testApiConnection"
            />
          </label>
          <div class="text-[11px] text-muted-foreground">当前默认：{{ DEFAULT_API_BASE_URL }}</div>
          <div v-if="apiTestStatus" class="text-xs text-positive">{{ apiTestStatus }}</div>
          <div v-if="apiSettingsError" class="text-xs text-negative">{{ apiSettingsError }}</div>
        </div>
        <div class="flex flex-wrap justify-end gap-2 border-t border-border px-4 py-3">
          <button class="h-8 rounded border border-border px-3 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground" @click="restoreDefaultApi">
            恢复默认
          </button>
          <button class="h-8 rounded border border-border px-3 text-xs text-foreground hover:bg-secondary disabled:opacity-50" :disabled="apiTesting" @click="testApiConnection">
            {{ apiTesting ? '测试中…' : '测试连接' }}
          </button>
          <button class="h-8 rounded bg-primary px-3 text-xs text-primary-foreground hover:bg-primary/90" @click="applyApiSettings">
            保存并重载
          </button>
        </div>
      </section>
    </div>

    <main class="mx-auto max-w-[1600px] px-3 py-4 sm:px-6">
      <AccountDashboard v-show="activeView === 'dashboard'" @select-symbol="openResearchForSymbol">
        <template #intelligence>
          <CockpitBriefing
            @open-review="activeView = 'review'"
            @open-rotation="openRotation"
            @open-import="openPortfolioImport"
            @select-symbol="openResearchForSymbol"
          />
        </template>
      </AccountDashboard>

      <PortfolioPanel
        v-if="activeView === 'portfolio'"
        ref="portfolioPanelRef"
        :open-import-kind="portfolioImportKind"
        :open-import-request="portfolioImportRequest"
      />

      <section v-if="activeView === 'review'" class="space-y-4">
        <div class="flex items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <div class="text-xs text-muted-foreground">驾驶舱详情</div>
            <h1 class="mt-1 text-xl font-semibold text-foreground">AI 复盘与闭环记录</h1>
          </div>
          <button class="h-9 rounded border border-border px-3 text-xs text-foreground hover:bg-secondary" @click="activeView = 'dashboard'">
            返回驾驶舱
          </button>
        </div>
        <AgentReview />
      </section>

      <section v-if="activeView === 'discovery'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <h1 class="text-xl font-semibold text-foreground">发现与研究</h1>
            <p class="mt-1 text-xs text-muted-foreground">先发现值得核查的方向，再进入具体标的研究。</p>
          </div>
          <div class="inline-flex rounded border border-border bg-card p-1 text-xs">
            <button
              :class="['h-8 rounded px-3', discoveryMode === 'rotation' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary']"
              @click="discoveryMode = 'rotation'"
            >
              轮动机会
            </button>
            <button
              :class="['h-8 rounded px-3', discoveryMode === 'research' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary']"
              @click="discoveryMode = 'research'"
            >
              个股研究
            </button>
          </div>
        </div>

        <RotationRadar v-if="discoveryMode === 'rotation'" @select-symbol="openResearchForSymbol" />

        <template v-if="discoveryMode === 'research'">
      <div class="mb-6">
        <div class="flex items-center gap-3">
          <div ref="searchContainerRef" class="relative max-w-md flex-1">
            <svg class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              v-model="symbol"
              type="text"
              placeholder="输入股票或ETF代码/名称"
              :disabled="loading"
              class="h-12 w-full rounded-xl border border-border bg-card pl-11 pr-4 text-sm font-mono text-foreground placeholder:text-muted-foreground transition-all focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              @focus="openSuggestions"
              @click="openSuggestions"
              @input="handleSearchInput"
              @keydown="onKeydown"
            />
            <div
              v-if="showSuggestions && suggestions.length > 0"
              class="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
            >
              <div
                v-for="(item, idx) in suggestions"
                :key="item.symbol"
                :class="[
                  'flex cursor-pointer items-center justify-between px-4 py-2.5 transition-all',
                  idx === activeIndex ? 'bg-secondary/50' : 'hover:bg-secondary/50',
                ]"
                @click="selectSuggestion(item)"
              >
                <div class="flex min-w-0 items-center gap-2 text-sm">
                  <span class="font-mono font-medium text-foreground">{{ item.symbol }}</span>
                  <span class="truncate text-muted-foreground">{{ item.name }}</span>
                  <span v-if="item.industry" class="text-[11px] text-muted-foreground/60">{{ item.industry }}</span>
                </div>
                <span class="shrink-0 text-[11px] text-muted-foreground/70">
                  {{ item.source === 'history' ? `${item.count}次` : item.asset_type === 'etf' ? 'ETF' : '匹配' }}
                </span>
              </div>
            </div>
          </div>
          <button
            class="flex h-12 items-center gap-2 rounded-xl bg-primary px-6 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:bg-primary/90 disabled:opacity-50"
            :disabled="loading"
            @click="handleAnalyze"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {{ loading ? '分析中...' : '分析' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="py-4 text-center text-negative">{{ error }}</div>
      <div v-if="!result && !loading && !error" class="py-12 text-center text-muted-foreground">
        输入股票或ETF代码开始分析
      </div>

      <div v-if="result?.stocks?.length" class="flex flex-col gap-4 xl:flex-row">
        <div class="min-w-0 flex-1 space-y-4">
          <StockCard :stock="result.stocks[0]" />
          <PositionContextPanel :symbol="result.stocks[0].symbol" />
          <KLineChart :symbol="result.stocks[0].symbol" :indicators="result.stocks[0].indicators" />
          <AutoFactsPanel :symbol="result.stocks[0].symbol" />
          <AnalysisPacketPanel :symbol="result.stocks[0].symbol" />
        </div>
        <div class="w-full shrink-0 xl:w-[420px]">
          <DeepAnalysisPanel :symbol="result.stocks[0].symbol" />
        </div>
      </div>
      </template>
      </section>
    </main>
  </div>
</template>
