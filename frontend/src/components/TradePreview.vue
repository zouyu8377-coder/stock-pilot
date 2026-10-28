<script setup lang="ts">
import { ref, watch } from 'vue'
import { simulateTrade } from '../api/client'
const props = defineProps<{ symbol: string; name: string }>()
const side = ref('sell')
const quantity = ref<number | null>(null)
const price = ref<number | null>(null)
const result = ref<any>(null)
const error = ref('')
const loading = ref(false)
watch([side, quantity, price], () => { result.value = null })
async function preview() {
  if (!quantity.value || quantity.value <= 0 || !price.value || price.value <= 0) { error.value = '请输入正数数量和预估成交价'; return }
  loading.value = true; error.value = ''
  const input = { symbol: props.symbol, name: props.name, action: side.value, quantity: quantity.value, estimated_price: price.value, is_planned_trade: true }
  try {
    const response = await simulateTrade(input)
    if (input.symbol === props.symbol && input.action === side.value && input.quantity === quantity.value && input.estimated_price === price.value) result.value = response
  }
  catch (e: any) { error.value = e.response?.data?.detail || '预案计算失败' }
  finally { loading.value = false }
}
const weight = (metrics: any) => metrics.position_weights?.find((p: any) => String(p.symbol).includes(props.symbol))?.weight_pct ?? 0
</script>
<template>
  <details class="mt-3 text-xs"><summary class="cursor-pointer text-sky-300">调整预案（只读模拟）</summary>
    <form class="mt-3 space-y-2" @submit.prevent="preview">
      <div class="grid grid-cols-2 gap-2">
        <label>方向<select v-model="side" class="mt-1 h-9 w-full rounded border border-border bg-background px-2"><option value="sell">减持</option><option value="buy">增持</option></select></label>
        <label>数量<input v-model.number="quantity" type="number" min="1" step="1" required class="mt-1 h-9 w-full rounded border border-border bg-background px-2" /></label>
        <label>预估成交价<input v-model.number="price" type="number" min="0.001" step="any" required class="mt-1 h-9 w-full rounded border border-border bg-background px-2" /></label>
        <button class="mt-5 h-9 rounded border border-border px-3 disabled:opacity-50" :disabled="loading">{{ loading ? '计算中' : '计算账户影响' }}</button>
      </div>
      <p v-if="error" role="alert" class="text-warning">{{ error }}</p>
      <div v-if="result" class="space-y-1 border-y border-border py-2">
        <p>现金比例 {{ result.before.cash_ratio_pct }}% → {{ result.after.cash_ratio_pct }}%</p>
        <p>总仓位 {{ result.before.invested_ratio_pct }}% → {{ result.after.invested_ratio_pct }}%</p>
        <p>该标的权重 {{ weight(result.before) }}% → {{ weight(result.after) }}%</p>
        <p v-for="warning in [...result.warnings, ...result.risk_notes]" :key="warning" class="text-warning">{{ warning }}</p>
      </div>
      <p class="text-muted-foreground">数量和价格由你设定；预案未计入实际成交费用，不代表交易已发生，不会保存为持仓。</p>
    </form>
  </details>
</template>
