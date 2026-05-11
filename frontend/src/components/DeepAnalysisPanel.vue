<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { deepAnalyze, type DeepAnalysisResult } from '../api/deepAnalyze'

const props = defineProps<{
  symbol: string
}>()

type Status = 'idle' | 'loading' | 'success' | 'error'

const status = ref<Status>('idle')
const data = ref<DeepAnalysisResult | null>(null)
const errorMsg = ref('')
const analysisTime = ref('')

const resetState = () => {
  status.value = 'idle'
  data.value = null
  errorMsg.value = ''
  analysisTime.value = ''
}

const loadCache = () => {
  const cacheKey = `stock-pilot-deep-analysis-${props.symbol}`
  const raw = localStorage.getItem(cacheKey)
  if (raw) {
    try {
      const cache = JSON.parse(raw)
      if (cache && cache.data) {
        data.value = cache.data
        status.value = 'success'
        analysisTime.value = cache.formattedTime || ''
      }
    } catch {
      // ignore invalid cache
    }
  }
}

const startDeepAnalysis = async () => {
  if (!props.symbol) return

  status.value = 'loading'
  errorMsg.value = ''
  analysisTime.value = ''

  try {
    const result = await deepAnalyze(props.symbol)
    if (result.success && result.data) {
      data.value = result.data
      status.value = 'success'

      const now = new Date()
      const cacheData = {
        symbol: props.symbol,
        timestamp: now.getTime(),
        formattedTime: now.toLocaleString('zh-CN'),
        data: result.data
      }
      localStorage.setItem(
        `stock-pilot-deep-analysis-${props.symbol}`,
        JSON.stringify(cacheData)
      )
    } else {
      errorMsg.value = result.message || '分析失败'
      status.value = 'error'
    }
  } catch (e: any) {
    errorMsg.value = e.message || '网络错误'
    status.value = 'error'
  }
}

watch(() => props.symbol, () => {
  resetState()
  loadCache()
})

onMounted(() => {
  resetState()
  loadCache()
})

function getRiskColor(level: string): string {
  if (level === '低') return 'text-green-500'
  if (level === '中') return 'text-yellow-500'
  if (level === '高') return 'text-red-500'
  return 'text-gray-500'
}

function getDriverColor(driver: string): string {
  if (driver.startsWith('▲')) return 'text-red-500'
  if (driver.startsWith('▼')) return 'text-green-500'
  return 'text-gray-400'
}
</script>

<template>
  <div class="rounded-lg border border-border bg-card p-4 flex flex-col h-[calc(100vh-120px)] overflow-hidden">
    <!-- Header -->
    <div class="mb-3">
      <h3 class="text-lg font-semibold text-foreground">AI 深度分析</h3>
      <p class="text-xs text-muted-foreground">
        {{ symbol }} · AI交易推演
      </p>
      <div v-if="analysisTime" class="text-[11px] text-muted-foreground mt-1">
        上次分析: {{ analysisTime }}
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto space-y-3 pr-1">
      <!-- Idle State -->
      <div v-if="status === 'idle'" class="flex flex-col items-center justify-center h-full py-12 text-center">
        <div class="text-muted-foreground mb-2">尚未启动AI深度分析</div>
        <p class="text-xs text-muted-foreground/70 max-w-xs mb-4">
          点击生成交易决策观点，3秒读懂当前是否适合买入
        </p>
      </div>

      <!-- Loading State -->
      <div v-else-if="status === 'loading'" class="flex flex-col items-center justify-center h-full py-12">
        <div class="animate-pulse text-sm text-foreground mb-2">AI正在推演交易策略...</div>
        <p class="text-xs text-muted-foreground/70">分析多空力量与关键价位</p>
      </div>

      <!-- Error State -->
      <div v-else-if="status === 'error'" class="flex flex-col items-center justify-center h-full py-12 text-center">
        <div class="text-red-500 mb-2">分析失败</div>
        <p class="text-xs text-muted-foreground mb-4">{{ errorMsg }}</p>
        <button
          @click="startDeepAnalysis"
          class="py-2 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all"
        >
          重试
        </button>
      </div>

      <!-- Success State -->
      <template v-else-if="status === 'success' && data">
        <!-- 当前交易观点 -->
        <div class="rounded-lg bg-primary/10 p-4 border border-primary/20">
          <h4 class="text-sm font-semibold text-foreground mb-2">当前交易观点</h4>
          <div class="text-lg font-bold mb-3" :class="data.trading_bias.includes('多') ? 'text-red-500' : data.trading_bias.includes('空') ? 'text-green-500' : 'text-yellow-500'">
            【{{ data.trading_advice }}】
          </div>

          <div class="flex items-center gap-4 text-xs">
            <span>胜率: <span class="font-semibold">{{ data.win_rate }}%</span></span>
            <span>盈亏比: <span class="font-semibold">{{ data.profit_loss_ratio }}</span></span>
            <span>风险: <span :class="getRiskColor(data.risk_level)" class="font-semibold">{{ data.risk_level }}</span></span>
          </div>
        </div>

        <!-- 多空力量对比 -->
        <div class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-3">多空力量对比</h4>

          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs text-red-500 w-8">多头</span>
            <div class="h-2 rounded bg-secondary overflow-hidden flex-1">
              <div class="h-full bg-red-500" :style="{ width: data.bull_score + '%' }"></div>
            </div>
            <span class="text-xs font-semibold text-red-500 w-8">{{ data.bull_score }}</span>
          </div>

          <div class="flex items-center gap-2">
            <span class="text-xs text-green-500 w-8">空头</span>
            <div class="h-2 rounded bg-secondary overflow-hidden flex-1">
              <div class="h-full bg-green-500" :style="{ width: data.bear_score + '%' }"></div>
            </div>
            <span class="text-xs font-semibold text-green-500 w-8">{{ data.bear_score }}</span>
          </div>
        </div>

        <!-- 核心驱动因素 -->
        <div class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">核心驱动因素</h4>
          <ul class="space-y-1">
            <li v-for="(driver, idx) in data.key_drivers" :key="idx" class="text-xs flex items-start gap-1.5" :class="getDriverColor(driver)">
              <span class="mt-0.5">{{ driver.startsWith('▲') ? '▲' : driver.startsWith('▼') ? '▼' : '•' }}</span>
              {{ driver.replace(/^[▲▼]\s*/, '') }}
            </li>
          </ul>
        </div>

        <!-- 短线/中线/长线 -->
        <div class="grid grid-cols-3 gap-2">
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">短线</div>
            <div class="text-sm font-semibold" :class="data.short_term.includes('多') ? 'text-red-500' : data.short_term.includes('空') ? 'text-green-500' : 'text-yellow-500'">
              {{ data.short_term }}
            </div>
          </div>
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">中线</div>
            <div class="text-sm font-semibold" :class="data.medium_term.includes('多') ? 'text-red-500' : data.medium_term.includes('空') ? 'text-green-500' : 'text-yellow-500'">
              {{ data.medium_term }}
            </div>
          </div>
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">长线</div>
            <div class="text-sm font-semibold" :class="data.long_term.includes('多') ? 'text-red-500' : data.long_term.includes('空') ? 'text-green-500' : 'text-yellow-500'">
              {{ data.long_term }}
            </div>
          </div>
        </div>

        <!-- 行业资金观察 -->
        <div v-if="data.sector_capital_flow" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">行业资金观察</h4>
          <p class="text-xs text-muted-foreground leading-relaxed">
            {{ data.sector_capital_flow }}
          </p>
        </div>

        <!-- 关键价格位 -->
        <div v-if="data.key_price_levels?.length" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">关键价格位</h4>
          <ul class="space-y-1">
            <li v-for="(level, idx) in data.key_price_levels" :key="idx" class="text-xs text-muted-foreground flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
              {{ level }}
            </li>
          </ul>
        </div>

        <!-- 风险提示 -->
        <div v-if="data.risk_factors?.length" class="rounded-lg bg-red-500/10 p-3 border border-red-500/20">
          <h4 class="text-sm font-semibold text-red-400 mb-2">风险提示</h4>
          <ul class="space-y-1">
            <li v-for="(risk, idx) in data.risk_factors" :key="idx" class="text-xs text-muted-foreground flex items-start gap-1.5">
              <span class="text-red-500 mt-0.5">•</span>
              {{ risk }}
            </li>
          </ul>
        </div>

        <!-- 总结 -->
        <div v-if="data.summary" class="rounded-lg bg-primary/5 p-3 border border-primary/10">
          <p class="text-xs text-foreground/80 leading-relaxed">
            {{ data.summary }}
          </p>
        </div>
      </template>
    </div>

    <!-- Action -->
    <div class="mt-3 pt-3 border-t border-border/50">
      <button
        @click="startDeepAnalysis"
        :disabled="status === 'loading'"
        class="w-full py-2.5 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all disabled:opacity-50"
      >
        {{ status === 'loading' ? '分析中...' : analysisTime ? '重新分析' : '开始AI深度分析' }}
      </button>
    </div>
  </div>
</template>