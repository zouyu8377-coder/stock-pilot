<script setup lang="ts">
import type { AgentReviewItem } from '../api/client'

defineProps<{ item: AgentReviewItem }>()
const confidenceLabels = { high: '高', medium: '中', low: '低' }
</script>

<template>
  <div class="mt-2 space-y-2 text-xs leading-relaxed text-foreground [overflow-wrap:anywhere]">
    <p><span class="font-medium text-sky-300">结论信心：{{ confidenceLabels[item.confidence] || '未评估' }}</span><span class="text-muted-foreground"> · {{ item.confidence_reason || '历史结论未提供信心拆解，重新分析后更新。' }}</span></p>
    <details>
      <summary class="cursor-pointer text-sky-300">技术面、消息面与判断依据</summary>
      <div class="mt-2 space-y-2">
        <p><span class="font-medium">技术面：</span>{{ item.technical_analysis || '历史结论未单列技术面分析。' }}</p>
        <p><span class="font-medium">消息面：</span>{{ item.news_analysis || '历史结论未单列消息面分析，不代表没有风险事件。' }}</p>
        <ul v-if="item.decision_basis?.length" class="list-disc space-y-1 pl-4"><li v-for="basis in item.decision_basis" :key="basis">{{ basis }}</li></ul>
        <p v-if="item.counter_scenario"><span class="font-medium">反向情景：</span>{{ item.counter_scenario }}</p>
      </div>
    </details>
  </div>
</template>
