<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getPortfolioDashboard, type PortfolioDashboard } from '../api/client'

const props = defineProps<{ symbol: string }>()

const dashboard = ref<PortfolioDashboard | null>(null)
const loading = ref(false)
const error = ref('')

const compactSymbol = (symbol: string) => symbol.split('.', 1)[0].padStart(6, '0')
const fmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const load = async () => {
  if (!props.symbol) return
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await getPortfolioDashboard()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '组合上下文加载失败'
  } finally {
    loading.value = false
  }
}

const position = computed(() => {
  const key = compactSymbol(props.symbol)
  return (dashboard.value?.positions || []).find((item: any) => compactSymbol(item.symbol) === key)
})

const attractiveness = computed(() => {
  const key = compactSymbol(props.symbol)
  return (dashboard.value?.attractiveness_radar?.positions || []).find((item: any) => compactSymbol(item.symbol) === key)
})

const themePosition = computed(() => {
  const key = compactSymbol(props.symbol)
  for (const theme of dashboard.value?.theme_evidence_radar?.themes || []) {
    const row = (theme.related_positions || []).find((item: any) => compactSymbol(item.symbol) === key)
    if (row) return { ...row, theme_name: theme.theme_name, theme_score: theme.portfolio_relevance_score, theme_weight: theme.related_position_weight_pct }
  }
  return null
})

const eventRows = computed(() => {
  const key = compactSymbol(props.symbol)
  return (dashboard.value?.market_event_radar?.events || []).filter((event: any) =>
    (event.related_positions || []).some((item: any) => compactSymbol(item.symbol) === key),
  )
})

const conclusion = computed(() => {
  const score = Number(attractiveness.value?.score || 0)
  const coverage = Number(attractiveness.value?.coverage || 0)
  const weight = Number(position.value?.portfolio_weight_pct || 0)
  const blockers = attractiveness.value?.account_constraints?.blockers || []
  if (!attractiveness.value) return '该标的尚未进入组合吸引力雷达，先以K线和基础事实为主。'
  if (blockers.length) return `组合约束优先：${blockers.join('；')}`
  if (score >= 70 && coverage >= 70) return weight > 0 ? '吸引力达到候选区间，但仍需结合账户空间和同主题机会成本。' : '观察池吸引力较高，可等待健康度和账户空间确认。'
  if (score >= 55) return '吸引力中性，重点观察催化、估值或相对强弱是否改善。'
  return '吸引力偏弱，当前不适合作为新增风险敞口的优先方向。'
})

watch(() => props.symbol, load, { immediate: true })
</script>

<template>
  <div class="rounded-lg border border-border bg-card">
    <div class="border-b border-border px-3 py-2">
      <h3 class="text-sm font-semibold text-foreground">组合上下文与吸引力拆解</h3>
      <p class="mt-1 text-xs text-muted-foreground">这部分来自驾驶舱缓存，用来解释它在账户中的角色。</p>
    </div>
    <div v-if="loading" class="p-3 text-xs text-muted-foreground">正在读取组合上下文...</div>
    <div v-else-if="error" class="p-3 text-xs text-warning">{{ error }}</div>
    <div v-else class="space-y-3 p-3 text-xs">
      <div class="rounded border border-border/70 bg-secondary/10 p-3">
        <div class="text-muted-foreground">当前结论</div>
        <div class="mt-1 text-sm font-medium text-foreground">{{ conclusion }}</div>
      </div>
      <div class="grid gap-2 md:grid-cols-4">
        <div class="rounded bg-secondary/25 p-2">
          <div class="text-muted-foreground">账户权重</div>
          <div class="mt-1 font-mono text-foreground">{{ fmt(position?.portfolio_weight_pct, '%') }}</div>
        </div>
        <div class="rounded bg-secondary/25 p-2">
          <div class="text-muted-foreground">主题</div>
          <div class="mt-1 truncate text-foreground">{{ themePosition?.theme_name || '-' }}</div>
        </div>
        <div class="rounded bg-secondary/25 p-2">
          <div class="text-muted-foreground">吸引力 / 覆盖</div>
          <div class="mt-1 font-mono text-sky-200">{{ attractiveness ? `${attractiveness.score} / ${attractiveness.coverage}%` : '-' }}</div>
        </div>
        <div class="rounded bg-secondary/25 p-2">
          <div class="text-muted-foreground">组合优先</div>
          <div class="mt-1 font-mono text-emerald-200">{{ attractiveness?.portfolio_priority_score ?? '-' }}</div>
        </div>
      </div>
      <div v-if="attractiveness?.dimensions?.length" class="grid gap-2 md:grid-cols-5">
        <div v-for="item in attractiveness.dimensions" :key="item.key" class="rounded border border-border/70 bg-background/40 p-2">
          <div class="text-muted-foreground">{{ item.label }} · {{ item.weight }}%</div>
          <div class="mt-1 font-mono text-base text-foreground">{{ item.score ?? '缺数据' }}</div>
          <div v-if="item.reasons?.[0]" class="mt-1 leading-5 text-muted-foreground">{{ item.reasons[0] }}</div>
        </div>
      </div>
      <div v-if="attractiveness?.top_reasons?.length" class="rounded bg-secondary/20 p-2 text-muted-foreground">
        主要理由：{{ attractiveness.top_reasons.join('；') }}
      </div>
      <div v-if="eventRows.length" class="rounded bg-secondary/20 p-2 text-muted-foreground">
        相关事件：{{ eventRows.map((event: any) => `${event.title}（${event.days_until}天）`).join('；') }}
      </div>
      <div v-if="attractiveness?.opportunity_cost?.dominated_by_symbol" class="rounded border border-warning/40 bg-warning/10 p-2 text-warning">
        同主题机会成本：优先级低于 {{ attractiveness.opportunity_cost.dominated_by_name || attractiveness.opportunity_cost.dominated_by_symbol }}，差 {{ fmt(attractiveness.opportunity_cost.priority_gap) }} 分。
      </div>
    </div>
  </div>
</template>
