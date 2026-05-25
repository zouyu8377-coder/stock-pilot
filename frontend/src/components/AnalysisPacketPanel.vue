<script setup lang="ts">
import { ref, watch } from 'vue'
import { createSingleAnalysisPacket } from '../api/client'

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

const reset = () => {
  error.value = ''
  markdown.value = ''
  jsonText.value = ''
  savedPaths.value = null
  copied.value = false
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
        <h3 class="text-sm font-semibold text-foreground">Analysis Packet v1</h3>
        <p class="text-[11px] text-muted-foreground">Local preview only. Copy or export manually; no external LLM call is made.</p>
      </div>
      <button class="rounded bg-primary px-3 py-1 text-xs" :disabled="loading" @click="generate">
        {{ loading ? 'Generating...' : 'Generate Analysis Packet' }}
      </button>
    </div>
    <div class="space-y-3 p-3">
      <div class="rounded border border-warning/40 bg-warning/10 p-2 text-xs text-muted-foreground">
        Exported content may include real holdings, cost, cash, plans, and manual evidence. Attachments are referenced only and are not uploaded automatically.
      </div>
      <textarea
        v-model="userQuestion"
        class="w-full rounded bg-input px-2 py-1 text-xs"
        rows="2"
        placeholder="Optional neutral question for the packet"
      ></textarea>
      <div v-if="error" class="text-xs text-warning">{{ error }}</div>
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
