<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { BrainCircuit, Database, ShieldCheck, Play, SkipForward, Square, Copy, Check, RefreshCw, ArrowRight, AlertTriangle, Network } from 'lucide-vue-next'
import { demoRequest, DEMO_API, type DemoRun, type DemoScenario } from '../api/demoClient'

const scenarios = ref<DemoScenario[]>([])
const scenario = ref('evidence_gap')
const mode = ref('sample')
const publicMarket = ref(false)
const run = ref<DemoRun | null>(null)
const busy = ref(false)
const autoplay = ref(false)
const error = ref('')
const notice = ref('')
const pasted = ref('')
const elapsed = ref(0)
const showAllEvents = ref(false)
let disposed = false
let timer: ReturnType<typeof setInterval> | undefined
const storageKey = 'stock-pilot-collaboration-demo-run'
const labels: Record<string, string> = { analyst_ready: '等待分析侧', collector_ready: '等待采集执行', collecting: '采集执行中', validating: '验收中', awaiting_external: '等待外部模型回传', awaiting_confirmation: '等待人工确认', confirmed: '已确认', cancelled: '已停止', failed: '已停止 · 需处理' }
const roles: Record<string, string> = { analyst: '分析侧', collector: '采集侧', coordinator: '协调程序', validator: '校验程序', human: '体验者', tool: '受限工具' }
const confidence: Record<string, string> = { high: '高', medium: '中', low: '低', unknown: '未知' }
const terminal = computed(() => !!run.value && ['confirmed', 'cancelled', 'failed'].includes(run.value.phase))
const actionable = computed(() => !!run.value && ['analyst_ready', 'collector_ready', 'collecting', 'validating'].includes(run.value.phase))
const report = computed(() => run.value?.pending_report?.report)
const events = computed(() => showAllEvents.value ? run.value?.events || [] : (run.value?.events || []).slice(-8))
const currentScenario = computed(() => scenarios.value.find(s => s.id === (run.value?.scenario || scenario.value)))
const time = (v: string) => new Date(v).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const number = (v: unknown) => typeof v === 'number' ? v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '--'

async function refresh() {
  if (!run.value) return
  run.value = await demoRequest<DemoRun>(`/runs/${run.value.run_id}`)
}
async function action(task: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''; elapsed.value = 0
  try { await task() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败'; await refresh().catch(() => undefined) }
  finally { busy.value = false }
}
async function create() {
  autoplay.value = false
  await action(async () => {
    run.value = await demoRequest<DemoRun>('/runs', { scenario: scenario.value, mode: mode.value, public_market: publicMarket.value })
    localStorage.setItem(storageKey, run.value.run_id)
    showAllEvents.value = false
  })
}
async function oneStep() {
  if (!run.value) return
  run.value = await demoRequest<DemoRun>(`/runs/${run.value.run_id}/step`, { revision: run.value.revision })
}
async function step() { await action(oneStep) }
async function play() {
  autoplay.value = true
  await action(async () => {
    for (let i = 0; i < 30 && autoplay.value && !disposed && actionable.value; i++) {
      await oneStep()
      await new Promise(resolve => setTimeout(resolve, 220))
    }
  })
  autoplay.value = false
}
async function stop() {
  autoplay.value = false
  error.value = ''
  try {
    await refresh()
    if (run.value && !terminal.value) run.value = await demoRequest<DemoRun>(`/runs/${run.value.run_id}/cancel`, { revision: run.value.revision })
  } catch (e) { error.value = e instanceof Error ? e.message : '停止失败' }
}
async function confirm() {
  await action(async () => {
    if (!run.value) return
    run.value = await demoRequest<DemoRun>(`/runs/${run.value.run_id}/confirm`, { revision: run.value.revision, preview_digest: run.value.preview_digest })
  })
}
async function copyPrompt() {
  await action(async () => {
    if (!run.value) return
    const result = await demoRequest<{ prompt: string }>(`/runs/${run.value.run_id}/prompt`)
    await navigator.clipboard.writeText(result.prompt)
    notice.value = '已复制当前资料与回传协议'
  })
}
async function submit() {
  await action(async () => {
    if (!run.value) return
    run.value = await demoRequest<DemoRun>(`/runs/${run.value.run_id}/reply`, { revision: run.value.revision, reply: JSON.parse(pasted.value) })
    if (run.value.events[run.value.events.length - 1]?.kind !== 'rejected') pasted.value = ''
  })
}
function evidence(refId: string) { document.getElementById(`evidence-${refId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }

onMounted(async () => {
  try {
    scenarios.value = (await demoRequest<{ scenarios: DemoScenario[] }>('/scenarios')).scenarios
    const previous = localStorage.getItem(storageKey)
    if (previous) {
      try { run.value = await demoRequest<DemoRun>(`/runs/${previous}`) }
      catch { localStorage.removeItem(storageKey) }
    }
  } catch { error.value = `演示服务未连接：${DEMO_API}。请启动独立演示后端。` }
  timer = setInterval(() => { if (busy.value) elapsed.value++ }, 1000)
})
onUnmounted(() => { disposed = true; autoplay.value = false; if (timer) clearInterval(timer) })
</script>

<template>
  <div class="demo-shell">
    <header class="demo-topbar"><div class="demo-brand"><Network :size="23" /><strong>Stock-Pilot</strong><span>v4.4 · Collaboration Lab</span></div><span class="demo-label">双 Agent 架构原型</span></header>
    <main>
      <header class="demo-heading"><div><p class="demo-eyebrow">合成账户 · 独立会话 · 不执行交易</p><h1>证据协作工作台</h1></div><p class="demo-provenance">{{ run?.mode === 'manual' ? '人工交接外部模型' : '分析侧：响应样本，非实时模型推理' }}<br />{{ run?.public_market ? '公开行情联网取数；财报仍为合成素材' : '离线合成资料 · 场景参考日 2026-10-26' }}</p></header>
      <form class="demo-toolbar" @submit.prevent="create">
        <label>演示场景<select v-model="scenario" aria-label="演示场景" :disabled="busy"><option v-for="item in scenarios" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <fieldset><legend>分析方式</legend><label><input v-model="mode" type="radio" value="sample" :disabled="busy" />响应样本</label><label><input v-model="mode" type="radio" value="manual" :disabled="busy" />手动外部模型</label></fieldset>
        <label class="demo-checkbox"><input v-model="publicMarket" type="checkbox" :disabled="busy" />联网获取公开行情</label>
        <button type="submit" class="demo-primary" :disabled="busy || !scenarios.length"><Play :size="16" />新建演示</button>
      </form>
      <p v-if="error" role="alert" class="demo-error"><AlertTriangle :size="17" />{{ error }}</p>
      <p v-if="notice" role="status" class="demo-notice">{{ notice }}</p>

      <section class="demo-agents" aria-label="协作角色">
        <article :class="{ active: run && ['analyst_ready', 'awaiting_external'].includes(run.phase) }"><BrainCircuit :size="24" /><div><h2>分析侧 Agent</h2><p>{{ run?.mode === 'manual' ? '外部模型 · 人工交接' : '样本驱动 · 证据需求与结论' }}</p></div><span>{{ run?.analyst_turns || 0 }} 轮</span></article>
        <article :class="{ active: run && ['collector_ready', 'collecting'].includes(run.phase) }"><Database :size="24" /><div><h2>采集侧 Agent</h2><p>受限工具 · 结构化证据返回</p></div><span>{{ run?.tool_calls || 0 }} 次</span></article>
        <article :class="{ active: run && ['validating', 'awaiting_confirmation', 'confirmed'].includes(run.phase) }"><ShieldCheck :size="24" /><div><h2>协调与校验程序</h2><p>版本 · 权限 · 预算 · 确认</p></div><span>非模型</span></article>
      </section>

      <template v-if="run">
        <section class="demo-runbar" aria-live="polite"><div><strong>{{ labels[run.phase] || run.phase }}</strong><span>{{ currentScenario?.name }} · 资料 v{{ run.context.version }}</span></div><div class="demo-run-actions"><span v-if="busy">执行中 {{ elapsed }} 秒</span><button v-if="actionable" :disabled="busy" @click="step"><SkipForward :size="16" />下一步</button><button v-if="actionable" class="demo-primary" :disabled="busy" @click="play"><Play :size="16" />运行至待确认</button><button v-if="!terminal" title="停止当前演示任务" aria-label="停止当前演示任务" @click="stop"><Square :size="16" /></button><button title="读取已保存状态" aria-label="读取已保存状态" :disabled="busy" @click="action(refresh)"><RefreshCw :size="16" /></button></div></section>
        <p v-if="run.error" class="demo-error">{{ run.error }}</p>
        <div class="demo-grid">
          <section class="demo-timeline"><header class="demo-section-head"><h2>协作轨迹</h2><span>{{ run.events.length }} 条交接</span></header>
            <ol><li v-for="item in events" :key="item.id" :class="{ rejected: ['rejected', 'tool_failed', 'tool_exhausted'].includes(item.kind) }"><div class="demo-event-meta"><span>{{ roles[item.sender] || item.sender }} <ArrowRight :size="12" /> {{ roles[item.receiver] || item.receiver }}</span><time>{{ time(item.at) }} · v{{ item.context_version }}</time></div><h3>{{ item.title }}</h3><p>{{ item.detail }}</p></li></ol>
            <button v-if="run.events.length > 8" class="demo-text-button" @click="showAllEvents = !showAllEvents">{{ showAllEvents ? '仅显示最近8条' : `展开全部 ${run.events.length} 条` }}</button>
          </section>
          <aside class="demo-evidence"><header class="demo-section-head"><h2>证据与验收</h2><span>{{ run.context.payload.evidence.length }} 项证据</span></header>
            <dl class="demo-budget"><div><dt>工具调用 / 上限</dt><dd>{{ run.tool_calls }} / {{ run.limits.tool_calls }}</dd></div><div><dt>返工 / 上限</dt><dd>{{ run.repairs }} / {{ run.limits.repairs }}</dd></div><div><dt>平台模型调用</dt><dd>{{ run.model_calls }} 次</dd></div><div><dt>平台模型 Token</dt><dd>{{ run.tokens }}</dd></div></dl>
            <p v-if="!run.context.payload.evidence.length" class="demo-muted demo-empty">尚无资料工具返回；初始包仅包含合成账户。</p>
            <article v-for="item in run.context.payload.evidence" :id="`evidence-${item.id}`" :key="item.id" class="demo-evidence-item"><h3>{{ item.id }} · {{ item.tool }} <span :class="item.data.synthetic ? 'demo-synthetic' : 'demo-live'">{{ item.data.synthetic ? '合成素材' : '公开行情' }}</span></h3><p class="demo-source">{{ item.data.source }} · {{ item.data.observed_at }}</p><p>{{ item.data.note }}</p>
              <p v-if="item.data.stale" class="demo-error">资料已过期，不能视为当前行情</p>
              <table v-if="item.data.rows"><thead><tr><th>标的</th><th>价格</th><th>合成账户权重</th></tr></thead><tbody><tr v-for="row in item.data.rows" :key="row.symbol"><td>{{ row.symbol }}</td><td>{{ number(row.price) }}</td><td>{{ number(row.account_weight_pct) }}%</td></tr></tbody></table>
              <details><summary>结构化证据</summary><pre>{{ JSON.stringify(item.data, null, 2) }}</pre></details>
            </article>
            <details class="demo-version"><summary>版本与指纹 · {{ run.versions.length }} 版</summary><p v-for="v in run.versions" :key="v.version">v{{ v.version }} · {{ v.fingerprint.slice(0, 16) }}…</p><p>会话 {{ run.run_id }}</p></details>
          </aside>
        </div>
        <section v-if="run.mode === 'manual'" class="demo-manual"><header class="demo-section-head"><h2>外部模型交接</h2><button :disabled="busy" @click="copyPrompt"><Copy :size="15" />复制当前资料与协议</button></header><textarea v-model="pasted" aria-label="外部分析侧 JSON 回传" placeholder="结构化分析回复 JSON" maxlength="100000" /><button :disabled="busy || !pasted.trim() || run.phase !== 'awaiting_external'" @click="submit">校验回传</button></section>
        <section v-if="report" class="demo-report"><header class="demo-section-head"><h2>{{ run.phase === 'confirmed' ? '已确认演示结论' : run.phase === 'validating' ? '待校验分析稿' : '结论预览' }}</h2><span>{{ run.pending_report?.provider }}</span></header><h3>{{ report.summary }}</h3>
          <article v-for="(finding, index) in report.findings" :key="index"><h4>{{ finding.title }} · 信心{{ confidence[finding.confidence] }}</h4><p>{{ finding.conclusion }}</p><p class="demo-muted">{{ finding.reasoning }}</p><div class="demo-refs"><button v-for="refId in finding.evidence_refs" :key="refId" @click="evidence(refId)">{{ refId }}</button></div></article>
          <h4>未解决事项</h4><ul><li v-for="gap in report.unresolved" :key="gap">{{ gap }}</li></ul>
          <button v-if="run.phase === 'awaiting_confirmation'" class="demo-primary" :disabled="busy" @click="confirm"><Check :size="17" />确认演示结论，不变更持仓</button>
        </section>
      </template>
      <section v-else class="demo-initial"><h2>合成账户</h2><table><thead><tr><th>工具编码</th><th>样本标的</th><th>数量</th></tr></thead><tbody><tr><td>600519</td><td>消费样本A</td><td>100</td></tr><tr><td>600036</td><td>银行样本B</td><td>2,000</td></tr><tr><td>510300</td><td>宽基样本C</td><td>10,000</td></tr></tbody></table><p class="demo-muted">合成现金 ¥100,000 · 财报与事件素材不代表真实证券事实</p></section>
      <footer class="demo-footer">架构演示，不构成投资建议。样本模式不验证模型推理效果；人工外部交接不等于自主多 Agent。接口协议为项目内部协议，未声明 A2A 兼容。</footer>
    </main>
  </div>
</template>
