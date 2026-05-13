<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { analyzeStock, getColdDataStatus, searchStocks, type AnalyzeResponse, type ColdDataStatus, type StockSearchItem } from './api/client'
import StockCard from './components/StockCard.vue'
import DeepAnalysisPanel from './components/DeepAnalysisPanel.vue'
import KLineChart from './components/KLineChart.vue'
import AnalysisPromptPanel from './components/AnalysisPromptPanel.vue'
import { getSearchHistory, updateSearchHistory, type SearchHistoryItem } from './utils/searchHistory'

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
      name: item.name || item.symbol || '未知股票',
      source: 'history' as const,
      industry: undefined,
      area: undefined,
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
  if (stockSearchTimer) {
    window.clearTimeout(stockSearchTimer)
  }
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
  const status = coldDataStatus.value?.status
  if (status === 'running' || status === 'checking') return 'bg-warning animate-pulse'
  if (status === 'complete') return 'bg-positive'
  if (status === 'partial_failed') return 'bg-warning'
  return 'bg-muted-foreground'
})

const coldDataLabel = computed(() => {
  if (coldDataError.value) return '冷数据状态离线'
  const status = coldDataStatus.value?.status
  if (!status) return '冷数据 --'
  if (status === 'checking') return '冷数据检查中'
  if (status === 'running') {
    const progress = coldDataStatus.value?.progress ?? 0
    const remaining = coldDataStatus.value?.remaining_count ?? 0
    const current = coldDataStatus.value?.current_symbol
    return `冷数据更新 ${progress.toFixed(1)}% · 剩余 ${remaining}${current ? ` · ${current}` : ''}`
  }
  if (status === 'complete') {
    return `冷数据已就绪 · ${coldDataStatus.value?.target_date ?? '-'}`
  }
  if (status === 'partial_failed') {
    const failed = coldDataStatus.value?.failed_count ?? 0
    const remaining = coldDataStatus.value?.remaining_count ?? 0
    return `冷数据部分失败 · 失败 ${failed} · 剩余 ${remaining}`
  }
  return `冷数据 ${status}`
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
    activeIndex.value =
      (activeIndex.value - 1 + suggestions.value.length) % suggestions.value.length
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
  if (
    searchContainerRef.value &&
    !searchContainerRef.value.contains(e.target as Node)
  ) {
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
  if (coldDataTimer) {
    window.clearInterval(coldDataTimer)
  }
  if (stockSearchTimer) {
    window.clearTimeout(stockSearchTimer)
  }
})

const resolveInputSymbol = async () => {
  const term = symbol.value.trim()
  if (/^\d{6}$/.test(term)) return term

  const exactSuggestion = suggestions.value.find(
    (item) => item.name === term || item.symbol === term
  )
  if (exactSuggestion) return exactSuggestion.symbol

  const matches = await searchStocks(term, 1)
  if (matches.length > 0) return matches[0].symbol

  throw new Error('未找到匹配的股票')
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
    <!-- Header -->
    <header class="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div class="mx-auto flex h-14 max-w-[1600px] items-center justify-between px-6">
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <svg class="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <span class="text-lg font-semibold tracking-tight text-foreground">
            Stock-Pilot
          </span>
        </div>

        <!-- Status indicators -->
        <div class="flex items-center gap-4 text-xs">
          <div class="flex items-center gap-2" :title="coldDataStatus?.updated_at || ''">
            <div :class="[
              'h-2 w-2 rounded-full',
              coldDataDotClass
            ]"></div>
            <span class="text-muted-foreground">{{ coldDataLabel }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result?.stocks?.[0]?.hot_status === 'ready' ? 'bg-positive' :
              result?.stocks?.[0]?.hot_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground'
            ]"></div>
            <span class="text-muted-foreground">Hot {{ result?.stocks?.[0]?.hot_status || '--' }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result?.stocks?.[0]?.cold_status === 'ready' ? 'bg-positive' :
              result?.stocks?.[0]?.cold_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground'
            ]"></div>
            <span class="text-muted-foreground">查询 {{ result?.stocks?.[0]?.cold_status || '--' }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result?.stocks?.[0]?.ai_status === 'ready' ? 'bg-positive' :
              result?.stocks?.[0]?.ai_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-muted-foreground'
            ]"></div>
            <span class="text-muted-foreground">AI {{ result?.stocks?.[0]?.ai_status || '--' }}</span>
          </div>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-[1600px] px-6 py-4">
      <!-- Search Section -->
      <div class="mb-6">
        <div class="flex items-center gap-3">
          <div ref="searchContainerRef" class="relative flex-1 max-w-md">
            <svg class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              v-model="symbol"
              type="text"
              placeholder="输入股票代码或名称..."
              :disabled="loading"
              @focus="openSuggestions"
              @click="openSuggestions"
              @input="handleSearchInput"
              @keydown="onKeydown"
              class="h-12 w-full rounded-xl border border-border bg-card pl-11 pr-4 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
            />
            <!-- Search Suggestions -->
            <div
              v-if="showSuggestions && suggestions.length > 0"
              class="absolute top-full left-0 right-0 mt-2 rounded-xl border border-border bg-card shadow-2xl z-50 overflow-hidden"
            >
              <div
                v-for="(item, idx) in suggestions"
                :key="item.symbol"
                @click="selectSuggestion(item)"
                :class="[
                  'flex items-center justify-between px-4 py-2.5 cursor-pointer transition-all',
                  idx === activeIndex ? 'bg-secondary/50' : 'hover:bg-secondary/50'
                ]"
              >
                <div class="flex items-center gap-2 text-sm">
                  <span class="font-mono font-medium text-foreground">{{ item.symbol }}</span>
                  <span class="text-muted-foreground">{{ item.name }}</span>
                  <span v-if="item.industry" class="text-[11px] text-muted-foreground/60">{{ item.industry }}</span>
                </div>
                <span class="text-[11px] text-muted-foreground/70">
                  {{ item.source === 'history' ? `${item.count}次` : '匹配' }}
                </span>
              </div>
            </div>
          </div>
          <button
            @click="handleAnalyze"
            :disabled="loading"
            class="h-12 px-6 rounded-xl bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 disabled:opacity-50 transition-all flex items-center gap-2 shadow-lg shadow-primary/20"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {{ loading ? '分析中...' : '分析' }}
          </button>
        </div>
      </div>

      <!-- Error message -->
      <div v-if="error" class="text-center text-negative py-4">
        {{ error }}
      </div>

      <!-- Hint -->
      <div v-if="!result && !loading && !error" class="text-center text-muted-foreground py-12">
        请输入股票代码开始分析
      </div>

      <!-- Main Layout: Left Column + Right Fixed Panel -->
      <div v-if="result?.stocks?.length" class="flex gap-4">
        <!-- Left Column: StockCard + Charts -->
        <div class="flex-1 min-w-0 space-y-4">
          <StockCard :stock="result.stocks[0]" />
          <KLineChart
            :symbol="result.stocks[0].symbol"
            :indicators="result.stocks[0].indicators"
          />
          <AnalysisPromptPanel :symbol="result.stocks[0].symbol" />
        </div>

        <!-- Right Column: Fixed Width DeepAnalysisPanel -->
        <div class="w-[420px] shrink-0">
          <DeepAnalysisPanel :symbol="result.stocks[0].symbol" />
        </div>
      </div>
    </main>
  </div>
</template>
