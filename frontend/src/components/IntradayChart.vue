<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { createChart, CandlestickSeries, HistogramSeries, ColorType, CrosshairMode } from 'lightweight-charts'

const props = defineProps<{
  symbol: string
}>()

const chartContainer = ref<HTMLElement | null>(null)
const hasData = ref(false)
let chart: any = null
let candleSeries: any = null
let volumeSeries: any = null

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// 解析后端时间字符串 "YYYY-MM-DD HH:mm:ss" 为 Unix timestamp (seconds)
function parseTime(timeStr: string): number {
  const d = new Date(timeStr.replace(' ', 'T') + '+08:00')
  return Math.floor(d.getTime() / 1000)
}

// 将 UTC 秒级时间戳格式化为北京时间 HH:mm
function formatBJTime(timestamp: number): string {
  const d = new Date((timestamp + 8 * 3600) * 1000)
  const hh = d.getUTCHours().toString().padStart(2, '0')
  const mm = d.getUTCMinutes().toString().padStart(2, '0')
  return `${hh}:${mm}`
}

// 将 UTC 秒级时间戳格式化为北京时间 "M月D日 HH:MM"
function formatBJDateTime(timestamp: number): string {
  const d = new Date((timestamp + 8 * 3600) * 1000)
  const month = d.getUTCMonth() + 1
  const day = d.getUTCDate()
  const hh = d.getUTCHours().toString().padStart(2, '0')
  const mm = d.getUTCMinutes().toString().padStart(2, '0')
  return `${month}月${day}日 ${hh}:${mm}`
}

async function fetchIntradayData(): Promise<any[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/intraday/${props.symbol}`)
    const rawData = await response.json()
    return rawData
  } catch (error) {
    console.error('[INTRADAY] Fetch error:', error)
    return []
  }
}

function convertData(data: any[]) {
  const candles: any[] = []
  const volumes: any[] = []

  for (const item of data) {
    const time = parseTime(item.time)
    const open = item.open
    const close = item.close
    const isUp = close >= open

    candles.push({
      time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })

    volumes.push({
      time,
      value: item.volume,
      color: isUp ? '#ef4444' : '#22c55e',
    })
  }

  return { candles, volumes }
}

function destroyChart() {
  if (chart) {
    chart.remove()
    chart = null
    candleSeries = null
    volumeSeries = null
  }
}

async function buildChart() {
  const data = await fetchIntradayData()

  if (data.length === 0) {
    hasData.value = false
    destroyChart()
    return
  }

  hasData.value = true
  const { candles, volumes } = convertData(data)

  // 彻底重建，避免旧数据残留
  destroyChart()

  await nextTick()
  if (!chartContainer.value) {
    setTimeout(buildChart, 100)
    return
  }

  const containerWidth = chartContainer.value.clientWidth

  chart = createChart(chartContainer.value, {
    layout: {
      background: { type: ColorType.Solid, color: '#132544' },
      textColor: '#94a3b8',
    },
    grid: {
      vertLines: { color: '#1e3a5f' },
      horzLines: { color: '#1e3a5f' },
    },
    width: containerWidth,
    height: 280,
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: {
        color: '#94a3b8',
        width: 1,
        style: 2,
        labelBackgroundColor: '#0f3460',
      },
      horzLine: {
        color: '#94a3b8',
        width: 1,
        style: 2,
        labelBackgroundColor: '#0f3460',
      },
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (time: number) => formatBJTime(time),
    },
    localization: {
      locale: 'zh-CN',
      timeFormatter: (time: number) => formatBJDateTime(time),
    },
    rightPriceScale: {
      scaleMargins: {
        top: 0.1,
        bottom: 0.2,
      },
    },
  })

  // 蜡烛图（A股：涨红跌绿）
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#22c55e',
    borderUpColor: '#ef4444',
    borderDownColor: '#22c55e',
    wickUpColor: '#ef4444',
    wickDownColor: '#22c55e',
  })
  candleSeries.setData(candles)

  // 成交量柱
  volumeSeries = chart.addSeries(HistogramSeries, {
    color: '#26a69a',
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.85,
      bottom: 0,
    },
  })
  volumeSeries.setData(volumes)

  chart.timeScale().fitContent()
}

function handleResize() {
  if (chart && chartContainer.value) {
    chart.applyOptions({ width: chartContainer.value.clientWidth })
  }
}

onMounted(() => {
  setTimeout(buildChart, 100)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  destroyChart()
  window.removeEventListener('resize', handleResize)
})

watch(() => props.symbol, async () => {
  await buildChart()
})
</script>

<template>
  <div class="rounded-xl border border-border bg-card overflow-hidden">
    <div class="flex items-center gap-2 px-4 py-2 border-b border-border bg-secondary/30">
      <h3 class="text-sm font-semibold text-foreground">当日分时</h3>
    </div>
    <div ref="chartContainer" class="w-full h-[280px] flex items-center justify-center">
      <div v-if="!hasData" class="text-muted-foreground text-sm">
        暂无分时数据
      </div>
    </div>
  </div>
</template>
