<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { API_BASE_URL, analyzeStock, getColdDataStatus, searchStocks, type AnalyzeResponse, type ColdDataStatus, type StockSearchItem } from './api/client'
import StockCard from './components/StockCard.vue'
import DeepAnalysisPanel from './components/DeepAnalysisPanel.vue'
import KLineChart from './components/KLineChart.vue'
import AutoFactsPanel from './components/AutoFactsPanel.vue'
import AnalysisPacketPanel from './components/AnalysisPacketPanel.vue'
import PortfolioPanel from './components/PortfolioPanel.vue'
import { getSearchHistory, updateSearchHistory, type SearchHistoryItem } from './utils/searchHistory'
import { APP_VERSION } from './version'

const symbol = ref('600519')
const loading = ref(false)
const result = ref<AnalyzeResponse | null>(null)
const error = ref('')
const coldDataStatus = ref<ColdDataStatus | null>(null)
const coldDataError = ref(false)
let coldDataTimer: number | undefined

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
  ].filter(Boolean)
  if (statuses.some((status) => status === 'running' || status === 'checking')) return 'bg-warning animate-pulse'
  if (statuses.some((status) => status === 'partial_failed' || status === 'unavailable')) return 'bg-warning'
  if (statuses.length > 0 && statuses.every((status) => status === 'complete')) return 'bg-positive'
  return 'bg-muted-foreground'
})

const formatColdComponent = (label: string, component?: ColdDataStatus) => {
  if (!component) return `${label} --`
  const status = component.status
  if (status === 'running' || status === 'checking') {
    const progress = component.progress ?? 0
    const remaining = component.remaining_count ?? 0
    const failed = component.failed_count ?? 0
    const current = component.current_symbol ? ` ${component.current_symbol}` : ''
    return `${label} ${progress.toFixed(1)}% / 剩 ${remaining} / 失败 ${failed}${current}`
  }
  if (status === 'complete') return `${label} 完成 ${component.completed_count}/${component.total_symbols}`
  if (status === 'partial_failed') return `${label} 部分失败 ${component.completed_count}/${component.total_symbols}`
  if (status === 'unavailable') return `${label} 不可用`
  return `${label} ${status || '--'}`
}

const coldDataLabel = computed(() => {
  if (coldDataError.value) return '冷数据状态离线'
  const components = coldDataStatus.value?.components
  if (components?.stock || components?.etf) {
    return [
      formatColdComponent('股票', components.stock),
      formatColdComponent('ETF', components.etf),
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
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div class="mx-auto flex h-14 max-w-[1600px] items-center justify-between px-6">
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <svg class="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <span class="text-lg font-semibold tracking-tight text-foreground">Stock-Pilot</span>
          <span class="rounded bg-secondary/60 px-2 py-0.5 text-[11px] font-mono text-muted-foreground" :title="`API ${API_BASE_URL}`">
            {{ APP_VERSION }} · API {{ API_BASE_URL.replace('http://127.0.0.1:', ':') }}
          </span>
        </div>

        <div class="flex min-w-0 items-center gap-4 text-xs">
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

    <main class="mx-auto max-w-[1600px] px-6 py-4">
      <PortfolioPanel />
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

      <div v-if="result?.stocks?.length" class="flex gap-4">
        <div class="min-w-0 flex-1 space-y-4">
          <StockCard :stock="result.stocks[0]" />
          <KLineChart :symbol="result.stocks[0].symbol" :indicators="result.stocks[0].indicators" />
          <AutoFactsPanel :symbol="result.stocks[0].symbol" />
          <AnalysisPacketPanel :symbol="result.stocks[0].symbol" />
        </div>
        <div class="w-[420px] shrink-0">
          <DeepAnalysisPanel :symbol="result.stocks[0].symbol" />
        </div>
      </div>
    </main>
  </div>
</template>
