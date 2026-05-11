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
        data.value = normalizeCache(cache.data)
        status.value = 'success'
        analysisTime.value = cache.formattedTime || ''
      }
    } catch {
      // ignore invalid cache
    }
  }
}

// 兼容旧缓存：将旧字段映射到新结构
function normalizeCache(raw: any): DeepAnalysisResult {
  const d = raw as any

  // 兼容 key_price_levels：旧版是字符串数组
  let kpl = d.key_price_levels || []
  if (kpl.length > 0 && typeof kpl[0] === 'string') {
    kpl = kpl.map((item: string) => ({ price: 0, type: '', meaning: item }))
  }

  // 兼容 short/medium/long_term：旧版可能是字符串
  function normalizeTimeframe(val: any): any {
    if (typeof val === 'string') return { view: val, action: '' }
    return val || { view: '', action: '' }
  }

  return {
    trade_thesis: d.trade_thesis || '',
    trading_bias: d.trading_bias || d.market_state || '观望',
    strategy_type: d.strategy_type || '',
    trading_advice: d.trading_advice || '等待分析',
    confidence_score: d.confidence_score ?? d.win_rate ?? 50,
    odds_score: d.odds_score ?? 50,
    risk_level: d.risk_level || '中',
    bull_score: d.bull_score ?? 50,
    bear_score: d.bear_score ?? 50,
    key_drivers: d.key_drivers || [],
    key_price_levels: kpl,
    invalid_condition: d.invalid_condition || '',
    bullish_triggers: d.bullish_triggers || [],
    bearish_triggers: d.bearish_triggers || [],
    short_term: normalizeTimeframe(d.short_term),
    medium_term: normalizeTimeframe(d.medium_term),
    long_term: normalizeTimeframe(d.long_term),
    company_alpha: d.company_alpha || '',
    industry_beta: d.industry_beta || '',
    industry_analysis: d.industry_analysis || '',
    risk_factors: d.risk_factors || [],
    missing_data: d.missing_data || [],
    market_regime: d.market_regime || '',
    selected_models: d.selected_models || [],
    summary: d.summary || '',
    sector_capital_flow: d.sector_capital_flow || '',
    win_rate: d.win_rate,
    profit_loss_ratio: d.profit_loss_ratio,
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
      data.value = normalizeCache(result.data)
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
    errorMsg.value = e.response?.data?.detail || e.message || '网络错误'
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

function getTimeframeView(tf: any): string {
  if (typeof tf === 'string') return tf
  return tf?.view || '-'
}

function getTimeframeAction(tf: any): string {
  if (typeof tf === 'string') return ''
  return tf?.action || ''
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
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <span v-if="data.market_regime"
              class="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary font-medium">
              {{ data.market_regime }}
            </span>
            <span v-for="(m, i) in data.selected_models?.slice(0, 2)" :key="i"
              class="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
              {{ m }}
            </span>
          </div>

          <h4 class="text-sm font-semibold text-foreground mb-1">当前交易观点</h4>

          <div v-if="data.trade_thesis" class="text-xs text-muted-foreground mb-2 leading-relaxed">
            {{ data.trade_thesis }}
          </div>

          <div class="text-lg font-bold mb-2"
            :class="data.trading_bias.includes('多') ? 'text-red-500' : data.trading_bias.includes('空') ? 'text-green-500' : 'text-yellow-500'"
          >
            【{{ data.trading_advice }}】
          </div>

          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <span>偏向: <span class="font-semibold">{{ data.trading_bias }}</span></span>
            <span v-if="data.strategy_type">策略: <span class="font-semibold">{{ data.strategy_type }}</span></span>
            <span>信心: <span class="font-semibold">{{ data.confidence_score }}</span></span>
            <span>赔率: <span class="font-semibold">{{ data.odds_score }}</span></span>
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
        <div v-if="data.key_drivers?.length" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">核心驱动因素</h4>
          <ul class="space-y-1">
            <li v-for="(driver, idx) in data.key_drivers" :key="idx" class="text-xs flex items-start gap-1.5" :class="getDriverColor(driver)">
              <span class="mt-0.5">{{ driver.startsWith('▲') ? '▲' : driver.startsWith('▼') ? '▼' : '•' }}</span>
              {{ driver.replace(/^[▲▼]\s*/, '') }}
            </li>
          </ul>
        </div>

        <!-- 关键价格位（结构化） -->
        <div v-if="data.key_price_levels?.length" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">关键价格位</h4>
          <ul class="space-y-1.5">
            <li v-for="(lvl, idx) in data.key_price_levels" :key="idx" class="text-xs flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full"
                :class="lvl.type === '支撑' ? 'bg-green-500' : lvl.type === '压力' ? 'bg-red-500' : 'bg-blue-500'"></span>
              <span v-if="lvl.price" class="font-mono font-medium text-foreground">{{ lvl.price.toFixed(2) }}</span>
              <span v-if="lvl.type" class="text-[10px] px-1 rounded bg-secondary text-muted-foreground">{{ lvl.type }}</span>
              <span class="text-muted-foreground">{{ lvl.meaning }}</span>
            </li>
          </ul>
        </div>

        <!-- 触发条件 -->
        <div v-if="data.bullish_triggers?.length || data.bearish_triggers?.length"
          class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">触发条件</h4>
          <div v-if="data.bullish_triggers?.length" class="mb-2">
            <div class="text-[10px] text-red-500 mb-1">看多触发</div>
            <ul class="space-y-1">
              <li v-for="(t, i) in data.bullish_triggers" :key="i" class="text-xs text-muted-foreground flex items-start gap-1.5">
                <span class="text-red-500 mt-0.5">+</span>{{ t }}
              </li>
            </ul>
          </div>
          <div v-if="data.bearish_triggers?.length">
            <div class="text-[10px] text-green-500 mb-1">看空触发</div>
            <ul class="space-y-1">
              <li v-for="(t, i) in data.bearish_triggers" :key="i" class="text-xs text-muted-foreground flex items-start gap-1.5">
                <span class="text-green-500 mt-0.5">-</span>{{ t }}
              </li>
            </ul>
          </div>
        </div>

        <!-- 短线/中线/长线 -->
        <div class="grid grid-cols-3 gap-2">
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">短线</div>
            <div class="text-sm font-semibold"
              :class="getTimeframeView(data.short_term).includes('多') ? 'text-red-500' : getTimeframeView(data.short_term).includes('空') ? 'text-green-500' : 'text-yellow-500'"
            >
              {{ getTimeframeView(data.short_term) }}
            </div>
            <div v-if="getTimeframeAction(data.short_term)" class="text-[10px] text-muted-foreground mt-0.5">
              {{ getTimeframeAction(data.short_term) }}
            </div>
          </div>
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">中线</div>
            <div class="text-sm font-semibold"
              :class="getTimeframeView(data.medium_term).includes('多') ? 'text-red-500' : getTimeframeView(data.medium_term).includes('空') ? 'text-green-500' : 'text-yellow-500'"
            >
              {{ getTimeframeView(data.medium_term) }}
            </div>
            <div v-if="getTimeframeAction(data.medium_term)" class="text-[10px] text-muted-foreground mt-0.5">
              {{ getTimeframeAction(data.medium_term) }}
            </div>
          </div>
          <div class="rounded-lg bg-secondary/20 p-3 border border-border/50 text-center">
            <div class="text-xs text-muted-foreground mb-1">长线</div>
            <div class="text-sm font-semibold"
              :class="getTimeframeView(data.long_term).includes('多') ? 'text-red-500' : getTimeframeView(data.long_term).includes('空') ? 'text-green-500' : 'text-yellow-500'"
            >
              {{ getTimeframeView(data.long_term) }}
            </div>
            <div v-if="getTimeframeAction(data.long_term)" class="text-[10px] text-muted-foreground mt-0.5">
              {{ getTimeframeAction(data.long_term) }}
            </div>
          </div>
        </div>

        <!-- Alpha / Beta 拆分 -->
        <div v-if="data.company_alpha || data.industry_beta" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">Alpha / Beta 拆分</h4>
          <div v-if="data.company_alpha" class="mb-2">
            <div class="text-[10px] text-primary mb-0.5">公司 Alpha</div>
            <p class="text-xs text-muted-foreground leading-relaxed">{{ data.company_alpha }}</p>
          </div>
          <div v-if="data.industry_beta">
            <div class="text-[10px] text-primary mb-0.5">行业 Beta</div>
            <p class="text-xs text-muted-foreground leading-relaxed">{{ data.industry_beta }}</p>
          </div>
        </div>

        <!-- 失效条件 -->
        <div v-if="data.invalid_condition" class="rounded-lg bg-yellow-500/10 p-3 border border-yellow-500/20">
          <h4 class="text-sm font-semibold text-yellow-400 mb-1">交易假设失效条件</h4>
          <p class="text-xs text-muted-foreground leading-relaxed">{{ data.invalid_condition }}</p>
        </div>

        <!-- 数据缺口 -->
        <div v-if="data.missing_data?.length" class="rounded-lg bg-blue-500/10 p-3 border border-blue-500/20">
          <h4 class="text-sm font-semibold text-blue-400 mb-2">数据缺口</h4>
          <ul class="space-y-1">
            <li v-for="(item, idx) in data.missing_data" :key="idx" class="text-xs text-muted-foreground flex items-start gap-1.5">
              <span class="text-blue-500 mt-0.5">?</span>{{ item }}
            </li>
          </ul>
        </div>

        <!-- 行业资金观察（兼容旧字段） -->
        <div v-if="data.sector_capital_flow" class="rounded-lg bg-secondary/20 p-3 border border-border/50">
          <h4 class="text-sm font-semibold text-foreground mb-2">行业资金观察</h4>
          <p class="text-xs text-muted-foreground leading-relaxed">{{ data.sector_capital_flow }}</p>
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
          <p class="text-xs text-foreground/80 leading-relaxed">{{ data.summary }}</p>
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
