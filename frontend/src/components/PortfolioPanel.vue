<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  addManualEvidence,
  createPortfolioAnalysisPacket,
  deleteManualEvidence,
  getPortfolio,
  getPortfolioSnapshot,
  listManualEvidence,
  savePortfolio,
  simulateTrade,
  updateManualEvidenceInclude,
  type ManualEvidenceRecord,
  type PortfolioState,
} from '../api/client'

const expanded = ref(false)
const loading = ref(false)
const saving = ref(false)
const state = ref<PortfolioState | null>(null)
const evidence = ref<ManualEvidenceRecord[]>([])
const snapshotPreview = ref('')
const packetMarkdown = ref('')
const packetJson = ref('')
const packetPaths = ref<Record<string, string> | null>(null)
const packetCopied = ref(false)
const packetLoading = ref(false)
const simResult = ref<any | null>(null)

const positionDraft = ref({
  symbol: '',
  name: '',
  quantity: 0,
  avg_cost: 0,
  position_role: 'observation',
  primary_theme: 'AI_PCB',
  theme_tags_text: 'AI_PCB',
  user_plan: '',
  target_max_weight: null as number | null,
})

const evidenceDraft = ref({
  symbol: '',
  evidence_type: 'shareholder_count_manual',
  title: '',
  text: '',
  source: '用户录入',
  reliability: 'B_manual_structured',
  llm_usage: 'fact_with_limit',
  holder_num: null as number | null,
  end_date: '',
  include_in_analysis_packet: true,
})

const tradeDraft = ref({
  side: 'buy',
  symbol: '',
  name: '',
  amount: 0,
  quantity: null as number | null,
  estimated_price: 0,
  reason: '',
  planned: true,
  primary_theme: 'AI_PCB',
  theme_tags_text: 'AI_PCB',
})

const accountDraft = ref({
  cash_available: 0,
  repo_amount: 0,
  total_assets: null as number | null,
  max_position_weight: 35,
  max_theme_weight: 50,
  min_cash_ratio: 5,
})

const fmt = (v?: number | null, suffix = '') => {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const positions = computed(() => state.value?.snapshot.positions || [])
const metrics = computed(() => state.value?.metrics)

const parseTags = (text: string) => text.split(',').map((x) => x.trim()).filter(Boolean)

const load = async () => {
  loading.value = true
  try {
    state.value = await getPortfolio()
    evidence.value = await listManualEvidence()
    accountDraft.value.cash_available = state.value.snapshot.cash_available
    accountDraft.value.repo_amount = state.value.snapshot.repo_amount
    accountDraft.value.total_assets = state.value.snapshot.total_assets ?? null
    accountDraft.value.max_position_weight = state.value.snapshot.risk_limits.max_position_weight
    accountDraft.value.max_theme_weight = state.value.snapshot.risk_limits.max_theme_weight
    accountDraft.value.min_cash_ratio = state.value.snapshot.risk_limits.min_cash_ratio
  } finally {
    loading.value = false
  }
}

const persist = async (nextPositions: any[] = positions.value) => {
  saving.value = true
  try {
    state.value = await savePortfolio({
      portfolio_id: state.value?.snapshot.portfolio_id || 'local_default',
      snapshot_time: new Date().toISOString(),
      total_assets: accountDraft.value.total_assets,
      cash_available: Number(accountDraft.value.cash_available || 0),
      repo_amount: Number(accountDraft.value.repo_amount || 0),
      risk_limits: {
        max_position_weight: Number(accountDraft.value.max_position_weight || 35),
        max_theme_weight: Number(accountDraft.value.max_theme_weight || 50),
        min_cash_ratio: Number(accountDraft.value.min_cash_ratio || 5),
      },
      positions: nextPositions.map((p: any) => ({
        symbol: p.symbol,
        name: p.name,
        quantity: Number(p.quantity || 0),
        available_quantity: p.available_quantity ?? null,
        avg_cost: Number(p.avg_cost || 0),
        position_role: p.position_role || 'observation',
        theme_tags: p.theme_tags || [],
        primary_theme: p.primary_theme || null,
        user_plan: p.user_plan || '',
        invalid_condition: p.invalid_condition || null,
        target_max_weight: p.target_max_weight ?? null,
        notes: p.notes || null,
      })),
    })
  } finally {
    saving.value = false
  }
}

const addPosition = async () => {
  const next = [
    ...positions.value,
    {
      ...positionDraft.value,
      theme_tags: parseTags(positionDraft.value.theme_tags_text),
      quantity: Number(positionDraft.value.quantity || 0),
      avg_cost: Number(positionDraft.value.avg_cost || 0),
    },
  ]
  await persist(next)
  positionDraft.value.symbol = ''
  positionDraft.value.name = ''
  positionDraft.value.quantity = 0
  positionDraft.value.avg_cost = 0
}

const removePosition = async (symbol: string) => {
  await persist(positions.value.filter((p) => p.symbol !== symbol))
}

const submitEvidence = async () => {
  await addManualEvidence({
    ...evidenceDraft.value,
    symbol: evidenceDraft.value.symbol || null,
    holder_num: evidenceDraft.value.holder_num,
    end_date: evidenceDraft.value.end_date || null,
    as_of_date: evidenceDraft.value.end_date || null,
  })
  evidence.value = await listManualEvidence()
  evidenceDraft.value.title = ''
  evidenceDraft.value.text = ''
  evidenceDraft.value.holder_num = null
}

const deleteEvidence = async (id: string) => {
  await deleteManualEvidence(id)
  evidence.value = await listManualEvidence()
}

const toggleEvidenceInclude = async (item: ManualEvidenceRecord) => {
  const updated = await updateManualEvidenceInclude(item.evidence_id, !item.include_in_analysis_packet)
  evidence.value = evidence.value.map((record) => record.evidence_id === updated.evidence_id ? updated : record)
}

const runSimulation = async () => {
  simResult.value = await simulateTrade({
    ...tradeDraft.value,
    amount: tradeDraft.value.amount || null,
    quantity: tradeDraft.value.quantity || null,
    estimated_price: Number(tradeDraft.value.estimated_price || 0),
    theme_tags: parseTags(tradeDraft.value.theme_tags_text),
  })
}

const buildSnapshot = async () => {
  const snap = await getPortfolioSnapshot()
  snapshotPreview.value = JSON.stringify({
    snapshot_id: snap.snapshot_id,
    analysis_scope: snap.analysis_scope,
    evidence_count: snap.evidence_items?.length,
    target_symbols: snap.target_symbols,
    missing_data: snap.missing_data,
  }, null, 2)
}

const buildPortfolioPacket = async () => {
  packetLoading.value = true
  packetCopied.value = false
  try {
    const result = await createPortfolioAnalysisPacket()
    packetMarkdown.value = result.markdown
    packetJson.value = JSON.stringify(result.packet, null, 2)
    packetPaths.value = result.saved_paths || null
  } finally {
    packetLoading.value = false
  }
}

const copyPortfolioPacket = async () => {
  if (!packetMarkdown.value) return
  await navigator.clipboard.writeText(packetMarkdown.value)
  packetCopied.value = true
}

onMounted(load)
</script>

<template>
  <section class="mb-4 rounded-lg border border-border bg-card">
    <button
      class="flex w-full items-center justify-between px-3 py-2 text-left"
      @click="expanded = !expanded"
    >
      <div>
        <h2 class="text-sm font-semibold text-foreground">组合与手动证据</h2>
        <p class="text-[11px] text-muted-foreground">本地保存，不自动发送给外部LLM</p>
      </div>
      <span class="text-xs text-muted-foreground">{{ expanded ? '收起' : '展开' }}</span>
    </button>

    <div v-if="expanded" class="space-y-4 border-t border-border p-3">
      <div v-if="loading" class="text-xs text-muted-foreground">加载组合...</div>
      <template v-if="state && metrics">
        <div class="grid grid-cols-5 gap-2 text-xs">
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">总资产</div><div class="font-mono">{{ fmt(metrics.total_assets) }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">总市值</div><div class="font-mono">{{ fmt(metrics.total_market_value) }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">现金</div><div class="font-mono">{{ fmt(metrics.cash_available) }} / {{ fmt(metrics.cash_ratio_pct, '%') }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">逆回购</div><div class="font-mono">{{ fmt(metrics.repo_amount) }} / {{ fmt(metrics.repo_ratio_pct, '%') }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">总仓位</div><div class="font-mono">{{ fmt(metrics.invested_ratio_pct, '%') }}</div></div>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="rounded border border-border/60 p-2">
            <h3 class="mb-2 text-xs font-semibold">主题唯一归属</h3>
            <div v-for="item in metrics.primary_theme_exposures" :key="item.theme" class="mb-1 flex justify-between text-xs">
              <span>{{ item.theme }}</span><span class="font-mono">{{ fmt(item.weight_pct, '%') }}</span>
            </div>
          </div>
          <div class="rounded border border-border/60 p-2">
            <h3 class="mb-2 text-xs font-semibold">相关风险标签</h3>
            <div v-for="item in metrics.risk_tag_exposures" :key="item.theme" class="mb-1 flex justify-between text-xs">
              <span>{{ item.theme }}</span><span class="font-mono">{{ fmt(item.weight_pct, '%') }}</span>
            </div>
          </div>
          <div class="rounded border border-border/60 p-2">
            <h3 class="mb-2 text-xs font-semibold">规则提醒</h3>
            <div v-if="metrics.warnings.length === 0" class="text-xs text-muted-foreground">暂无触发</div>
            <div v-for="w in metrics.warnings" :key="w" class="mb-1 text-xs text-warning">{{ w }}</div>
            <div v-for="n in metrics.composite_exposure_notes" :key="n" class="mb-1 text-xs text-muted-foreground">{{ n }}</div>
          </div>
        </div>

        <div class="overflow-x-auto rounded border border-border/60">
          <table class="w-full text-xs">
            <thead class="bg-secondary/40 text-muted-foreground">
              <tr><th class="p-2 text-left">标的</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>主题</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="p in positions" :key="p.symbol" class="border-t border-border/50">
                <td class="p-2">{{ p.symbol }} {{ p.name }}</td>
                <td class="text-right">{{ fmt(p.quantity) }}</td>
                <td class="text-right">{{ fmt(p.avg_cost) }}</td>
                <td class="text-right">{{ fmt(p.market_price) }}</td>
                <td class="text-right">{{ fmt(p.market_value) }}</td>
                <td class="text-right">{{ fmt(p.unrealized_pnl) }} / {{ fmt(p.unrealized_pnl_pct, '%') }}</td>
                <td class="px-2">{{ p.primary_theme }} · {{ p.theme_tags.join(',') }}</td>
                <td class="p-2 text-right"><button class="text-negative" @click="removePosition(p.symbol)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="grid grid-cols-6 gap-2 text-xs">
          <input v-model="positionDraft.symbol" class="rounded bg-input px-2 py-1" placeholder="代码" />
          <input v-model="positionDraft.name" class="rounded bg-input px-2 py-1" placeholder="名称" />
          <input v-model.number="positionDraft.quantity" class="rounded bg-input px-2 py-1" type="number" placeholder="数量" />
          <input v-model.number="positionDraft.avg_cost" class="rounded bg-input px-2 py-1" type="number" placeholder="成本" />
          <input v-model="positionDraft.primary_theme" class="rounded bg-input px-2 py-1" placeholder="primary_theme" />
          <input v-model="positionDraft.theme_tags_text" class="rounded bg-input px-2 py-1" placeholder="标签逗号分隔" />
          <input v-model.number="accountDraft.cash_available" class="rounded bg-input px-2 py-1" type="number" placeholder="现金" />
          <input v-model.number="accountDraft.repo_amount" class="rounded bg-input px-2 py-1" type="number" placeholder="逆回购" />
          <input v-model.number="accountDraft.max_position_weight" class="rounded bg-input px-2 py-1" type="number" placeholder="单票上限%" />
          <input v-model.number="accountDraft.max_theme_weight" class="rounded bg-input px-2 py-1" type="number" placeholder="主题上限%" />
          <input v-model.number="accountDraft.min_cash_ratio" class="rounded bg-input px-2 py-1" type="number" placeholder="现金底线%" />
          <button class="rounded bg-primary px-3 py-1" :disabled="saving" @click="addPosition">新增/保存</button>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="rounded border border-border/60 p-2">
            <h3 class="mb-2 text-xs font-semibold">手动证据</h3>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <input v-model="evidenceDraft.symbol" class="rounded bg-input px-2 py-1" placeholder="代码，可空" />
              <select v-model="evidenceDraft.evidence_type" class="rounded bg-input px-2 py-1">
                <option value="shareholder_count_manual">股东户数</option>
                <option value="unlock_event_manual">解禁事件</option>
                <option value="intraday_screenshot">盘中截图</option>
                <option value="manual_market_observation">手动观察</option>
                <option value="trade_plan">交易计划</option>
                <option value="announcement_excerpt_manual">公告摘录</option>
                <option value="survey_excerpt_manual">调研摘录</option>
                <option value="macro_observation_manual">宏观观察</option>
              </select>
              <input v-model="evidenceDraft.title" class="rounded bg-input px-2 py-1" placeholder="标题" />
              <input v-model="evidenceDraft.end_date" class="rounded bg-input px-2 py-1" type="date" />
              <input v-model.number="evidenceDraft.holder_num" class="rounded bg-input px-2 py-1" type="number" placeholder="股东户数" />
              <label class="flex items-center gap-2"><input v-model="evidenceDraft.include_in_analysis_packet" type="checkbox" />纳入分析包</label>
              <textarea v-model="evidenceDraft.text" class="col-span-2 rounded bg-input px-2 py-1" rows="2" placeholder="说明/摘录/观察"></textarea>
              <button class="rounded bg-primary px-3 py-1" @click="submitEvidence">新增证据</button>
            </div>
            <div class="mt-2 space-y-1">
              <div v-for="item in evidence" :key="item.evidence_id" class="flex justify-between gap-2 rounded bg-secondary/25 p-2 text-xs">
                <button class="text-muted-foreground" @click="toggleEvidenceInclude(item)">
                  {{ item.include_in_analysis_packet ? 'Exclude' : 'Include' }}
                </button>
                <span>{{ item.title }} · {{ item.evidence_type }} · {{ item.include_in_analysis_packet ? '纳入' : '不纳入' }}</span>
                <button class="text-negative" @click="deleteEvidence(item.evidence_id)">删除</button>
              </div>
            </div>
          </div>

          <div class="rounded border border-border/60 p-2">
            <h3 class="mb-2 text-xs font-semibold">拟交易模拟</h3>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <select v-model="tradeDraft.side" class="rounded bg-input px-2 py-1"><option value="buy">买入</option><option value="sell">卖出</option></select>
              <input v-model="tradeDraft.symbol" class="rounded bg-input px-2 py-1" placeholder="代码" />
              <input v-model="tradeDraft.name" class="rounded bg-input px-2 py-1" placeholder="名称" />
              <input v-model.number="tradeDraft.amount" class="rounded bg-input px-2 py-1" type="number" placeholder="金额" />
              <input v-model.number="tradeDraft.estimated_price" class="rounded bg-input px-2 py-1" type="number" placeholder="估算价" />
              <input v-model="tradeDraft.primary_theme" class="rounded bg-input px-2 py-1" placeholder="primary_theme" />
              <input v-model="tradeDraft.theme_tags_text" class="rounded bg-input px-2 py-1" placeholder="标签逗号分隔" />
              <input v-model="tradeDraft.reason" class="rounded bg-input px-2 py-1" placeholder="理由" />
              <button class="rounded bg-primary px-3 py-1" @click="runSimulation">模拟</button>
            </div>
            <div v-if="simResult" class="mt-2 space-y-1 text-xs">
              <div>现金比例：{{ fmt(simResult.before.cash_ratio_pct, '%') }} -> {{ fmt(simResult.after.cash_ratio_pct, '%') }}</div>
              <div>总仓位：{{ fmt(simResult.before.invested_ratio_pct, '%') }} -> {{ fmt(simResult.after.invested_ratio_pct, '%') }}</div>
              <div v-for="w in simResult.warnings" :key="w" class="text-warning">{{ w }}</div>
              <div v-for="n in simResult.risk_notes" :key="n" class="text-muted-foreground">{{ n }}</div>
            </div>
          </div>
        </div>

        <div class="rounded border border-border/60 p-2">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="text-xs font-semibold">Portfolio Analysis Snapshot</h3>
            <button class="rounded bg-secondary px-3 py-1 text-xs" @click="buildSnapshot">生成JSON摘要</button>
          </div>
          <pre v-if="snapshotPreview" class="max-h-40 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ snapshotPreview }}</pre>
        </div>

        <div class="rounded border border-border/60 p-2">
          <div class="mb-2 flex items-center justify-between">
            <div>
              <h3 class="text-xs font-semibold">Portfolio Analysis Packet v1</h3>
              <p class="text-[11px] text-muted-foreground">Local preview only. May include real holdings, cost, cash, and manual evidence; no external LLM call is made.</p>
            </div>
            <div class="flex gap-2">
              <button class="rounded bg-secondary px-3 py-1 text-xs" :disabled="!packetMarkdown" @click="copyPortfolioPacket">
                {{ packetCopied ? 'Copied' : 'Copy Markdown' }}
              </button>
              <button class="rounded bg-primary px-3 py-1 text-xs" :disabled="packetLoading" @click="buildPortfolioPacket">
                {{ packetLoading ? 'Generating...' : 'Generate Portfolio Packet' }}
              </button>
            </div>
          </div>
          <pre v-if="packetMarkdown" class="max-h-80 overflow-auto rounded bg-black/30 p-2 text-[11px] whitespace-pre-wrap">{{ packetMarkdown }}</pre>
          <details v-if="packetJson" class="mt-2 text-xs">
            <summary class="cursor-pointer text-muted-foreground">JSON snapshot</summary>
            <pre class="mt-2 max-h-60 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ packetJson }}</pre>
          </details>
          <div v-if="packetPaths" class="mt-2 text-[11px] text-muted-foreground">
            Saved JSON: {{ packetPaths.json_path }}<br />
            Saved Markdown: {{ packetPaths.markdown_path }}
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
