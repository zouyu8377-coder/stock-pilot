<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { planRequest } from '../api/client'
const emit = defineEmits<{ (e: 'discuss', value: { level: string; target: string; question: string }): void }>()
const state = ref<any>({ status: 'idle', board: { plans: [], research: [] }, settings: {} })
const error = ref(''), pending = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const states: Record<string, string> = { idle: '尚未检查', running: '检查中', completed: '检查完成', failed: '检查失败', met: '成立', not_met: '未成立', unknown: '无法判断', discussion_required: '需要讨论', evidence_missing: '证据待补齐', monitoring: '继续监控', blocked: '取证受阻', answered: '可计算问题已回答', material_ready: '取得材料，待研判', incomplete: '证据不完整' }
const metrics: Record<string, string> = { latest_close: '最近完整日K收盘价', price_vs_ma20_pct: '相对MA20（%）', return_5d_pct: '5日涨跌（%）', return_20d_pct: '20日涨跌（%）', volume_ratio_5d_pct: '5日均量相对20日均量变化（%）', cash_ratio_pct: '现金比例（%）', invested_ratio_pct: '总仓位（%）', weight_pct: '单票权重（%）' }
const ops: Record<string, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' }
async function load() { try { state.value = await planRequest('/monitor'); error.value = '' } catch { error.value = '本地监控状态暂不可用' } finally { if (!disposed) timer = setTimeout(load, state.value.status === 'running' ? 2500 : 30000) } }
onMounted(load)
onUnmounted(() => { disposed = true; clearTimeout(timer) })
async function run() { pending.value = true; try { state.value = await planRequest('/monitor', {}); clearTimeout(timer); await load() } catch { error.value = '启动检查失败' } finally { pending.value = false } }
async function settings(e: Event) { try { const enabled = (e.target as HTMLInputElement).checked; state.value.settings = await planRequest('/settings', { enabled, external_only: state.value.settings.external_only }); } catch { error.value = '设置保存失败' } }
</script>
<template>
  <section class="border-y border-border py-3 space-y-3 text-sm">
    <div class="flex flex-wrap justify-between gap-2"><h4 class="font-semibold">计划巡检与复盘</h4><button :disabled="pending || state.status === 'running'" class="rounded border border-border px-3 py-2 disabled:opacity-50" @click="run">立即检查（不调用模型）</button></div>
    <div class="flex flex-wrap gap-3 text-xs text-muted-foreground"><span>{{ state.settings.external_only ? '外部模型协作模式 · 内置研判已停用' : '本地检查不调用模型' }}</span><label class="flex items-center gap-2"><input type="checkbox" :checked="state.settings.enabled" @change="settings" />工作日每小时自动检查</label></div>
    <p role="status">{{ states[state.status] || state.status }}<span v-if="state.status === 'running'"> · {{ state.completed }}/{{ state.total }} · {{ state.detail }}</span><span v-else-if="state.board.checked_at"> · {{ state.board.checked_at }}</span></p>
    <p v-if="error || state.error" role="alert" class="text-warning">{{ error || state.error }}</p>
    <p v-if="!state.board.plans.length" class="text-muted-foreground">尚无已确认计划；确认计划后开始跟踪其条件与执行变化。</p>
    <article v-for="p in state.board.plans" :key="p.scope" class="border-b border-border py-3 space-y-2">
      <div class="flex flex-wrap justify-between gap-2"><h5 class="font-semibold">{{ p.target }} · 第{{ p.version }}版</h5><span :class="p.state === 'monitoring' ? 'text-sky-300' : 'text-warning'">{{ states[p.state] }}</span></div>
      <p>{{ p.reason }}</p><p>下一步：{{ p.next_action }}</p><p v-for="a in p.triggered_actions" :key="a">触发后的讨论建议：{{ a }}</p>
      <button class="text-sky-300" @click="emit('discuss', { level: p.level, target: p.target, question: `原计划：${p.next_action}。最新检查：${p.reason}。结合监控证据、原计划和操作变化，是否需要修正？` })">讨论并修正计划</button>
      <details><summary class="cursor-pointer text-sky-300">条件与证据 · {{ p.mode === 'all' ? '同时满足' : '任一满足' }}</summary><p v-if="!p.conditions.length" class="text-warning">原计划没有结构化条件，目前仅检查日期与账户变化。</p><div v-for="(c, i) in p.conditions" :key="i" class="py-2"><p>{{ c.label }} · {{ c.symbol }} · {{ states[c.state] }}</p><p>{{ metrics[c.metric] }} {{ ops[c.operator] }} {{ c.threshold }}；当前 {{ c.value ?? '缺失' }} · {{ c.as_of || '无有效日期' }}</p><p class="text-warning">{{ c.reason }}</p></div></details>
      <details><summary class="cursor-pointer text-sky-300">执行变化与阶段复盘</summary><p>{{ p.operation_review.boundary }}</p><p v-for="c in p.operation_review.items" :key="c.symbol">{{ c.symbol }}：{{ c.before }} → {{ c.after }}（净变化 {{ c.delta }}）· {{ c.assessment }}</p><p v-if="!p.operation_review.items.length">未记录到适用的持仓净变化。</p><p v-if="p.performance_review.price_return_pct != null">计划后 {{ p.performance_review.trading_days }} 个交易日 · 价格变化 {{ p.performance_review.price_return_pct }}% · 相对沪深300ETF {{ p.performance_review.relative_return_pct ?? '缺失' }}个百分点 · 截至 {{ p.performance_review.through }}</p><p>{{ p.performance_review.boundary || p.performance_review.reason }}</p></details>
    </article>
    <details v-if="state.board.research.length"><summary class="text-sky-300 cursor-pointer">研究取证结果 · {{ state.board.research.length }}</summary><article v-for="r in state.board.research" :key="r.id" class="border-b border-border py-2 space-y-1"><p>{{ r.target }} · {{ r.question }} · {{ states[r.state] }}</p><p v-if="typeof r.answer === 'string'">{{ r.answer }}</p><p v-else-if="r.answer">{{ metrics[r.answer.metric] }}：{{ r.answer.value ?? '缺失' }} · {{ states[r.answer.state] }} · {{ r.answer.as_of }}</p><p class="text-warning">{{ r.error }}</p><p class="text-xs text-muted-foreground">最近检查 {{ r.checked_at }} · 最早再次取证 {{ r.next_attempt_at }}</p><button class="text-sky-300" @click="emit('discuss', { level: r.level, target: r.target, question: `请根据最新取证材料回答：${r.question}，区分事实、缺口和对投资计划的影响。` })">讨论材料</button><details v-if="r.data"><summary class="cursor-pointer">原始证据</summary><pre class="text-xs whitespace-pre-wrap break-all max-h-72 overflow-auto">{{ JSON.stringify(r.data, null, 2) }}</pre></details></article></details>
    <p class="text-xs text-muted-foreground">仅检查已登记条件，不代表覆盖全部风险；定时任务需后端持续运行。不会自动修改计划或交易。</p>
  </section>
</template>
