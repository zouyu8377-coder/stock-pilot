<script setup lang="ts">
import { ref, watch } from 'vue'
import { createSingleAnalysisPacket } from '../api/client'
import { APP_VERSION } from '../version'

const props = defineProps<{
  symbol: string
}>()

const loading = ref(false)
const error = ref('')
const userQuestion = ref('')
const markdown = ref('')
const jsonText = ref('')
const savedPaths = ref<Record<string, string> | null>(null)
const copied = ref(false)
const chainWarning = ref('')

const reset = () => {
  error.value = ''
  markdown.value = ''
  jsonText.value = ''
  savedPaths.value = null
  copied.value = false
  chainWarning.value = ''
}

const generate = async () => {
  if (!props.symbol) return
  loading.value = true
  error.value = ''
  copied.value = false
  try {
    const result = await createSingleAnalysisPacket(props.symbol, userQuestion.value)
    markdown.value = result.markdown
    jsonText.value = JSON.stringify(result.packet, null, 2)
    savedPaths.value = result.saved_paths || null
    const packetText = `${result.markdown}\n${JSON.stringify(result.packet)}`
    const hasVisibleDriverSection = packetText.includes('Relevant External Drivers')
    const hasOldBoundary = packetText.includes('FX, futures') || packetText.includes('market_data_as_of')
    chainWarning.value = (!hasVisibleDriverSection || hasOldBoundary)
      ? `Packet 链路自检未通过：当前页面 ${APP_VERSION} 收到的内容疑似旧版导出，请确认顶部版本号和 API 端口后刷新重试。`
      : ''
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e.message || 'Analysis Packet generation failed'
  } finally {
    loading.value = false
  }
}

const copyMarkdown = async () => {
  if (!markdown.value) return
  await navigator.clipboard.writeText(markdown.value)
  copied.value = true
}

watch(() => props.symbol, reset)
</script>

<template>
  <section class="rounded-lg border border-border bg-card">
    <div class="flex items-center justify-between border-b border-border bg-secondary/30 px-3 py-2">
      <div>
        <h3 class="text-sm font-semibold text-foreground">单票证据包 / Stock Analysis Packet v1</h3>
        <p class="text-[11px] text-muted-foreground">汇总该标的的行情、事实、辅助信号与外部驱动；如当前持有，仅只读展示其账户关系。</p>
      </div>
      <button class="rounded bg-primary px-3 py-1 text-xs" :disabled="loading" @click="generate">
        {{ loading ? 'Generating...' : '生成单票证据包 / Generate Stock Packet' }}
      </button>
    </div>
    <div class="space-y-3 p-3">
      <div class="rounded border border-warning/40 bg-warning/10 p-2 text-xs text-muted-foreground">
        Exported content may include real holdings, cost, cash, plans, and manual evidence. Attachments are referenced only and are not uploaded automatically.
      </div>
      <div class="rounded border border-border/60 bg-secondary/30 p-2 text-xs text-muted-foreground">
        账户级仓位与组合分析请在未来的个人投资仪表盘中查看；本页不生成账户级行动建议。
      </div>
      <textarea
        v-model="userQuestion"
        class="w-full rounded bg-input px-2 py-1 text-xs"
        rows="2"
        placeholder="Optional neutral question for the packet"
      ></textarea>
      <div v-if="error" class="text-xs text-warning">{{ error }}</div>
      <div v-if="chainWarning" class="rounded border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
        {{ chainWarning }}
      </div>
      <div v-if="markdown" class="flex items-center justify-between">
        <span class="text-xs text-muted-foreground">Markdown preview</span>
        <button class="rounded bg-secondary px-3 py-1 text-xs" @click="copyMarkdown">
          {{ copied ? 'Copied' : 'Copy Markdown' }}
        </button>
      </div>
      <pre v-if="markdown" class="max-h-80 overflow-auto rounded bg-black/40 p-3 text-[11px] leading-relaxed text-foreground/85 whitespace-pre-wrap">{{ markdown }}</pre>
      <details v-if="jsonText" class="text-xs">
        <summary class="cursor-pointer text-muted-foreground">JSON snapshot</summary>
        <pre class="mt-2 max-h-60 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ jsonText }}</pre>
      </details>
      <div v-if="savedPaths" class="text-[11px] text-muted-foreground">
        Saved JSON: {{ savedPaths.json_path }}<br />
        Saved Markdown: {{ savedPaths.markdown_path }}
      </div>
    </div>
  </section>
</template>
