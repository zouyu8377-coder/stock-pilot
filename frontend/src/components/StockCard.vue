<script setup lang="ts">
import { computed } from 'vue'
import type { Stock } from '../api/client'

const props = defineProps<{
  stock: Stock
}>()

const isPositive = computed(() => props.stock.change_pct >= 0)
</script>

<template>
  <div class="space-y-3">
    <!-- Stock Price Hero -->
    <div class="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div class="flex items-start justify-between">
        <div>
          <div class="flex items-center gap-2 mb-1 flex-wrap">
            <h2 class="text-lg font-semibold text-foreground">{{ stock.name }}</h2>
            <span
              v-if="stock.industry"
              class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200"
            >
              {{ stock.industry }}
            </span>
            <span class="px-2 py-0.5 rounded bg-secondary text-xs font-mono text-muted-foreground">
              {{ stock.symbol }}
            </span>
          </div>

          <div class="flex items-baseline gap-2">
            <span class="text-3xl font-bold tracking-tight font-mono text-foreground">
              {{ stock.price?.toFixed(2) }}
            </span>
            <div :class="[
              'flex items-center gap-1 px-2 py-0.5 rounded text-sm font-medium',
              isPositive ? 'bg-red-500/10 text-red-500' : 'bg-green-500/10 text-green-500'
            ]">
              {{ isPositive ? '+' : '' }}{{ stock.change_pct?.toFixed(2) }}%
            </div>
          </div>
        </div>
      </div>

      <!-- Market info row -->
      <div class="flex flex-wrap gap-2 mt-2 pt-2 border-t border-border/50 text-xs text-slate-400">
        <span>总市值: {{ stock.market_cap != null ? stock.market_cap.toFixed(2) + '亿' : '-' }}</span>
        <span>流通: {{ stock.float_market_cap != null ? stock.float_market_cap.toFixed(2) + '亿' : '-' }}</span>
        <span>PE: {{ stock.pe ? stock.pe.toFixed(2) : '-' }}</span>
        <span>PB: {{ stock.pb ? stock.pb.toFixed(2) : '-' }}</span>
        <span>换手: {{ stock.turnover_rate ? stock.turnover_rate.toFixed(2) + '%' : '-' }}</span>
        <span>量比: {{ stock.volume_ratio ? stock.volume_ratio.toFixed(2) : '-' }}</span>
        <span>成交量: {{ ((stock.volume || 0) / 10000).toFixed(2) }}万手</span>
      </div>
    </div>

    <!-- AI Analysis Card -->
    <div class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-secondary/30">
        <h3 class="text-sm font-semibold text-foreground">AI分析结论</h3>
      </div>

      <div class="p-3">
        <div class="grid grid-cols-2 gap-2 mb-2">
          <div class="flex items-center gap-2 rounded-lg bg-secondary/50 p-1.5">
            <span class="text-xs text-muted-foreground">趋势</span>
            <span :class="[
              'text-sm font-semibold',
              stock.analysis?.trend?.includes('多') ? 'text-red-500' : 'text-green-500'
            ]">
              {{ stock.analysis?.trend || '-' }}
            </span>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-secondary/50 p-1.5">
            <span class="text-xs text-muted-foreground">信号</span>
            <span :class="[
              'text-sm font-semibold',
              stock.analysis?.signal?.includes('买') ? 'text-red-500' :
              stock.analysis?.signal?.includes('卖') ? 'text-green-500' : 'text-yellow-500'
            ]">
              {{ stock.analysis?.signal || '-' }}
            </span>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-secondary/50 p-1.5">
            <span class="text-xs text-muted-foreground">支撑</span>
            <span class="text-sm font-semibold text-foreground">{{ stock.analysis?.support || '-' }}</span>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-secondary/50 p-1.5">
            <span class="text-xs text-muted-foreground">压力</span>
            <span class="text-sm font-semibold text-foreground">{{ stock.analysis?.resistance || '-' }}</span>
          </div>
        </div>

        <p class="text-xs text-foreground/80 leading-relaxed">
          {{ stock.analysis?.summary || '暂无分析' }}
        </p>
      </div>
    </div>
  </div>
</template>