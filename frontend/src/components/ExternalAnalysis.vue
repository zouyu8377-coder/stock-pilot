<script setup lang="ts">
import { ref, watch } from 'vue'
import { exportExternalAnalysis, importExternalAnalysis } from '../api/client'
const emit = defineEmits<{ (event: 'imported'): void }>()
const request = ref<{ prompt: string; local_path: string; request_id: string } | null>(null)
const result = ref('')
const preview = ref<any>(null)
const pending = ref(false)
const message = ref('')
watch(result, () => { preview.value = null })
async function generate() {
  pending.value = true; message.value = ''; request.value = null; preview.value = null
  try { request.value = await exportExternalAnalysis() }
  catch (e: any) { message.value = e.response?.data?.detail || '导出失败' }
  finally { pending.value = false }
}
async function copy() {
  try { await navigator.clipboard.writeText(request.value!.prompt); message.value = '提示词已复制' }
  catch { message.value = '剪贴板不可用，请下载请求文件' }
}
function download() {
  const url = URL.createObjectURL(new Blob([request.value!.prompt], { type: 'text/plain;charset=utf-8' }))
  const a = document.createElement('a'); a.href = url; a.download = `${request.value!.request_id}.txt`; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 300000) { message.value = '结果文件过大'; return }
  result.value = await file.text()
}
async function submit(confirm = false) {
  pending.value = true; message.value = ''
  try {
    const response = await importExternalAnalysis(result.value, confirm)
    if (response.status === 'preview') preview.value = response
    else { preview.value = null; result.value = ''; message.value = '分析结果已导入，持仓未修改'; emit('imported') }
  } catch (e: any) { preview.value = null; message.value = e.response?.data?.detail || '校验失败' }
  finally { pending.value = false }
}
</script>

<template>
  <details class="border-y border-border py-3 text-sm">
    <summary class="cursor-pointer text-sky-300">外部分析 · 导出与回传</summary>
    <div class="mt-3 space-y-3">
      <p class="text-xs text-muted-foreground">包含账户与交易敏感信息。仅在主动复制或下载后交给外部模型；导出本身不调用模型。有效期4小时，账户变化后需重新导出。</p>
      <div class="flex flex-wrap gap-2">
        <button class="rounded bg-primary px-3 py-2 disabled:opacity-50" :disabled="pending" @click="generate">{{ pending ? '处理中' : '生成分析请求' }}</button>
        <button v-if="request" class="rounded border border-border px-3 py-2" @click="copy">复制提示词</button>
        <button v-if="request" class="rounded border border-border px-3 py-2" @click="download">下载请求</button>
      </div>
      <p v-if="request" class="break-all text-xs text-muted-foreground">本地请求：{{ request.local_path }}</p>
      <label class="block">分析结果 JSON<textarea v-model="result" class="mt-2 block min-h-28 w-full rounded border border-border bg-background p-2 font-mono text-xs" aria-label="分析结果 JSON" /></label>
      <div class="flex flex-wrap items-center gap-3"><input type="file" accept=".json,.txt" aria-label="导入分析结果文件" class="max-w-full text-xs" @change="readFile" /><button class="rounded border border-border px-3 py-2 disabled:opacity-50" :disabled="pending || !result.trim()" @click="submit(false)">校验并预览</button></div>
      <div v-if="preview" class="space-y-2 border-l-2 border-sky-400 pl-3">
        <h4 class="font-semibold">{{ preview.review.headline }}</h4><p>{{ preview.review.summary }}</p>
        <p v-for="warning in preview.warnings" :key="warning" class="text-xs text-warning">{{ warning }}</p>
        <details><summary class="cursor-pointer text-sky-300">完整待导入结果</summary><pre class="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(preview.review, null, 2) }}</pre></details>
        <button class="rounded bg-primary px-3 py-2 disabled:opacity-50" :disabled="pending" @click="submit(true)">确认导入分析与任务</button>
      </div>
      <p v-if="message" role="status" class="text-sm text-warning">{{ message }}</p>
    </div>
  </details>
</template>
