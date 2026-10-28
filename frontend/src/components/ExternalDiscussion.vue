<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Copy, RefreshCw, Check, FolderOpen } from 'lucide-vue-next'
import { discussionRequest } from '../api/client'
const emit = defineEmits(['confirmed'])
const data = ref<any>(null)
const question = ref('请结合账户、行业方向和具体标的，讨论风险、机会及下一步计划。')
const mode = ref('continue')
const archive = ref(false)
const pasted = ref('')
const busy = ref('')
const error = ref('')
const notice = ref('')
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | undefined
let polling = false
let disposed = false
let firstLoad = true
let ticks = 0
const incoming = computed(() => data.value?.incoming)
const latest = computed(() => data.value?.records?.results?.at(-1))
const entities = computed<any[]>(() => Object.values(data.value?.records?.entities || {}).filter((e: any) => e.active))
const kind: Record<string, string> = { assessment: '判断', recommendation: '建议', followup: '待办', memory: '长期记录' }
const levels: Record<string, string> = { account: '账户', direction: '行业方向', symbol: '具体标的' }
const confidence: Record<string, string> = { high: '高', medium: '中', low: '低', unknown: '未确定' }
const operations: Record<string, string> = { add: '新增', update: '修改', retract: '撤回' }
const time = (v: string) => v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '--'
async function poll() {
  if (disposed || busy.value || polling || document.hidden) return
  polling = true
  try {
    const value = await discussionRequest()
    if (!busy.value && !disposed) data.value = value
    if (firstLoad && value.manifest?.question) question.value = value.manifest.question
    firstLoad = false
  }
  catch { error.value = '本地服务暂不可用；已保存的讨论不会丢失' }
  finally { polling = false }
}
async function run(label: string, action: () => Promise<void>) {
  if (busy.value) return
  busy.value = label; elapsed.value = 0; error.value = ''; notice.value = ''
  try { await action() } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '操作失败' }
  finally { busy.value = '' }
}
async function generate() {
  await run('准备讨论资料', async () => {
    data.value = await discussionRequest('/start', { question: question.value, mode: mode.value, archive_unfinished: archive.value })
    notice.value = '讨论资料已就绪'; mode.value = 'continue'; archive.value = false
  })
}
async function copy() {
  await run('读取讨论提示词', async () => {
    const result = await discussionRequest('/start', { mode: 'continue' })
    await navigator.clipboard.writeText(result.prompt || ''); notice.value = '已复制'
  })
}
async function confirm() {
  const checksum = incoming.value?.digest
  await run('保存讨论结论', async () => { data.value = await discussionRequest('/confirm', { preview_digest: checksum }); emit('confirmed') })
}
async function importResult() {
  await run('校验结果', async () => { data.value = await discussionRequest('/import', { result: JSON.parse(pasted.value) }) })
}
async function supplement() {
  await run('补充公开资料', async () => { data.value = await discussionRequest('/supplement', {}) })
}
onMounted(() => { poll(); timer = setInterval(() => { ticks++; if (busy.value) elapsed.value++; else if (ticks % 5 === 0) poll() }, 1000) })
onUnmounted(() => { disposed = true; if (timer) clearInterval(timer) })
</script>

<template>
  <section class="discussion space-y-5">
    <div class="grid gap-5 lg:grid-cols-2">
      <section class="space-y-3">
        <h2 class="text-base font-semibold">讨论资料</h2>
        <textarea v-model="question" aria-label="本次讨论问题" maxlength="6000" class="w-full min-h-24 rounded border border-border bg-background p-3 text-sm" />
        <div class="flex flex-wrap items-center gap-3 text-sm">
          <select v-model="mode" aria-label="讨论方式" class="rounded border border-border bg-background p-2">
            <option value="continue">继续当前讨论</option><option value="refresh">刷新资料并继续</option><option value="new">新建讨论并归档上一轮</option>
          </select>
          <button :disabled="!!busy" class="rounded bg-primary px-3 py-2 disabled:opacity-50" @click="generate"><RefreshCw :size="15" />{{ data?.manifest ? '准备讨论' : '生成讨论包' }}</button>
          <button v-if="data?.manifest" :disabled="!!busy" title="复制完整讨论提示词" aria-label="复制完整讨论提示词" class="rounded border border-border p-2" @click="copy"><Copy :size="17" /></button>
        </div>
        <label v-if="mode === 'new'" class="flex gap-2 text-sm"><input v-model="archive" type="checkbox" />允许归档尚未确认的讨论</label>
        <p v-if="data?.stale" class="text-sm text-amber-300">持仓已变化，当前讨论资料已过期。请刷新资料后继续。</p>
        <div v-if="data?.manifest" class="space-y-1 text-xs text-muted-foreground">
          <p>资料版本 {{ data.manifest.context_version }} · {{ time(data.manifest.created_at) }}</p>
          <details><summary class="cursor-pointer text-sky-300"><FolderOpen :size="14" class="inline" /> 本地交接文件</summary><p class="mt-2 break-all">{{ data.directory }}</p><p>prompt.md / context.json → response.json</p></details>
        </div>
      </section>
      <section class="space-y-3">
        <h2 class="text-base font-semibold">讨论结果</h2>
        <p v-if="!data?.manifest" class="text-sm text-muted-foreground">尚无讨论资料</p>
        <p v-else-if="incoming?.status === 'waiting'" class="text-sm text-muted-foreground">等待讨论结束后的回传结果</p>
        <p v-else-if="incoming?.status === 'confirmed'" class="text-sm text-sky-300">本轮结果已确认入库</p>
        <p v-if="incoming?.status === 'invalid'" class="whitespace-pre-wrap break-words text-sm text-amber-300">{{ incoming.error }}</p>
        <details><summary class="cursor-pointer text-sm text-sky-300">粘贴外部模型结果</summary>
          <textarea v-model="pasted" aria-label="回传 JSON" placeholder="最终结果 JSON" class="mt-3 min-h-24 w-full rounded border border-border bg-background p-2 font-mono text-xs" />
          <button :disabled="!!busy || !pasted.trim()" class="mt-2 rounded border border-border px-3 py-2 text-sm disabled:opacity-50" @click="importResult">校验并预览</button>
        </details>
        <button v-if="data?.supplement_pending" :disabled="!!busy" class="rounded border border-border px-3 py-2 text-sm" @click="supplement">执行资料补充请求</button>
      </section>
    </div>
    <p v-if="busy" role="status" class="text-sm text-sky-300">{{ busy }} · 已用 {{ elapsed }} 秒</p>
    <p v-if="notice" role="status" class="text-sm text-sky-300">{{ notice }}</p>
    <p v-if="error" role="alert" class="text-sm text-amber-300">{{ error }}</p>
    <section v-if="incoming?.status === 'preview'" class="space-y-3 border-y border-border py-4">
      <h2 class="font-semibold">待确认结果 · {{ incoming.result.provider }}</h2>
      <p class="whitespace-pre-wrap text-sm">{{ incoming.result.summary }}</p>
      <p class="text-xs text-amber-300">{{ incoming.warning }}</p>
      <div v-for="diff in incoming.diff" :key="diff.after.id" class="border-b border-border py-3 text-sm">
        <h3 class="font-medium">{{ operations[diff.after.operation] }} · {{ kind[diff.after.kind] }} · {{ diff.after.target }}</h3>
        <p v-if="diff.before" class="mt-1 text-muted-foreground">此前：{{ diff.before.conclusion }}</p>
        <p class="mt-1 whitespace-pre-wrap">{{ diff.after.conclusion }}</p>
        <details class="mt-2"><summary class="cursor-pointer text-sky-300">依据与条件</summary><p>{{ diff.after.reasoning }}</p><p>信心 {{ confidence[diff.after.confidence] }}：{{ diff.after.confidence_reason }}</p><p>触发：{{ diff.after.trigger || '未指定' }}</p><p>失效：{{ diff.after.invalidation || '未指定' }}</p><p>引用：{{ diff.after.evidence_refs.join('、') || '未引用证据' }}</p></details>
      </div>
      <details><summary class="cursor-pointer text-sm text-sky-300">外部来源（未经本地核验）</summary><p v-for="source in incoming.result.sources" :key="source.id" class="my-2 text-sm break-all">{{ source.id }} · {{ source.title }} · {{ source.url }}<br />{{ source.excerpt }}</p></details>
      <button :disabled="!!busy || data?.stale" class="rounded bg-primary px-3 py-2 text-sm disabled:opacity-50" @click="confirm"><Check :size="16" />确认记录，不变更持仓</button>
    </section>
    <section class="space-y-3 border-t border-border pt-4">
      <h2 class="font-semibold">已确认结论与待办</h2>
      <template v-if="latest"><p class="text-xs text-muted-foreground">{{ latest.provider }} · {{ time(latest.confirmed_at) }}</p><p class="whitespace-pre-wrap text-sm">{{ latest.summary }}</p></template>
      <p v-if="latest && (data?.stale || latest.context_fingerprint !== data?.manifest?.context_fingerprint)" class="text-xs text-amber-300">以上为历史已确认结论，尚未针对当前资料重新讨论。</p>
      <p v-else class="text-sm text-muted-foreground">暂无已确认的外部讨论结论</p>
      <div v-for="level in ['account', 'direction', 'symbol']" :key="level">
        <h3 v-if="entities.some(e => e.level === level)" class="py-2 text-sm font-semibold">{{ levels[level] }}</h3>
        <article v-for="entry in entities.filter(e => e.level === level)" :key="entry.id" class="border-b border-border py-3 text-sm">
          <p class="font-medium">{{ entry.target }} · {{ kind[entry.kind] }}</p><p class="mt-1 whitespace-pre-wrap">{{ entry.conclusion }}</p>
          <details class="mt-2"><summary class="cursor-pointer text-sky-300">依据、信心与条件</summary><p>{{ entry.reasoning }}</p><p>信心 {{ confidence[entry.confidence] }}：{{ entry.confidence_reason }}</p><p>触发：{{ entry.trigger || '未指定' }}</p><p>失效：{{ entry.invalidation || '未指定' }}</p></details>
        </article>
      </div>
      <details v-if="data?.records?.results?.length"><summary class="cursor-pointer text-sm text-sky-300">讨论历史 · {{ data.records.results.length }}</summary><article v-for="record in [...data.records.results].reverse()" :key="record.result_id" class="border-b border-border py-3 text-sm"><p>{{ time(record.confirmed_at) }} · {{ record.provider }}</p><p class="whitespace-pre-wrap">{{ record.summary }}</p></article></details>
    </section>
  </section>
</template>

<style scoped>
.discussion { overflow-wrap: anywhere; }
button { display: inline-flex; align-items: center; gap: 6px; }
button svg { flex-shrink: 0; }
</style>
