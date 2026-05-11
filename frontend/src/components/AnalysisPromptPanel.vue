<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

const props = defineProps<{
  symbol: string
}>()

type Status = 'idle' | 'loading' | 'success' | 'error'

const status = ref<Status>('idle')
const promptText = ref('')
const errorMsg = ref('')

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const resetState = () => {
  status.value = 'idle'
  promptText.value = ''
  errorMsg.value = ''
}

const loadPromptData = async () => {
  if (!props.symbol) return

  status.value = 'loading'
  errorMsg.value = ''

  try {
    const response = await fetch(`${API_BASE_URL}/api/deep-analyze-prompt/${props.symbol}`)
    const result = await response.json()
    if (!response.ok) {
      throw new Error(result.detail || `HTTP ${response.status}`)
    }

    if (result.success) {
      promptText.value = result.prompt
      status.value = 'success'
    } else {
      errorMsg.value = result.message || '数据构建失败'
      status.value = 'error'
    }
  } catch (e: any) {
    errorMsg.value = e.message || '网络错误'
    status.value = 'error'
  }
}

const copyToClipboard = async () => {
  const text = promptText.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    alert('已复制到剪贴板')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    alert('已复制到剪贴板')
  }
}

watch(() => props.symbol, () => {
  resetState()
})

onMounted(() => {
  resetState()
})
</script>

<template>
  <div class="rounded-xl border border-border bg-card overflow-hidden flex flex-col">
    <div class="flex items-center justify-between px-4 py-2 border-b border-border bg-secondary/30">
      <h3 class="text-sm font-semibold text-foreground">AI 分析提示词预览</h3>
      <span class="text-[11px] text-muted-foreground">可拷贝至 ChatGPT / Claude 等 LLM 使用</span>
    </div>

    <div class="p-4 space-y-4 flex-1 overflow-y-auto max-h-[600px]">
      <!-- Idle -->
      <div v-if="status === 'idle'" class="text-center py-8">
        <p class="text-sm text-muted-foreground mb-3">点击下方按钮生成可直接拷贝的完整提示词</p>
        <button
          @click="loadPromptData"
          class="py-2 px-5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-all"
        >
          生成提示词
        </button>
      </div>

      <!-- Loading -->
      <div v-else-if="status === 'loading'" class="text-center py-8">
        <div class="animate-pulse text-sm text-foreground mb-2">正在构建提示词...</div>
        <p class="text-xs text-muted-foreground">读取行情、指标、公司画像与策略上下文</p>
      </div>

      <!-- Error -->
      <div v-else-if="status === 'error'" class="text-center py-8">
        <div class="text-red-500 text-sm mb-2">构建失败</div>
        <p class="text-xs text-muted-foreground mb-4">{{ errorMsg }}</p>
        <button
          @click="loadPromptData"
          class="py-2 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-all"
        >
          重试
        </button>
      </div>

      <!-- Success -->
      <template v-else-if="status === 'success'">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-xs font-semibold text-foreground uppercase tracking-wide">完整 Prompt</h4>
          <button
            @click="copyToClipboard"
            class="text-[11px] px-2 py-1 rounded bg-secondary text-muted-foreground hover:text-foreground transition-colors"
          >
            复制全部
          </button>
        </div>
        <pre class="text-[11px] leading-relaxed bg-black/40 rounded-lg p-3 overflow-x-auto text-foreground/80 font-mono whitespace-pre-wrap border border-border/50">{{ promptText }}</pre>

        <div class="pt-2">
          <button
            @click="loadPromptData"
            class="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-all"
          >
            重新生成
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
