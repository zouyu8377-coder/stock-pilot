<script setup lang="ts">
import type { ResearchDossier } from '../api/client'
defineProps<{ dossier: ResearchDossier }>()
const labels: Record<string, string> = { not_checked: '未检查', checked_no_new: '已检查无新增', material_found: '取得材料，问题待核验', body_verified: '正文已核验', source_blocked: '来源受阻' }
const time = (v?: string) => v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '尚无记录'
const safe = (url?: string) => /^https?:\/\//.test(url || '')
</script>
<template>
  <div class="space-y-3 text-xs leading-6 [overflow-wrap:anywhere]">
    <div v-for="q in dossier.questions" :key="q.question" class="border-b border-border pb-3">
      <p class="font-medium text-foreground">{{ q.question }}</p>
      <p :class="q.status === 'body_verified' ? 'text-sky-300' : 'text-warning'">{{ labels[q.status] || q.status }}<span v-if="q.check_stale"> · 检查待更新</span></p>
      <p class="text-muted-foreground">最近检查 {{ time(q.checked_at) }}</p>
      <p v-if="q.answer">{{ q.answer }}</p>
      <div v-for="source in q.sources" :key="source.source_url + source.quote" class="mt-2 border-l-2 border-sky-800 pl-3">
        <a v-if="safe(source.source_url)" :href="source.source_url" target="_blank" rel="noopener noreferrer" class="text-sky-300">{{ source.source_title }} · {{ source.announced_at }}<span v-if="source.page"> · 第{{ source.page }}页</span></a>
        <p>{{ source.quote }}</p>
      </div>
      <p v-if="q.blocker" class="text-warning">{{ q.blocker }}</p>
      <p v-if="q.status !== 'body_verified'" class="text-muted-foreground">{{ q.next_step }}</p>
    </div>
    <details v-if="dossier.documents.length"><summary class="cursor-pointer text-sky-300">取得的原始材料 {{ dossier.documents.length }} 份</summary><div v-for="doc in dossier.documents" :key="doc.pdf_url"><a v-if="safe(doc.pdf_url)" :href="doc.pdf_url" target="_blank" rel="noopener noreferrer" class="text-sky-300">{{ doc.title }} · {{ doc.announced_at }}</a></div></details>
    <details v-if="dossier.tasks.length"><summary class="cursor-pointer text-sky-300">取证任务记录</summary><p v-for="task in dossier.tasks" :key="task.task_id">{{ task.task }} · {{ task.status }} {{ task.error || '' }}</p></details>
    <p class="text-muted-foreground">引用通过核验不代表投资判断正确；未取得材料不代表不存在风险。</p>
  </div>
</template>
