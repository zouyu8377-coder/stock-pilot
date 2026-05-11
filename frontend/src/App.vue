<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { analyzeStock, type AnalyzeResponse } from './api/client'
import StockCard from './components/StockCard.vue'
import DeepAnalysisPanel from './components/DeepAnalysisPanel.vue'
import KLineChart from './components/KLineChart.vue'
import IntradayChart from './components/IntradayChart.vue'
import { getSearchHistory, updateSearchHistory, type SearchHistoryItem } from './utils/searchHistory'

const symbol = ref('600519')
const loading = ref(false)
const result = ref<AnalyzeResponse | null>(null)
const error = ref('')

const showSuggestions = ref(false)
const activeIndex = ref(-1)
const searchContainerRef = ref<HTMLElement | null>(null)

const allHistory = ref<SearchHistoryItem[]>([])

const suggestions = computed(() => {
  const term = symbol.value.trim()
  if (!term) return allHistory.value
  return allHistory.value.filter(
    (item) =>
      item.symbol.includes(term) || item.name.includes(term)
  )
})

const refreshHistory = () => {
  allHistory.value = getSearchHistory()
}

const openSuggestions = () => {
  refreshHistory()
  showSuggestions.value = true
  activeIndex.value = -1
}

const closeSuggestions = () => {
  showSuggestions.value = false
  activeIndex.value = -1
}

const selectSuggestion = (item: SearchHistoryItem) => {
  symbol.value = item.symbol
  closeSuggestions()
  handleAnalyze()
}

const onKeydown = (e: KeyboardEvent) => {
  if (!showSuggestions.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % suggestions.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
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
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

const handleAnalyze = async () => {
  loading.value = true
  error.value = ''
  result.value = null
  closeSuggestions()

  try {
    result.value = await analyzeStock(symbol.value)
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
        <div class="flex items-center gap-4 text-xs" v-if="result?.stocks?.[0]">
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result.stocks[0].hot_status === 'ready' ? 'bg-positive' :
              result.stocks[0].hot_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-negative'
            ]"></div>
            <span class="text-muted-foreground">Hot {{ result.stocks[0].hot_status }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result.stocks[0].cold_status === 'ready' ? 'bg-positive' :
              result.stocks[0].cold_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-negative'
            ]"></div>
            <span class="text-muted-foreground">Cold {{ result.stocks[0].cold_status }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div :class="[
              'h-2 w-2 rounded-full',
              result.stocks[0].ai_status === 'ready' ? 'bg-positive' :
              result.stocks[0].ai_status === 'loading' ? 'bg-warning animate-pulse' : 'bg-negative'
            ]"></div>
            <span class="text-muted-foreground">AI {{ result.stocks[0].ai_status }}</span>
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
              placeholder="输入股票代码..."
              :disabled="loading"
              @focus="openSuggestions"
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
                </div>
                <span class="text-[11px] text-muted-foreground/70">{{ item.count }}次</span>
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
          <IntradayChart :symbol="result.stocks[0].symbol" />
        </div>

        <!-- Right Column: Fixed Width DeepAnalysisPanel -->
        <div class="w-[420px] shrink-0">
          <DeepAnalysisPanel :symbol="result.stocks[0].symbol" />
        </div>
      </div>
    </main>
  </div>
</template>