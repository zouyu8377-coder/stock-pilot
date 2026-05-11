<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { createChart, CandlestickSeries, LineSeries, ColorType } from 'lightweight-charts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const props = defineProps<{
  symbol: string
  indicators?: {
    ma5?: number
    ma10?: number
    ma20?: number
    ma30?: number
    ma60?: number
    rsi14?: number
    macd?: number
  }
}>()

const chartContainer = ref<HTMLElement | null>(null)

let chart: any = null
let candleSeries: any = null
let ma5Series: any = null
let ma10Series: any = null
let ma20Series: any = null
let ma30Series: any = null
let ma60Series: any = null

interface KLineData {
  date: string
  time: string
  open: number
  high: number
  low: number
  close: number
  ma5?: number | null
  ma10?: number | null
  ma20?: number | null
  ma30?: number | null
  ma60?: number | null
}

async function fetchKLineData(): Promise<KLineData[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/history/${props.symbol}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('[KLINE] Fetch error:', error)
    return []
  }
}

async function initChart() {
  await nextTick()

  if (!chartContainer.value) {
    setTimeout(initChart, 100)
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
    height: 400,
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
    },
    rightPriceScale: {
      visible: true,
    },
  })

  // Candlestick - A股红涨绿跌
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#22c55e',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#22c55e',
  })

  // MA lines - hide price labels and lines
  ma5Series = chart.addSeries(LineSeries, {
    color: '#facc15',
    lineWidth: 1.5,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  ma10Series = chart.addSeries(LineSeries, {
    color: '#22c55e',
    lineWidth: 1.5,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  ma20Series = chart.addSeries(LineSeries, {
    color: '#3b82f6',
    lineWidth: 1.5,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  ma30Series = chart.addSeries(LineSeries, {
    color: '#a855f7',
    lineWidth: 1.5,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  ma60Series = chart.addSeries(LineSeries, {
    color: '#ef4444',
    lineWidth: 1.5,
    lastValueVisible: false,
    priceLineVisible: false,
  })

  const data = await fetchKLineData()

  if (data.length > 0) {
    const candleData = data.map((d: KLineData) => ({
      time: d.date, open: d.open, high: d.high, low: d.low, close: d.close
    }))
    candleSeries.setData(candleData)

    ma5Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma5 })).filter((d: any) => d.value))
    ma10Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma10 })).filter((d: any) => d.value))
    ma20Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma20 })).filter((d: any) => d.value))
    ma30Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma30 })).filter((d: any) => d.value))
    ma60Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma60 })).filter((d: any) => d.value))

    // Show last 80 bars by default (approx 4 months)
    const visibleBars = 80
    const lastIndex = candleData.length - 1
    const startIndex = Math.max(0, lastIndex - visibleBars)
    chart.timeScale().setVisibleRange({
      from: candleData[startIndex].time,
      to: candleData[lastIndex].time,
    })
  }
}

function handleResize() {
  if (chart && chartContainer.value) {
    chart.applyOptions({ width: chartContainer.value.clientWidth })
  }
}

onMounted(() => {
  setTimeout(initChart, 100)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (chart) {
    chart.remove()
    chart = null
  }
  window.removeEventListener('resize', handleResize)
})

watch(() => props.symbol, async () => {
  if (chart) {
    const data = await fetchKLineData()
    if (data.length > 0) {
      const candleData = data.map((d: KLineData) => ({ time: d.date, open: d.open, high: d.high, low: d.low, close: d.close }))
      candleSeries.setData(candleData)
      ma5Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma5 })).filter((d: any) => d.value))
      ma10Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma10 })).filter((d: any) => d.value))
      ma20Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma20 })).filter((d: any) => d.value))
      ma30Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma30 })).filter((d: any) => d.value))
      ma60Series.setData(data.map((d: KLineData) => ({ time: d.date, value: d.ma60 })).filter((d: any) => d.value))
      const visibleBars = 80
      const lastIndex = candleData.length - 1
      const startIndex = Math.max(0, lastIndex - visibleBars)
      chart.timeScale().setVisibleRange({
        from: candleData[startIndex].time,
        to: candleData[lastIndex].time,
      })
    }
  }
})

function formatValue(value: number | undefined): string {
  return value !== undefined ? value.toFixed(2) : '-'
}
</script>

<template>
  <div class="rounded-xl border border-border bg-card overflow-hidden">
    <div class="px-4 py-2 border-b border-border bg-secondary/30">
      <h3 class="text-sm font-semibold text-foreground">日K线</h3>
      <!-- MA + RSI + MACD indicators below title -->
      <div class="flex flex-wrap gap-4 mt-2 text-xs">
        <span class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full" style="background:#facc15"></span>
          <span style="color:#facc15">MA5:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.ma5) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full" style="background:#22c55e"></span>
          <span style="color:#22c55e">MA10:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.ma10) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full" style="background:#3b82f6"></span>
          <span style="color:#3b82f6">MA20:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.ma20) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full" style="background:#a855f7"></span>
          <span style="color:#a855f7">MA30:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.ma30) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full" style="background:#ef4444"></span>
          <span style="color:#ef4444">MA60:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.ma60) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="text-slate-400">RSI:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.rsi14) }}</span>
        </span>
        <span class="flex items-center gap-1">
          <span class="text-slate-400">MACD:</span>
          <span class="text-slate-300">{{ formatValue(indicators?.macd) }}</span>
        </span>
      </div>
    </div>
    <div ref="chartContainer" class="w-full h-[400px]"></div>
  </div>
</template>
