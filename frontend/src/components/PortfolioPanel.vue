<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  createPortfolioAnalysisPacket,
  getPortfolio,
  getPortfolioSemanticSuggestions,
  getPortfolioSnapshot,
  getStockQuote,
  savePortfolio,
  searchStocks,
  type HoldingSemanticSuggestion,
  type PortfolioPosition,
  type PortfolioState,
  type StockQuoteInfo,
  type StockSearchItem,
} from '../api/client'

type ManualRow = {
  row_id: string
  symbol: string
  name: string
  query: string
  quantity: number | null
  available_quantity: number | null
  avg_cost: number | null
  position_role: string
  primary_theme: string
  theme_tags: string[]
  directions: string[]
  risk_flags: string[]
  user_plan: string
  invalid_condition: string
  target_max_weight: number | null
  semantic_classification_status: string
  semantic_classification_source: string
  quote: StockQuoteInfo | null
  quoteLoading: boolean
}

const supportedDirections = ['COPPER', 'GOLD', 'PCB', 'AI', 'SEMICONDUCTOR_EQUIPMENT', 'TUNGSTEN', 'OTHER', 'UNCLASSIFIED']
const positionRoles = ['core', 'trend', 'defensive', 'short_term', 'observation', 'unclassified']

const expanded = ref(false)
const loading = ref(false)
const saving = ref(false)
const state = ref<PortfolioState | null>(null)
const manualRows = ref<ManualRow[]>([])
const suggestions = ref<Record<string, HoldingSemanticSuggestion>>({})
const activeRowId = ref('')
const rowMatches = ref<StockSearchItem[]>([])
const searchLoading = ref(false)
const saveError = ref('')
const saveNotice = ref('')
let searchTimer: number | undefined

const snapshotPreview = ref('')
const snapshotNotice = ref('')
const packetMarkdown = ref('')
const packetJson = ref('')
const packetCopied = ref(false)
const packetLoading = ref(false)
const contextDirtyPrompt = ref(false)
const savedDraftFingerprint = ref('')

const editingTagsRowId = ref('')
const tagDrafts = ref<Record<string, string>>({})

const accountDraft = ref({
  cash_available: 0,
  account_actual_total_cost: null as number | null,
  repo_amount: 0,
  max_position_weight: 35,
  max_theme_weight: 50,
  min_cash_ratio: 5,
})

const fmt = (v?: number | null, suffix = '') => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const signedFmt = (v?: number | null, suffix = '') => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  const value = Number(v)
  return `${value > 0 ? '+' : ''}${fmt(value, suffix)}`
}

const rowKey = () => `manual_${Date.now()}_${Math.random().toString(16).slice(2)}`
const compactSymbol = (symbol: string) => symbol.split('.', 1)[0].padStart(6, '0')
const roleLabelMap: Record<string, string> = {
  core: '核心',
  trend: '趋势',
  defensive: '防御',
  short_term: '短线',
  observation: '观察',
  unclassified: '待分类',
}
const roleLabel = (key: string) => roleLabelMap[key] || key

const themeLabelMap: Record<string, string> = {
  AI: 'AI',
  GOLD: '黄金',
  COPPER: '铜',
  TUNGSTEN: '钨',
  PCB: 'PCB',
  SEMICONDUCTOR_EQUIPMENT: '半导体设备',
  OTHER: '其他',
  UNCLASSIFIED: '待分类',
  HIGH_VOLATILITY: '高波动',
}
const themeLabel = (key: string) => themeLabelMap[key] || key
const normalizeTag = (value: string) => value.trim().replace(/\s+/g, '_').toUpperCase()
const selectableDirectionsForRow = (row: ManualRow) =>
  Array.from(new Set([...supportedDirections, ...row.directions])).filter((d) => !row.directions.includes(d))

const canonicalNames: Record<string, string> = {
  '601899': '紫金矿业',
  '603993': '洛阳钼业',
  '002463': '沪电股份',
  '002916': '深南电路',
  '159382': '创业板人工智能 ETF',
  '159934': '黄金 ETF',
  '159516': '半导体设备 ETF',
  '000657': '中钨高新',
}

const marketBadge = (symbol: string) => {
  const code = symbol.split('.')[0]
  if (code.startsWith('6')) return '沪'
  if (code.startsWith('0') || code.startsWith('1') || code.startsWith('3')) return '深'
  return ''
}

const rowShortName = (row: ManualRow) => {
  const code = compactSymbol(row.symbol)
  const name = canonicalNames[code] || row.name || ''
  return name.replace(/^(XD|XR|DR)/i, '')
}

const quotePrice = (row: ManualRow) => row.quote?.price ?? null
const suggestionFor = (row: ManualRow) => suggestions.value[compactSymbol(row.symbol)]
const rowQuantity = (row: ManualRow) => Number(row.quantity || 0)
const rowAvgCost = (row: ManualRow) => Number(row.avg_cost || 0)
const rowMarketValue = (row: ManualRow) => {
  const price = quotePrice(row)
  return price === null ? 0 : rowQuantity(row) * price
}
const rowCostValue = (row: ManualRow) => rowQuantity(row) * rowAvgCost(row)
const totalMarketValue = computed(() => manualRows.value.reduce((sum, row) => sum + rowMarketValue(row), 0))
const totalCostValue = computed(() => manualRows.value.reduce((sum, row) => sum + rowCostValue(row), 0))
const currentHoldingPnl = computed(() => totalMarketValue.value - totalCostValue.value)
const currentHoldingPnlPct = computed(() => totalCostValue.value ? (currentHoldingPnl.value / totalCostValue.value) * 100 : null)
const computedTotalAssets = computed(() =>
  totalMarketValue.value + Number(accountDraft.value.cash_available || 0) + Number(accountDraft.value.repo_amount || 0),
)
const accountActualTotalCost = computed(() => {
  const value = Number(accountDraft.value.account_actual_total_cost || 0)
  return value > 0 ? value : null
})
const accountTotalPnl = computed(() => accountActualTotalCost.value ? computedTotalAssets.value - accountActualTotalCost.value : null)
const accountTotalPnlPct = computed(() => accountActualTotalCost.value && accountTotalPnl.value !== null ? accountTotalPnl.value / accountActualTotalCost.value * 100 : null)
const cashRatio = computed(() => computedTotalAssets.value ? Number(accountDraft.value.cash_available || 0) / computedTotalAssets.value * 100 : 0)
const investedRatio = computed(() => computedTotalAssets.value ? totalMarketValue.value / computedTotalAssets.value * 100 : 0)
const validRows = computed(() => manualRows.value.filter((row) => row.symbol && rowQuantity(row) > 0 && rowAvgCost(row) > 0))
const draftFingerprint = computed(() => JSON.stringify({
  cash_available: Number(accountDraft.value.cash_available || 0),
  account_actual_total_cost: accountActualTotalCost.value,
  repo_amount: Number(accountDraft.value.repo_amount || 0),
  risk_limits: {
    max_position_weight: Number(accountDraft.value.max_position_weight || 35),
    max_theme_weight: Number(accountDraft.value.max_theme_weight || 50),
    min_cash_ratio: Number(accountDraft.value.min_cash_ratio || 5),
  },
  positions: validRows.value.map((row) => ({
    symbol: compactSymbol(row.symbol),
    name: rowShortName(row),
    quantity: Number(row.quantity || 0),
    available_quantity: row.available_quantity ?? null,
    avg_cost: Number(row.avg_cost || 0),
    directions: row.directions,
    risk_flags: row.risk_flags,
    position_role: row.position_role || 'observation',
    user_plan: row.user_plan || '',
    invalid_condition: row.invalid_condition || null,
    target_max_weight: row.target_max_weight ?? null,
  })),
}))
const isDirty = computed(() => Boolean(savedDraftFingerprint.value) && draftFingerprint.value !== savedDraftFingerprint.value)

const riskObservationSummary = computed(() => {
  const highVolRows = manualRows.value.filter((row) => row.risk_flags.includes('HIGH_VOLATILITY'))
  if (!highVolRows.length) return ''
  const names = highVolRows.map((row) => rowShortName(row) || compactSymbol(row.symbol)).join('、')
  return `风险观察：高波动关联持仓包括 ${names}。`
})

const newRow = (position?: PortfolioPosition): ManualRow => ({
  row_id: rowKey(),
  symbol: position?.symbol || '',
  name: position?.symbol ? (canonicalNames[compactSymbol(position.symbol)] || position?.name || '') : '',
  query: position?.symbol ? `${compactSymbol(position.symbol)} ${canonicalNames[compactSymbol(position.symbol)] || position.name || ''}`.trim() : '',
  quantity: position?.quantity ?? null,
  available_quantity: position?.available_quantity ?? position?.quantity ?? null,
  avg_cost: position?.avg_cost ?? null,
  position_role: position?.position_role || 'observation',
  primary_theme: position?.primary_theme || '',
  theme_tags: [...(position?.theme_tags || [])],
  directions: [...(position?.directions || [])],
  risk_flags: [...(position?.risk_flags || [])],
  user_plan: position?.user_plan || '',
  invalid_condition: position?.invalid_condition || '',
  target_max_weight: position?.target_max_weight ?? null,
  semantic_classification_status: position?.semantic_classification_status || 'unconfirmed',
  semantic_classification_source: position?.semantic_classification_source || '',
  quote: position
    ? {
        symbol: position.symbol,
        name: position.name,
        price: position.system_quote_price ?? position.market_price ?? null,
        change_pct: null,
        quote_status: position.quote_time_status || 'saved',
      }
    : null,
  quoteLoading: false,
})

const loadSuggestions = async () => {
  const items = await getPortfolioSemanticSuggestions()
  suggestions.value = Object.fromEntries(items.map((item) => [compactSymbol(item.symbol), item]))
}

const applySuggestionToRow = (row: ManualRow) => {
  const suggestion = suggestionFor(row)
  if (!suggestion) return
  if (!row.directions.length) {
    row.directions = [...(suggestion.suggested_directions || [])]
  }
  if (!row.risk_flags.length) {
    row.risk_flags = [...(suggestion.suggested_risk_flags || [])]
  }
  if (!row.position_role) {
    row.position_role = suggestion.suggested_position_role || 'observation'
  }
}

const load = async () => {
  loading.value = true
  try {
    state.value = await getPortfolio()
    await loadSuggestions()
    accountDraft.value.cash_available = state.value.snapshot.cash_available
    accountDraft.value.account_actual_total_cost = state.value.snapshot.account_actual_total_cost ?? null
    accountDraft.value.repo_amount = state.value.snapshot.repo_amount
    accountDraft.value.max_position_weight = state.value.snapshot.risk_limits.max_position_weight
    accountDraft.value.max_theme_weight = state.value.snapshot.risk_limits.max_theme_weight
    accountDraft.value.min_cash_ratio = state.value.snapshot.risk_limits.min_cash_ratio
    manualRows.value = state.value.snapshot.positions.length ? state.value.snapshot.positions.map(newRow) : [newRow()]
    manualRows.value.forEach((row) => {
      if (!row.symbol) return
      applySuggestionToRow(row)
    })
    await Promise.all(manualRows.value.filter((row) => row.symbol).map(loadQuoteForRow))
    savedDraftFingerprint.value = draftFingerprint.value
    contextDirtyPrompt.value = false
  } finally {
    loading.value = false
  }
}

const scheduleSearch = (row: ManualRow) => {
  activeRowId.value = row.row_id
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(async () => {
    const term = row.query.trim()
    if (!term) {
      rowMatches.value = []
      return
    }
    searchLoading.value = true
    try {
      rowMatches.value = await searchStocks(term, 8)
    } finally {
      searchLoading.value = false
    }
  }, 160)
}

const loadQuoteForRow = async (row: ManualRow) => {
  if (!row.symbol) return
  row.quoteLoading = true
  try {
    row.quote = await getStockQuote(row.symbol)
    row.name = canonicalNames[compactSymbol(row.symbol)] || row.quote.name || row.name
    row.query = `${compactSymbol(row.symbol)} ${rowShortName(row)}`.trim()
  } finally {
    row.quoteLoading = false
  }
}

const chooseMatch = async (row: ManualRow, match: StockSearchItem) => {
  row.symbol = match.symbol
  row.name = canonicalNames[compactSymbol(match.symbol)] || match.name
  row.query = `${compactSymbol(match.symbol)} ${row.name}`
  rowMatches.value = []
  activeRowId.value = ''
  await loadQuoteForRow(row)
  await loadSuggestions()
  applySuggestionToRow(row)
}

const addRow = () => {
  manualRows.value.push(newRow())
}

const removeRow = (rowId: string) => {
  manualRows.value = manualRows.value.filter((row) => row.row_id !== rowId)
  if (!manualRows.value.length) addRow()
}

const toggleDirection = (row: ManualRow, tag: string) => {
  row.directions = row.directions.includes(tag)
    ? row.directions.filter((item) => item !== tag)
    : [...row.directions, tag]
}

const moveDirection = (row: ManualRow, index: number, delta: number) => {
  const newIndex = index + delta
  if (newIndex < 0 || newIndex >= row.directions.length) return
  const arr = [...row.directions]
  ;[arr[index], arr[newIndex]] = [arr[newIndex], arr[index]]
  row.directions = arr
}

const removeDirection = (row: ManualRow, tag: string) => {
  row.directions = row.directions.filter((t) => t !== tag)
}

const addCustomDirection = (row: ManualRow) => {
  const tag = normalizeTag(tagDrafts.value[row.row_id] || '')
  if (!tag) return
  if (!row.directions.includes(tag)) {
    row.directions = [...row.directions, tag]
  }
  tagDrafts.value[row.row_id] = ''
}

const toggleRiskFlag = (row: ManualRow, flag: string) => {
  row.risk_flags = row.risk_flags.includes(flag)
    ? row.risk_flags.filter((f) => f !== flag)
    : [...row.risk_flags, flag]
}

const toggleTagEdit = (rowId: string) => {
  editingTagsRowId.value = editingTagsRowId.value === rowId ? '' : rowId
}

const saveManualPortfolio = async () => {
  saveError.value = ''
  saveNotice.value = ''
  saving.value = true
  try {
    state.value = await savePortfolio({
      portfolio_id: state.value?.snapshot.portfolio_id || 'local_default',
      snapshot_time: new Date().toISOString(),
      total_assets: computedTotalAssets.value,
      cash_available: Number(accountDraft.value.cash_available || 0),
      account_actual_total_cost: accountActualTotalCost.value,
      repo_amount: Number(accountDraft.value.repo_amount || 0),
      source_type: 'manual_account',
      source_name: 'user_manual_entry',
      risk_limits: {
        max_position_weight: Number(accountDraft.value.max_position_weight || 35),
        max_theme_weight: Number(accountDraft.value.max_theme_weight || 50),
        min_cash_ratio: Number(accountDraft.value.min_cash_ratio || 5),
      },
      positions: validRows.value.map((row) => ({
        symbol: compactSymbol(row.symbol),
        name: rowShortName(row),
        quantity: Number(row.quantity || 0),
        available_quantity: row.available_quantity ?? null,
        avg_cost: Number(row.avg_cost || 0),
        source_type: 'manual_account',
        source_name: 'user_manual_entry',
        confirmed_by_user: true,
        position_role: row.position_role || 'observation',
        theme_tags: [...row.directions, ...row.risk_flags],
        primary_theme: row.directions[0] || null,
        directions: row.directions,
        risk_flags: row.risk_flags,
        semantic_classification_status: row.directions.length ? 'user_confirmed' : 'unconfirmed',
        semantic_classification_source: row.directions.length ? 'manual_confirmed_from_system_suggestion' : null,
        semantic_classification_confirmed_at: row.directions.length ? new Date().toISOString() : null,
        user_plan: row.user_plan || '',
        invalid_condition: row.invalid_condition || null,
        target_max_weight: row.target_max_weight ?? null,
      })),
    })
    await loadSuggestions()
    manualRows.value = state.value.snapshot.positions.length ? state.value.snapshot.positions.map(newRow) : [newRow()]
    manualRows.value.forEach((row) => {
      if (!row.directions.length && row.symbol) {
        applySuggestionToRow(row)
      }
    })
    await Promise.all(manualRows.value.filter((row) => row.symbol).map(loadQuoteForRow))
    savedDraftFingerprint.value = draftFingerprint.value
    contextDirtyPrompt.value = false
    saveNotice.value = '已保存为正式本地组合快照。'
  } catch (error: any) {
    saveError.value = error?.response?.data?.detail || error?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

const buildSnapshot = async () => {
  const snap = await getPortfolioSnapshot()
  snapshotNotice.value = '摘要只读取已保存的正式 portfolio snapshot；未保存的手动编辑不会进入证据包。'
  snapshotPreview.value = JSON.stringify({
    snapshot_id: snap.snapshot_id,
    analysis_scope: snap.analysis_scope,
    evidence_count: snap.evidence_items?.length,
    target_symbols: snap.target_symbols,
    missing_data: snap.missing_data,
  }, null, 2)
}

const generatePortfolioPacket = async (staleDraft = false) => {
  packetLoading.value = true
  packetCopied.value = false
  try {
    const result = await createPortfolioAnalysisPacket('', { staleDraft })
    packetMarkdown.value = result.markdown
    packetJson.value = JSON.stringify(result.packet, null, 2)
    contextDirtyPrompt.value = false
  } finally {
    packetLoading.value = false
  }
}

const buildPortfolioPacket = async () => {
  if (isDirty.value) {
    contextDirtyPrompt.value = true
    return
  }
  await generatePortfolioPacket(false)
}

const generateSavedSnapshotPacket = async () => {
  await generatePortfolioPacket(true)
}

const saveAndGeneratePacket = async () => {
  await saveManualPortfolio()
  if (!saveError.value) {
    await generatePortfolioPacket(false)
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
  <section class="mb-4 overflow-hidden rounded-lg border border-border bg-card">
    <button class="flex w-full items-center justify-between px-4 py-3 text-left" @click="expanded = !expanded">
      <div>
        <h2 class="text-sm font-semibold text-foreground">组合与手动账户快照</h2>
        <p class="text-[11px] text-muted-foreground">手动维护持仓、确认主题归属与持仓角色；保存后进入 Portfolio Packet 和未来账户级 AI 输入。</p>
      </div>
      <span class="text-xs text-muted-foreground">{{ expanded ? '收起' : '展开' }}</span>
    </button>

    <div v-if="expanded" class="space-y-4 border-t border-border p-4">
      <div v-if="loading" class="text-xs text-muted-foreground">加载组合...</div>

      <template v-else>
        <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
          <div class="rounded bg-secondary/40 p-3" :title="`当前持仓浮动盈亏：${signedFmt(currentHoldingPnl)} ${signedFmt(currentHoldingPnlPct, '%')}`">
            <div class="text-muted-foreground">当前估算总资产</div>
            <div class="font-mono text-base font-semibold">{{ fmt(computedTotalAssets) }}</div>
          </div>
          <div class="rounded bg-secondary/40 p-3">
            <div class="text-muted-foreground">当前行情持仓市值</div>
            <div class="font-mono text-base font-semibold">{{ fmt(totalMarketValue) }}</div>
          </div>
          <div class="rounded bg-secondary/40 p-3">
            <div class="text-muted-foreground">账户总盈亏</div>
            <div v-if="accountTotalPnl !== null" :class="['font-mono text-base font-semibold', accountTotalPnl >= 0 ? 'text-negative' : 'text-positive']">
              {{ signedFmt(accountTotalPnl) }} <span class="text-xs">{{ signedFmt(accountTotalPnlPct, '%') }}</span>
            </div>
            <div v-else class="text-xs font-medium text-muted-foreground">
              待录入实际总成本
            </div>
          </div>
          <div class="rounded bg-secondary/40 p-3">
            <div class="text-muted-foreground">可用现金</div>
            <div class="font-mono text-base font-semibold">{{ fmt(accountDraft.cash_available) }} <span class="text-xs">{{ fmt(cashRatio, '%') }}</span></div>
          </div>
          <div class="rounded bg-secondary/40 p-3">
            <div class="text-muted-foreground">仓位</div>
            <div class="font-mono text-base font-semibold">{{ fmt(investedRatio, '%') }}</div>
          </div>
        </div>

        <div class="rounded border border-border/60 bg-secondary/20 p-2 text-xs text-muted-foreground">
          当前估算总资产基于系统最新取价与已保存现金计算；账户总盈亏基于手动维护的账户实际总成本计算，均不等同于券商实时官方口径。
        </div>

        <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
          <label class="space-y-1">
            <span class="text-muted-foreground">可用现金</span>
            <input v-model.number="accountDraft.cash_available" class="h-9 w-full rounded bg-input px-2" type="number" />
          </label>
          <label class="space-y-1">
            <span class="text-muted-foreground">账户实际总成本</span>
            <input v-model.number="accountDraft.account_actual_total_cost" class="h-9 w-full rounded bg-input px-2" min="0" step="0.01" type="number" />
          </label>
          <div class="flex items-end md:col-start-3">
            <button class="h-9 w-full rounded bg-primary px-3 text-xs font-medium" :disabled="saving" @click="saveManualPortfolio">
              {{ saving ? '保存中...' : '保存组合快照' }}
            </button>
          </div>
        </div>
        <div v-if="isDirty" class="rounded border border-warning/50 bg-warning/10 p-2 text-xs text-warning">
          存在未保存修改；账户上下文将基于最近一次已保存快照生成。
        </div>
        <div v-else-if="savedDraftFingerprint" class="text-xs text-muted-foreground">
          已保存
        </div>

        <div class="overflow-x-auto rounded border border-border/60">
          <table class="w-full min-w-[1050px] table-fixed text-xs">
            <colgroup>
              <col class="w-[220px]" />
              <col class="w-[90px]" />
              <col class="w-[90px]" />
              <col class="w-[90px]" />
              <col class="w-[120px]" />
              <col class="w-[110px]" />
              <col class="w-[100px]" />
              <col class="w-[280px]" />
              <col class="w-[100px]" />
              <col class="w-[56px]" />
            </colgroup>
            <thead class="bg-secondary/40 text-muted-foreground">
              <tr>
                <th class="px-2 py-2 text-left">标的</th>
                <th class="px-2 py-2 text-right">持仓</th>
                <th class="px-2 py-2 text-right">可用</th>
                <th class="px-2 py-2 text-right">成本</th>
                <th class="px-2 py-2 text-right">现价 / 涨跌</th>
                <th class="px-2 py-2 text-right">市值</th>
                <th class="px-2 py-2 text-right">账户权重</th>
                <th class="px-2 py-2">关联方向</th>
                <th class="px-2 py-2">角色</th>
                <th class="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in manualRows" :key="row.row_id" class="border-t border-border/50 align-top">
                <td class="relative p-2">
                  <div class="rounded bg-input focus-within:ring-2 focus-within:ring-warning/70">
                    <input
                      v-model="row.query"
                      class="h-9 w-full rounded bg-transparent px-2 font-mono outline-none"
                      placeholder="输入代码或名称"
                      @focus="scheduleSearch(row)"
                      @input="scheduleSearch(row)"
                    />
                    <div v-if="row.symbol" class="-mt-1 flex items-center gap-1 truncate px-2 pb-1 text-[11px]">
                      <span v-if="marketBadge(row.symbol)" class="rounded bg-secondary px-1 text-muted-foreground">{{ marketBadge(row.symbol) }}</span>
                    </div>
                  </div>
                  <div v-if="activeRowId === row.row_id && rowMatches.length" class="absolute left-2 right-2 top-12 z-30 overflow-hidden rounded border border-border bg-card shadow-xl">
                    <button
                      v-for="match in rowMatches"
                      :key="match.symbol"
                      class="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-secondary/50"
                      @mousedown.prevent="chooseMatch(row, match)"
                    >
                      <span><span class="font-mono text-foreground">{{ match.symbol }}</span> <span class="text-muted-foreground">{{ match.name }}</span></span>
                      <span class="text-[11px] text-muted-foreground">{{ match.asset_type === 'etf' ? 'ETF' : (match.industry || match.area || '本地库') }}</span>
                    </button>
                  </div>
                  <div v-if="row.quoteLoading || searchLoading" class="mt-1 text-[11px] text-muted-foreground">查询中...</div>
                </td>
                <td class="p-2"><input v-model.number="row.quantity" class="h-9 w-full rounded bg-input px-2 text-right font-mono" type="number" /></td>
                <td class="p-2"><input v-model.number="row.available_quantity" class="h-9 w-full rounded bg-input px-2 text-right font-mono" type="number" /></td>
                <td class="p-2"><input v-model.number="row.avg_cost" class="h-9 w-full rounded bg-input px-2 text-right font-mono" type="number" /></td>
                <td class="p-2 text-right font-mono">
                  <div>{{ fmt(row.quote?.price) }}</div>
                  <div :class="['text-[11px]', Number(row.quote?.change_pct || 0) >= 0 ? 'text-negative' : 'text-positive']">
                    {{ signedFmt(row.quote?.change_pct, '%') }}
                  </div>
                </td>
                <td class="p-2 text-right font-mono">{{ fmt(rowMarketValue(row)) }}</td>
                <td class="p-2 text-right font-mono">{{ fmt(computedTotalAssets ? rowMarketValue(row) / computedTotalAssets * 100 : 0, '%') }}</td>
                <td class="p-2">
                  <div class="flex flex-wrap items-center gap-1">
                    <span
                      v-for="(tag, idx) in row.directions"
                      :key="tag"
                      :class="['rounded border px-2 py-1 text-[11px]', idx === 0 ? 'border-primary bg-primary/20 font-semibold text-foreground' : 'border-border/80 bg-secondary/30 text-muted-foreground']"
                    >
                      {{ themeLabel(tag) }}
                    </span>
                    <button
                      class="rounded border border-border px-2 py-1 text-[11px] text-muted-foreground"
                      @click="toggleTagEdit(row.row_id)"
                    >
                      {{ editingTagsRowId === row.row_id ? '完成' : (row.directions.length ? '编辑' : '+ 方向') }}
                    </button>
                  </div>
                  <div v-if="editingTagsRowId === row.row_id" class="mt-2 space-y-2 rounded border border-border/60 bg-secondary/20 p-2">
                    <div class="text-[11px] text-muted-foreground">第一个方向用于主要归组统计</div>
                    <div class="flex flex-wrap gap-1">
                      <div
                        v-for="(tag, idx) in row.directions"
                        :key="tag"
                        class="flex items-center gap-1 rounded border border-primary bg-primary/20 px-2 py-1 text-[11px] text-foreground"
                      >
                        <span>{{ themeLabel(tag) }}</span>
                        <button
                          type="button"
                          class="text-[10px] text-muted-foreground hover:text-foreground"
                          :disabled="idx === 0"
                          @click="moveDirection(row, idx, -1)"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          class="text-[10px] text-muted-foreground hover:text-foreground"
                          :disabled="idx === row.directions.length - 1"
                          @click="moveDirection(row, idx, 1)"
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          class="text-[10px] text-negative hover:text-negative"
                          @click="removeDirection(row, tag)"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                    <div class="flex flex-wrap gap-1">
                      <button
                        v-for="tag in selectableDirectionsForRow(row)"
                        :key="tag"
                        type="button"
                        class="rounded border px-2 py-1 text-[11px] border-border text-muted-foreground hover:border-primary hover:bg-primary/10"
                        @click="toggleDirection(row, tag)"
                      >
                        + {{ themeLabel(tag) }}
                      </button>
                    </div>
                    <div class="flex min-w-[180px] flex-1 gap-1">
                      <input
                        v-model="tagDrafts[row.row_id]"
                        class="h-7 min-w-0 flex-1 rounded bg-input px-2 text-[11px]"
                        placeholder="NEW_TAG"
                        @keydown.enter.prevent="addCustomDirection(row)"
                      />
                      <button
                        type="button"
                        class="rounded border border-primary px-2 py-1 text-[11px] text-foreground"
                        @click="addCustomDirection(row)"
                      >
                        Add
                      </button>
                    </div>
                    <div class="flex items-center gap-2 pt-1">
                      <label class="flex items-center gap-1 text-[11px] text-muted-foreground">
                        <input
                          type="checkbox"
                          :checked="row.risk_flags.includes('HIGH_VOLATILITY')"
                          @change="toggleRiskFlag(row, 'HIGH_VOLATILITY')"
                        />
                        <span>高波动</span>
                      </label>
                    </div>
                  </div>
                </td>
                <td class="p-2">
                  <select v-model="row.position_role" class="h-9 w-full rounded bg-input px-2">
                    <option v-for="role in positionRoles" :key="role" :value="role">{{ roleLabel(role) }}</option>
                  </select>
                </td>
                <td class="p-2 text-right"><button class="text-negative" @click="removeRow(row.row_id)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs">
          <button class="rounded bg-secondary px-3 py-2" @click="addRow">新增一行</button>
          <span v-if="saveNotice" class="text-positive">{{ saveNotice }}</span>
          <span v-if="saveError" class="text-negative">{{ saveError }}</span>
        </div>

        <div v-if="riskObservationSummary" class="rounded border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
          {{ riskObservationSummary }}
        </div>

        <div class="rounded border border-border/60 p-2">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="text-xs font-semibold">Portfolio Analysis Snapshot</h3>
            <button class="rounded bg-secondary px-3 py-1 text-xs" @click="buildSnapshot">生成 JSON 摘要</button>
          </div>
          <div v-if="snapshotNotice" class="mb-2 rounded border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
            {{ snapshotNotice }}
          </div>
          <pre v-if="snapshotPreview" class="max-h-40 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ snapshotPreview }}</pre>
        </div>

        <div class="rounded border border-border/60 p-2">
          <div class="mb-2 flex items-center justify-between">
            <div>
              <h3 class="text-xs font-semibold">组合证据包 / Portfolio Analysis Packet v1</h3>
              <p class="text-[11px] text-muted-foreground">汇总当前账户持仓、主题结构、外部驱动与组合上下文，供账户级复盘使用。</p>
            </div>
            <div class="flex gap-2">
              <button class="rounded bg-secondary px-3 py-1 text-xs" :disabled="!packetMarkdown" @click="copyPortfolioPacket">{{ packetCopied ? 'Copied' : 'Copy Markdown' }}</button>
              <button class="rounded bg-primary px-3 py-1 text-xs" :disabled="packetLoading" @click="buildPortfolioPacket">
                {{ packetLoading ? 'Generating...' : '生成组合证据包 / Generate Portfolio Packet' }}
              </button>
            </div>
          </div>
          <div v-if="contextDirtyPrompt" class="mb-2 rounded border border-warning/50 bg-warning/10 p-2 text-xs text-warning">
            <div class="mb-2">当前存在未保存修改。账户上下文默认基于最近一次已保存快照生成。</div>
            <div class="flex flex-wrap gap-2">
              <button class="rounded bg-secondary px-3 py-1" @click="contextDirtyPrompt = false">取消</button>
              <button class="rounded bg-secondary px-3 py-1" :disabled="packetLoading" @click="generateSavedSnapshotPacket">仍按已保存快照生成</button>
              <button class="rounded bg-primary px-3 py-1" :disabled="saving || packetLoading" @click="saveAndGeneratePacket">先保存并生成</button>
            </div>
          </div>
          <pre v-if="packetMarkdown" class="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 text-[11px]">{{ packetMarkdown }}</pre>
          <details v-if="packetJson" class="mt-2 text-xs">
            <summary class="cursor-pointer text-muted-foreground">JSON snapshot</summary>
            <pre class="mt-2 max-h-60 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ packetJson }}</pre>
          </details>
        </div>
      </template>
    </div>
  </section>
</template>
