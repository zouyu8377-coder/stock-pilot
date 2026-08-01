<script setup lang="ts">
import { ColorType, LineSeries, createChart, type IChartApi } from 'lightweight-charts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  points: Array<{ date: string; sector: number; benchmark: number }>
}>()

const container = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let observer: ResizeObserver | null = null

const render = async () => {
  await nextTick()
  if (!container.value) return
  chart?.remove()
  chart = createChart(container.value, {
    width: container.value.clientWidth,
    height: 240,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: '#94a3b8',
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
      horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
    },
    rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.18)' },
    timeScale: { borderColor: 'rgba(148, 163, 184, 0.18)', timeVisible: false },
    crosshair: {
      vertLine: { color: '#64748b', labelBackgroundColor: '#334155' },
      horzLine: { color: '#64748b', labelBackgroundColor: '#334155' },
    },
  })
  const sector = chart.addSeries(LineSeries, {
    color: '#38bdf8',
    lineWidth: 2,
    title: '方向代理',
    priceLineVisible: false,
  })
  const benchmark = chart.addSeries(LineSeries, {
    color: '#94a3b8',
    lineWidth: 1,
    title: '沪深300',
    priceLineVisible: false,
  })
  sector.setData(props.points.map((point) => ({ time: point.date, value: point.sector })))
  benchmark.setData(props.points.map((point) => ({ time: point.date, value: point.benchmark })))
  chart.timeScale().fitContent()
}

onMounted(() => {
  render()
  if (container.value) {
    observer = new ResizeObserver(([entry]) => {
      chart?.applyOptions({ width: Math.floor(entry.contentRect.width) })
    })
    observer.observe(container.value)
  }
})

watch(() => props.points, render, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.remove()
})
</script>

<template>
  <div ref="container" class="h-[240px] w-full"></div>
</template>
