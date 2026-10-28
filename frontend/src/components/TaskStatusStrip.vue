<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { getAnalysisWorkflow, cancelAnalysisWorkflow, type AnalysisWorkflow } from '../api/client'
const task = ref<AnalysisWorkflow>({ status: 'idle', steps: [] })
const error = ref('')
let stopped = false
let timer: ReturnType<typeof setTimeout> | undefined
async function poll() {
  try { task.value = await getAnalysisWorkflow(); error.value = '' }
  catch { error.value = '暂时无法读取后台任务状态' }
  finally { if (!stopped) timer = setTimeout(poll, 3000) }
}
async function cancel() {
  try { task.value = await cancelAnalysisWorkflow() }
  catch { error.value = '取消请求未确认' }
}
onMounted(poll)
onUnmounted(() => { stopped = true; clearTimeout(timer) })
</script>
<template>
  <aside v-if="task.status !== 'idle' || error" class="mb-4 border-y border-border py-3 text-xs">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="text-foreground">后台任务 · {{ task.detail || task.status }} · 已用 {{ task.elapsed_seconds || 0 }} 秒</div>
      <button v-if="task.status === 'running'" class="rounded border border-border px-3 py-2 text-foreground" @click="cancel">取消后续步骤</button>
    </div>
    <p class="mt-1 text-muted-foreground">最近进展 {{ task.last_progress_at ? new Date(task.last_progress_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '--' }} · 模型请求 {{ task.model_requests || 0 }} 次</p>
    <p v-if="task.status === 'cancelling'" class="mt-1 text-warning">等待当前请求返回或超时后停止，不启动后续步骤。</p>
    <p v-if="task.overdue" class="mt-1 text-warning">当前阶段超出预期等待时间。</p>
    <p v-if="task.error || error" class="mt-1 text-warning">{{ error || task.error }}</p>
  </aside>
</template>
