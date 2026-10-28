<script setup lang="ts">
import ExternalDiscussion from './ExternalDiscussion.vue'
import InvestmentAgentWorkbench from './InvestmentAgentWorkbench.vue'
import { accountPrivacyHidden } from '../composables/useAccountPrivacy'
defineProps<{ accountOverview?: any }>()
defineEmits(['open-review', 'open-rotation', 'open-import', 'select-symbol', 'refresh-dashboard'])
const fmt = (n: number | undefined) => n == null ? '--' : n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
</script>
<template>
  <section class="space-y-5">
    <header class="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
      <h1 class="text-xl font-semibold">投资工作台</h1>
      <div class="flex flex-wrap gap-3">
        <button class="rounded border border-border px-3 py-2 text-sm" @click="$emit('open-import', 'current_holdings')">更新持仓</button>
        <button class="rounded border border-border px-3 py-2 text-sm" @click="$emit('open-import', 'trade_history')">记录交易</button>
      </div>
    </header>
    <dl aria-label="账户基础数据" class="grid grid-cols-2 gap-4 border-b border-border pb-4 text-sm sm:grid-cols-4">
      <div><dt class="text-muted-foreground">账户总盈亏</dt><dd :class="['mt-1 font-mono', accountPrivacyHidden ? 'text-muted-foreground' : (accountOverview?.pnl ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400']">{{ accountPrivacyHidden ? '****' : `${fmt(accountOverview?.pnl)} / ${fmt(accountOverview?.pnlPct)}%` }}</dd></div>
      <div><dt class="text-muted-foreground">仓位</dt><dd class="mt-1">{{ accountPrivacyHidden ? '****' : `${fmt(accountOverview?.positionPct)}%` }}</dd></div>
      <div><dt class="text-muted-foreground">现金比例</dt><dd class="mt-1">{{ accountPrivacyHidden ? '****' : `${fmt(accountOverview?.cashPct)}%` }}</dd></div>
      <div><dt class="text-muted-foreground">最大方向暴露</dt><dd class="mt-1">{{ accountPrivacyHidden ? '****' : accountOverview?.exposure || '--' }}</dd></div>
    </dl>
    <InvestmentAgentWorkbench @updated="$emit('refresh-dashboard')" />
    <details class="border-t border-border pt-4"><summary class="cursor-pointer text-sm text-sky-300">外部手动讨论与既有记录</summary><div class="pt-4"><ExternalDiscussion @confirmed="$emit('refresh-dashboard')" /></div></details>
  </section>
</template>
