<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getResearchWorkbench, respondToDecision, type ResearchWorkbench, type HoldingDecision } from '../api/client'
import DecisionReasoning from './DecisionReasoning.vue'
import ResearchDossier from './ResearchDossier.vue'
import TradePreview from './TradePreview.vue'
const props = defineProps<{ revision?: string; issues?: { subject: string; reason: string; action: string; symbol?: string }[] }>()
const emit = defineEmits<{ (e: 'select-symbol', symbol: string): void; (e: 'update-analysis'): void }>()
const data = ref<ResearchWorkbench | null>(null)
const error = ref('')
const saving = ref('')
const showAll = ref(false)
const notes = ref<Record<string, string>>({})
const states: Record<string, string> = { pending: '待处理', monitoring: '持续关注', dismissed: '暂不采纳' }
const actions = computed(() => [...(data.value?.actions || [])].sort((a, b) => Number(a.state !== 'pending') - Number(b.state !== 'pending')))
const uncovered = computed(() => props.issues?.filter(i => !actions.value.some(a => i.symbol?.includes(a.symbol))) || [])
const dossier = (s: string) => data.value?.dossiers.find(d => d.symbol === s)
const rules = (s: string) => props.issues?.filter(i => i.symbol?.includes(s)) || []
async function load() {
  try { data.value = await getResearchWorkbench(); error.value = '' }
  catch { error.value = '研究档案暂不可达；不能确认取证与处理状态。' }
}
async function respond(item: HoldingDecision, state: string) {
  saving.value = item.id
  try { await respondToDecision(item, state, notes.value[item.id] || ''); await load() }
  catch (e: any) { error.value = e.response?.data?.detail || '记录失败，请重试' }
  finally { saving.value = '' }
}
onMounted(load)
watch(() => props.revision, load)
</script>
<template>
  <div class="min-w-0 [overflow-wrap:anywhere]">
    <p v-if="error" role="alert" class="py-2 text-sm text-warning">{{ error }}</p>
    <p v-if="data?.account_update?.status === 'pending'" class="mt-2 text-xs text-sky-300">账户更新后的分析已排队，后台空闲后启动；无需重复提交。</p>
    <p v-if="data?.needs_refresh" class="mt-2 text-xs text-warning">账户已变化或分析不是今日生成，历史建议仅供参考。<button class="ml-2 text-sky-300" @click="emit('update-analysis')">更新分析</button></p>
    <div v-for="issue in uncovered" :key="issue.subject" class="border-b border-border py-3 text-sm"><p class="font-medium text-warning">{{ issue.subject }}</p><p>{{ issue.reason }}</p><p class="text-muted-foreground">{{ issue.action }}</p></div>
    <article v-for="item in actions.slice(0, showAll ? actions.length : 3)" :key="item.id" class="border-b border-border py-4 text-sm">
      <div class="flex flex-wrap items-baseline justify-between gap-2"><button class="font-semibold text-sky-300" @click="emit('select-symbol', item.symbol)">{{ item.name }} <span class="font-mono text-xs">{{ item.symbol }}</span></button><span class="text-xs text-muted-foreground">{{ states[item.state] }}</span></div>
      <p v-if="item.changed_since_response" class="mt-1 text-xs text-warning">建议已变化，需要重新判断；此前处理记录保留。</p>
      <p class="mt-2 font-medium">{{ item.needs_refresh ? '历史建议' : '当前建议' }}：{{ item.primary.action_semantics }}</p>
      <p class="mt-1 text-muted-foreground">{{ item.primary.conclusion }}</p>
      <p v-for="rule in rules(item.symbol)" :key="rule.subject" class="mt-1 text-xs text-warning">账户约束：{{ rule.reason }}</p>
      <p v-if="item.primary.account_impact" class="mt-2 text-xs">账户影响：{{ item.primary.account_impact }}</p>
      <p class="mt-1 text-xs">调整条件：{{ item.primary.trigger_condition || '尚未明确，不据此自动调整' }} · {{ item.primary.horizon || '下次更新分析时复核' }}</p>
      <DecisionReasoning :item="item.primary" />
      <TradePreview v-if="!item.needs_refresh" :symbol="item.symbol" :name="item.name" />
      <details v-if="item.related.length" class="mt-2 text-xs"><summary class="cursor-pointer text-sky-300">合并的其他判断 {{ item.related.length }} 项</summary><p v-for="other in item.related" :key="other.item_id" class="mt-2">{{ other.conclusion }} · {{ other.action_semantics }}</p></details>
      <details v-if="dossier(item.symbol)" class="mt-2"><summary class="cursor-pointer text-xs text-sky-300">研究档案 · {{ item.unanswered }} 个问题尚未得到原文验证</summary><ResearchDossier class="mt-3" :dossier="dossier(item.symbol)!" /></details>
      <details class="mt-3 text-xs"><summary class="cursor-pointer text-sky-300">处理建议</summary><div class="mt-2 space-y-2">
        <input v-model="notes[item.id]" class="h-9 w-full rounded border border-border bg-background px-2" :aria-label="`${item.name}处理原因`" placeholder="处理原因（暂不采纳时必填）" maxlength="500" />
        <div class="flex flex-wrap gap-2"><button v-for="state in ['monitoring', 'dismissed', 'pending']" :key="state" class="rounded border border-border px-3 py-2 disabled:opacity-50" :disabled="!!saving || item.needs_refresh" @click="respond(item, state)">{{ state === 'pending' ? '恢复待处理' : states[state] }}</button></div>
        <p class="text-muted-foreground">这里只记录决策状态，不代表成交，不会调整真实持仓。</p>
      </div></details>
      <details v-if="item.history.length" class="mt-2 text-xs"><summary class="cursor-pointer text-muted-foreground">处理记录</summary><p v-for="(row, index) in item.history" :key="index">{{ row.at }} · {{ states[row.state] }} · {{ row.note }}</p></details>
    </article>
    <button v-if="actions.length > 3" class="mt-3 text-xs text-sky-300" @click="showAll = !showAll">{{ showAll ? '收起' : `全部 ${actions.length} 个持仓事项` }}</button>
    <p v-if="data && !actions.length" class="py-3 text-sm text-muted-foreground">尚无可关联持仓的分析建议，可先查看研究档案并更新分析。</p>
    <details v-if="data?.dossiers.length" class="mt-4 border-t border-border pt-3"><summary class="cursor-pointer text-sm text-sky-300">全部持仓研究档案 · {{ data.dossiers.length }} 个标的</summary><details v-for="record in data.dossiers" :key="record.symbol" class="border-b border-border py-3"><summary class="cursor-pointer text-sm">{{ record.name }} · {{ record.symbol }}</summary><ResearchDossier class="mt-3" :dossier="record" /></details></details>
  </div>
</template>
