<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  createPortfolioAnalysisPacket,
  confirmPortfolioImportDraft,
  getPortfolio,
  getPortfolioImportParserProviders,
  getPortfolioSemanticSuggestions,
  getPortfolioSnapshot,
  getStockQuote,
  rejectPortfolioImportDraft,
  savePortfolio,
  searchStocks,
  suggestPortfolioTradeReason,
  updatePortfolioImportDraft,
  uploadPortfolioScreenshot,
  type HoldingSemanticSuggestion,
  type PortfolioPosition,
  type PortfolioImportDraft,
  type PortfolioParserProviderStatus,
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
  asset_type: string
  ipo_status: string
  issue_price: number | null
  expected_list_date: string
  semantic_classification_status: string
  semantic_classification_source: string
  quote: StockQuoteInfo | null
  quoteLoading: boolean
}

const supportedDirections = ['COPPER', 'GOLD', 'PCB', 'AI', 'SEMICONDUCTOR_EQUIPMENT', 'DISPLAY_PANEL', 'GREEN_POWER', 'TUNGSTEN', 'OTHER', 'UNCLASSIFIED']
const positionRoles = ['core', 'trend', 'defensive', 'short_term', 'observation', 'unclassified']

const expanded = ref(false)
const emit = defineEmits<{ (event: 'account-saved'): void; (event: 'close'): void }>()
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
const importFileInput = ref<HTMLInputElement | null>(null)
const importSection = ref<HTMLElement | null>(null)
const importFile = ref<File | null>(null)
const importKind = ref<'current_holdings' | 'trade_history'>('current_holdings')
const importDropActive = ref(false)
const tradeApplyMode = ref<'record_only' | 'apply'>('record_only')
const tradeDecisionReason = ref('')
const tradeReasonQuestions = ref<string[]>([])
const tradeReasonLoading = ref(false)
const importProviderStatus = ref<PortfolioParserProviderStatus | null>(null)
const importDraft = ref<PortfolioImportDraft | null>(null)
const importConsent = ref(false)
const importLoading = ref(false)
const importConfirming = ref(false)
const importError = ref('')
const importNotice = ref('')
let searchTimer: number | undefined

const snapshotPreview = ref('')
const snapshotNotice = ref('')
const packetMarkdown = ref('')
const packetJson = ref('')
const packetCopied = ref(false)
const packetLoading = ref(false)
const contextDirtyPrompt = ref(false)
const savedDraftFingerprint = ref('')
const marketValueSort = ref<'desc' | 'asc'>('desc')
const rowSortOrder = ref<string[]>([])

const editingTagsRowId = ref('')
const tagDrafts = ref<Record<string, string>>({})
const editingDirectionCatalog = ref(false)
const directionCatalogDraft = ref('')
const customDirectionCatalog = ref<string[]>([])
const hiddenDirectionCatalog = ref<string[]>([])

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

const props = defineProps<{
  openImportKind?: 'current_holdings' | 'trade_history' | null
  openImportRequest?: number
}>()

const visionProvider = computed(() =>
  importProviderStatus.value?.providers.find((item) => item.provider === 'volcengine_ark_vision'),
)
const visionAvailable = computed(() => visionProvider.value?.status === 'configured_not_verified')
const importRows = computed(() => importDraft.value?.holding_rows_draft || [])
const importTransactionRows = computed(() => importDraft.value?.transaction_rows_draft || [])
const importRowCount = computed(() => (
  importDraft.value?.screenshot_kind === 'trade_history'
    ? importTransactionRows.value.length
    : importRows.value.length
))
const importAction = (row: Record<string, any>) => {
  const symbol = compactSymbol(String(row.normalized_symbol || row.raw_symbol_text || ''))
  const previous = state.value?.snapshot.positions.find((item) => compactSymbol(item.symbol) === symbol)
  const before = Number(previous?.quantity || 0)
  const after = Number(row.quantity || 0)
  if (!previous && after > 0) return { label: '新建仓', before, after }
  if (previous && after === 0) return { label: '清仓', before, after }
  if (after > before) return { label: '加仓', before, after }
  if (after < before) return { label: '减仓', before, after }
  return { label: '数量不变', before, after }
}

const signedFmt = (v?: number | null, suffix = '') => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  const value = Number(v)
  return `${value > 0 ? '+' : ''}${fmt(value, suffix)}`
}

const rowKey = () => `manual_${Date.now()}_${Math.random().toString(16).slice(2)}`
const compactSymbol = (symbol: string) => {
  const raw = (symbol || '').split('.', 1)[0].trim().toUpperCase()
  const digits = raw.replace(/\D/g, '')
  return digits ? digits.slice(0, 6).padStart(6, '0') : raw
}
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
  CXO: 'CXO',
  INNOVATION_DRUG: '创新药',
  MEDICAL_ETF: '医药ETF',
  INSURANCE: '保险',
  MOLYBDENUM: '钼',
  EV_AUTOMOTIVE: '新能源车 / 整车',
  METAL_RESOURCE: '金属资源',
  OTHER: '其他',
  UNCLASSIFIED: '待分类',
  HIGH_VOLATILITY: '高波动',
}
Object.assign(themeLabelMap, {
  DISPLAY_PANEL: '显示面板',
  GREEN_POWER: '绿电',
})
const themeLabel = (key: string) => themeLabelMap[key] || key
const normalizeTag = (value: string) => value.trim().replace(/\s+/g, '_').toUpperCase()
const rowDirectionTags = computed(() =>
  manualRows.value.flatMap((row) => row.directions),
)
const allDirectionOptions = computed(() => {
  const hidden = new Set(hiddenDirectionCatalog.value)
  return Array.from(new Set([
    ...supportedDirections,
    ...(state.value?.supported_directions || []),
    ...customDirectionCatalog.value,
    ...rowDirectionTags.value,
  ])).filter((tag) => tag && !hidden.has(tag))
})
const selectableDirectionsForRow = (row: ManualRow) =>
  allDirectionOptions.value.filter((d) => !row.directions.includes(d))

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

const marketBadge = (row: ManualRow) => {
  if (row.asset_type === 'ipo_subscription') return 'IPO'
  const code = row.symbol.split('.')[0]
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
const displayPrice = (row: ManualRow) => quotePrice(row) ?? row.issue_price ?? (row.asset_type === 'ipo_subscription' ? rowAvgCost(row) : null)
const suggestionFor = (row: ManualRow) => suggestions.value[compactSymbol(row.symbol)]
const rowQuantity = (row: ManualRow) => Number(row.quantity || 0)
const rowAvgCost = (row: ManualRow) => Number(row.avg_cost || 0)
const rowMarketValue = (row: ManualRow) => {
  const price = displayPrice(row)
  return price === null ? 0 : rowQuantity(row) * price
}
const rowCostValue = (row: ManualRow) => rowQuantity(row) * rowAvgCost(row)
const totalMarketValue = computed(() => manualRows.value.reduce((sum, row) => sum + rowMarketValue(row), 0))
const totalCostValue = computed(() => manualRows.value.reduce((sum, row) => sum + rowCostValue(row), 0))
const currentHoldingPnl = computed(() => totalMarketValue.value - totalCostValue.value)
const currentHoldingPnlPct = computed(() =>
  totalCostValue.value > 0 ? (currentHoldingPnl.value / totalCostValue.value) * 100 : null,
)
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
const validRows = computed(() => manualRows.value.filter((row) => {
  if (!row.symbol) return false
  const quantity = rowQuantity(row)
  const hasCost = row.avg_cost !== null
    && row.avg_cost !== undefined
    && String(row.avg_cost).trim() !== ''
    && Number.isFinite(Number(row.avg_cost))
  return quantity >= 0 && (quantity === 0 || hasCost)
}))
const marketValueSortedIds = () =>
  [...manualRows.value]
    .sort((a, b) => {
      const diff = rowMarketValue(b) - rowMarketValue(a)
      return marketValueSort.value === 'desc' ? diff : -diff
    })
    .map((row) => row.row_id)

const refreshMarketValueOrder = () => {
  rowSortOrder.value = marketValueSortedIds()
}
Object.assign(canonicalNames, {
  '001399': '惠科股份',
  '001248': '华润新能源',
})

const displayedRows = computed(() => {
  if (!rowSortOrder.value.length) return manualRows.value
  const order = new Map(rowSortOrder.value.map((rowId, index) => [rowId, index]))
  return [...manualRows.value].sort((a, b) => {
    const aOrder = order.get(a.row_id) ?? Number.MAX_SAFE_INTEGER
    const bOrder = order.get(b.row_id) ?? Number.MAX_SAFE_INTEGER
    if (aOrder !== bOrder) return aOrder - bOrder
    return manualRows.value.indexOf(a) - manualRows.value.indexOf(b)
  })
})
const toggleMarketValueSort = () => {
  marketValueSort.value = marketValueSort.value === 'desc' ? 'asc' : 'desc'
  refreshMarketValueOrder()
}
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
    avg_cost: Number(row.avg_cost || 0),
    asset_type: row.asset_type || 'stock',
    ipo_status: row.ipo_status || null,
    issue_price: row.issue_price ?? null,
    expected_list_date: row.expected_list_date || null,
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
  asset_type: position?.asset_type || 'stock',
  ipo_status: position?.ipo_status || '',
  issue_price: position?.issue_price ?? null,
  expected_list_date: position?.expected_list_date || '',
  semantic_classification_status: position?.semantic_classification_status || 'unconfirmed',
  semantic_classification_source: position?.semantic_classification_source || '',
  quote: position
    ? {
        symbol: position.symbol,
        name: position.name,
        price: position.system_quote_price ?? position.market_price ?? null,
        change_pct: null,
        asset_type: position.asset_type,
        ipo_status: position.ipo_status,
        issue_price: position.issue_price,
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
    const [nextState, nextProviderStatus] = await Promise.all([
      getPortfolio(),
      getPortfolioImportParserProviders(),
    ])
    state.value = nextState
    importProviderStatus.value = nextProviderStatus
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
    refreshMarketValueOrder()
    savedDraftFingerprint.value = draftFingerprint.value
    contextDirtyPrompt.value = false
  } finally {
    loading.value = false
  }
}

const selectImportFile = () => importFileInput.value?.click()

const resetImportSelection = () => {
  importFile.value = null
  importDraft.value = null
  importConsent.value = false
  importError.value = ''
  importNotice.value = ''
  tradeApplyMode.value = 'record_only'
  tradeDecisionReason.value = ''
  tradeReasonQuestions.value = []
  if (importFileInput.value) importFileInput.value.value = ''
}

const setImportKind = (kind: 'current_holdings' | 'trade_history') => {
  if (importKind.value === kind) return
  importKind.value = kind
  resetImportSelection()
}

const acceptImportFile = (file?: File | null) => {
  if (!file) return false
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    importError.value = '仅支持 PNG、JPEG 或 WebP 图片。'
    return false
  }
  if (file.size > 8 * 1024 * 1024) {
    importError.value = '图片不能超过 8MB。'
    return false
  }
  importFile.value = file
  importDraft.value = null
  importError.value = ''
  importNotice.value = ''
  return true
}

const recognizePortfolioScreenshot = async () => {
  if (!importFile.value || !importConsent.value || importLoading.value) return
  importLoading.value = true
  importError.value = ''
  importNotice.value = `正在上传并识别${importKind.value === 'trade_history' ? '交易行为' : '当前持仓'}截图...`
  try {
    importDraft.value = await uploadPortfolioScreenshot(importFile.value, {
      screenshot_kind: importKind.value,
      parser_provider: 'volcengine_ark_vision',
      cloud_send_consent: true,
      user_notice_acknowledged_at: new Date().toISOString(),
    })
    if (importDraft.value.screenshot_kind === 'trade_history') {
      tradeApplyMode.value = importDraft.value.transaction_apply_recommendation === 'apply' ? 'apply' : 'record_only'
      importNotice.value = `已生成 ${importTransactionRows.value.length} 条待确认成交，尚未写入交易台账。`
    } else {
      importNotice.value = `已生成 ${importRows.value.length} 条待确认持仓，尚未修改正式账户。`
    }
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || error?.message || '识图失败'
  } finally {
    importLoading.value = false
  }
}

const recognizeAcceptedFile = async (accepted: boolean) => {
  if (!accepted || !importFile.value) return
  if (!visionAvailable.value) {
    importError.value = '云端解析当前不可用，请检查模型配置。'
    return
  }
  if (!importConsent.value) {
    importNotice.value = '图片已选择；勾选云端解析同意后，点击“识别为草稿”。'
    return
  }
  await recognizePortfolioScreenshot()
}

const onImportFileSelected = async (event: Event) => {
  const input = event.target as HTMLInputElement
  await recognizeAcceptedFile(acceptImportFile(input.files?.[0]))
}

const onImportDrop = async (event: DragEvent) => {
  importDropActive.value = false
  await recognizeAcceptedFile(acceptImportFile(event.dataTransfer?.files?.[0]))
}

const onImportConsentChanged = async () => {
  if (importConsent.value && importFile.value && !importDraft.value) {
    await recognizePortfolioScreenshot()
  }
}

const confirmImportedPortfolio = async () => {
  if (!importDraft.value) return
  importConfirming.value = true
  importError.value = ''
  try {
    const isTrade = importDraft.value.screenshot_kind === 'trade_history'
    const payload = isTrade
      ? {
          transaction_rows_draft: importDraft.value.transaction_rows_draft.map((row) => ({
            ...row,
            confirmed_by_user: true,
          })),
        }
      : {
          account_summary_draft: importDraft.value.account_summary_draft,
          holding_rows_draft: importDraft.value.holding_rows_draft.map((row) => ({
            ...row,
            confirmed_by_user: true,
          })),
        }
    importDraft.value = await updatePortfolioImportDraft(importDraft.value.draft_id, payload)
    await confirmPortfolioImportDraft(importDraft.value.draft_id, {
      apply_transactions_to_portfolio: isTrade ? tradeApplyMode.value === 'apply' : true,
      user_reason: isTrade ? tradeDecisionReason.value : undefined,
    })
    importNotice.value = isTrade
      ? tradeApplyMode.value === 'apply'
        ? '成交记录已写入交易台账，并已生成更新后的正式持仓快照。'
        : '成交记录已写入交易台账；当前正式持仓未重复调整。'
      : '持仓截图已确认并保存为新的正式组合快照。'
    importDraft.value = null
    importFile.value = null
    importConsent.value = false
    tradeDecisionReason.value = ''
    tradeReasonQuestions.value = []
    if (importFileInput.value) importFileInput.value.value = ''
    await load()
    emit('account-saved')
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || error?.message || '确认保存失败'
  } finally {
    importConfirming.value = false
  }
}

const generateTradeReasonDraft = async () => {
  if (!importDraft.value || importDraft.value.screenshot_kind !== 'trade_history') return
  tradeReasonLoading.value = true
  importError.value = ''
  try {
    const result = await suggestPortfolioTradeReason(importDraft.value.draft_id)
    tradeDecisionReason.value = result.reason_summary
    tradeReasonQuestions.value = result.questions || []
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || error?.message || '交易理由草稿生成失败'
  } finally {
    tradeReasonLoading.value = false
  }
}

const discardImportDraft = async () => {
  if (importDraft.value) {
    try {
      await rejectPortfolioImportDraft(importDraft.value.draft_id)
    } catch {
      // Local UI cleanup remains available even if the draft was already removed.
    }
  }
  resetImportSelection()
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
    row.asset_type = row.quote.asset_type || row.asset_type || 'stock'
    row.ipo_status = row.quote.ipo_status || row.ipo_status || ''
    row.issue_price = row.quote.issue_price ?? row.issue_price
    if (row.asset_type === 'ipo_subscription' && (!row.avg_cost || row.avg_cost <= 0) && row.issue_price) {
      row.avg_cost = row.issue_price
    }
    row.query = `${compactSymbol(row.symbol)} ${rowShortName(row)}`.trim()
  } finally {
    row.quoteLoading = false
  }
}

const chooseMatch = async (row: ManualRow, match: StockSearchItem) => {
  row.symbol = match.symbol
  row.name = canonicalNames[compactSymbol(match.symbol)] || match.name
  row.asset_type = match.asset_type || 'stock'
  row.ipo_status = match.ipo_status || ''
  row.issue_price = match.issue_price ?? null
  if (row.asset_type === 'ipo_subscription' && (!row.avg_cost || row.avg_cost <= 0) && row.issue_price) {
    row.avg_cost = row.issue_price
  }
  row.query = `${compactSymbol(match.symbol)} ${row.name}`
  rowMatches.value = []
  activeRowId.value = ''
  await loadQuoteForRow(row)
  await loadSuggestions()
  applySuggestionToRow(row)
}

const addRow = () => {
  const row = newRow()
  manualRows.value.push(row)
  rowSortOrder.value = [...rowSortOrder.value, row.row_id]
}

const removeRow = (rowId: string) => {
  manualRows.value = manualRows.value.filter((row) => row.row_id !== rowId)
  rowSortOrder.value = rowSortOrder.value.filter((id) => id !== rowId)
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

const ensureCatalogTag = (tag: string) => {
  if (!tag) return
  hiddenDirectionCatalog.value = hiddenDirectionCatalog.value.filter((item) => item !== tag)
  if (!supportedDirections.includes(tag) && !customDirectionCatalog.value.includes(tag)) {
    customDirectionCatalog.value = [...customDirectionCatalog.value, tag]
  }
}

const addCustomDirection = (row: ManualRow) => {
  const tag = normalizeTag(tagDrafts.value[row.row_id] || '')
  if (!tag) return
  ensureCatalogTag(tag)
  if (!row.directions.includes(tag)) {
    row.directions = [...row.directions, tag]
  }
  tagDrafts.value[row.row_id] = ''
}

const addCatalogDirection = () => {
  const tag = normalizeTag(directionCatalogDraft.value)
  if (!tag) return
  ensureCatalogTag(tag)
  directionCatalogDraft.value = ''
}

const removeCatalogDirection = (tag: string) => {
  hiddenDirectionCatalog.value = Array.from(new Set([...hiddenDirectionCatalog.value, tag]))
  customDirectionCatalog.value = customDirectionCatalog.value.filter((item) => item !== tag)
  manualRows.value = manualRows.value.map((row) => ({
    ...row,
    directions: row.directions.filter((item) => item !== tag),
  }))
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
        available_quantity: null,
        avg_cost: Number(row.avg_cost || 0),
        asset_type: row.asset_type || 'stock',
        ipo_status: row.ipo_status || null,
        issue_price: row.issue_price ?? null,
        expected_list_date: row.expected_list_date || null,
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
    refreshMarketValueOrder()
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

const openImport = async (kind: 'current_holdings' | 'trade_history') => {
  expanded.value = true
  setImportKind(kind)
  await nextTick()
  importSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

defineExpose({ openImport })

watch(
  () => props.openImportRequest,
  () => {
    if (props.openImportKind) openImport(props.openImportKind)
  },
  { immediate: true },
)

onMounted(load)
</script>

<template>
  <section class="mb-4 overflow-hidden rounded-lg border border-border bg-card">
    <button class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left" @click="expanded = !expanded">
      <div class="min-w-0">
        <h2 class="text-sm font-semibold text-foreground">组合与手动账户快照</h2>
        <p class="text-[11px] text-muted-foreground">手动维护持仓、确认主题归属与持仓角色；保存后进入 Portfolio Packet 和未来账户级 AI 输入。</p>
      </div>
      <span class="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{{ expanded ? '收起' : '展开' }}</span>
    </button>

    <div v-if="expanded" class="space-y-4 border-t border-border p-4">
      <div v-if="loading" class="text-xs text-muted-foreground">加载组合...</div>

      <template v-else>
        <div ref="importSection" class="scroll-mt-20 border-y border-border py-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 class="text-xs font-semibold text-foreground">账户截图导入</h3>
              <p class="mt-1 text-[11px] leading-5 text-muted-foreground">
                MiniMax M3 仅生成待确认草稿；持仓快照与成交记录分别处理。
              </p>
            </div>
            <div class="text-right text-[11px] text-muted-foreground">
              <div>{{ visionProvider?.model || 'minimax-m3' }}</div>
              <div>{{ visionAvailable ? '云端解析已配置' : '云端解析不可用' }}</div>
            </div>
          </div>

          <div class="mt-3 inline-flex border border-border text-xs">
            <button
              type="button"
              :class="['h-8 px-3', importKind === 'current_holdings' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary']"
              @click="setImportKind('current_holdings')"
            >
              当前持仓截图
            </button>
            <button
              type="button"
              :class="['h-8 border-l border-border px-3', importKind === 'trade_history' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary']"
              @click="setImportKind('trade_history')"
            >
              交易行为截图
            </button>
          </div>

          <div
            :class="[
              'mt-3 flex min-h-[112px] cursor-pointer flex-col items-center justify-center border border-dashed px-4 py-5 text-center transition-colors',
              importDropActive ? 'border-primary bg-primary/10' : 'border-border hover:bg-secondary/30',
            ]"
            @click="selectImportFile"
            @dragenter.prevent="importDropActive = true"
            @dragover.prevent="importDropActive = true"
            @dragleave.prevent="importDropActive = false"
            @drop.prevent="onImportDrop"
          >
            <input
              ref="importFileInput"
              class="hidden"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              @change="onImportFileSelected"
            />
            <div class="text-xs font-medium text-foreground">
              {{ importFile ? importFile.name : `拖拽或点击选择${importKind === 'trade_history' ? '交易行为' : '当前持仓'}截图` }}
            </div>
            <div class="mt-1 text-[11px] text-muted-foreground">PNG、JPEG、WebP，最大 8MB</div>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <label class="flex items-center gap-2 text-[11px] text-muted-foreground">
              <input v-model="importConsent" type="checkbox" @click.stop @change="onImportConsentChanged" />
              <span>同意将截图发送至火山引擎 MiniMax M3</span>
            </label>
            <button
              type="button"
              class="h-8 rounded bg-primary px-3 font-medium disabled:opacity-50"
              :disabled="!visionAvailable || !importFile || !importConsent || importLoading"
              @click="recognizePortfolioScreenshot"
            >
              {{ importLoading ? '识别中...' : '识别为草稿' }}
            </button>
          </div>

          <div v-if="importDraft" class="mt-3 space-y-3">
            <div class="grid grid-cols-2 border border-border text-xs md:grid-cols-4">
              <label v-if="importDraft.screenshot_kind === 'current_holdings'" class="border-b border-r border-border p-2 md:border-b-0">
                <span class="text-[10px] text-muted-foreground">总资产</span>
                <input v-model.number="importDraft.account_summary_draft.total_assets_ocr" class="mt-1 h-7 w-full bg-input px-2 font-mono" type="number" />
              </label>
              <label v-if="importDraft.screenshot_kind === 'current_holdings'" class="border-b border-border p-2 md:border-b-0 md:border-r">
                <span class="text-[10px] text-muted-foreground">可用现金</span>
                <input v-model.number="importDraft.account_summary_draft.cash_available_ocr" class="mt-1 h-7 w-full bg-input px-2 font-mono" type="number" />
              </label>
              <div v-if="importDraft.screenshot_kind === 'trade_history'" class="border-b border-r border-border p-2 md:border-b-0">
                <div class="text-[10px] text-muted-foreground">截图类型</div>
                <div class="mt-1 text-sm font-semibold text-foreground">交易行为</div>
              </div>
              <div v-if="importDraft.screenshot_kind === 'trade_history'" class="border-b border-border p-2 md:border-b-0 md:border-r">
                <div class="text-[10px] text-muted-foreground">应用建议</div>
                <div class="mt-1 text-sm font-semibold text-foreground">
                  {{ importDraft.transaction_apply_recommendation === 'apply' ? '可应用' : importDraft.transaction_apply_recommendation === 'record_only' ? '仅记录' : '需核对' }}
                </div>
              </div>
              <div class="border-r border-border p-2">
                <div class="text-[10px] text-muted-foreground">识别行数</div>
                <div class="mt-1 font-mono text-sm font-semibold">{{ importRowCount }}</div>
              </div>
              <div class="p-2">
                <div class="text-[10px] text-muted-foreground">Token 使用</div>
                <div class="mt-1 font-mono text-sm font-semibold">{{ importDraft.provider_usage?.total_tokens || '--' }}</div>
              </div>
            </div>

            <div v-if="importDraft.screenshot_kind === 'current_holdings'" class="overflow-x-auto border border-border">
              <table class="w-full min-w-[920px] table-fixed text-xs">
                <colgroup>
                  <col class="w-[110px]" />
                  <col class="w-[150px]" />
                  <col class="w-[105px]" />
                  <col class="w-[105px]" />
                  <col class="w-[105px]" />
                  <col class="w-[105px]" />
                  <col class="w-[150px]" />
                  <col class="w-[190px]" />
                </colgroup>
                <thead class="bg-secondary/40 text-muted-foreground">
                  <tr>
                    <th class="px-2 py-2 text-left">代码</th>
                    <th class="px-2 py-2 text-left">名称</th>
                    <th class="px-2 py-2 text-right">持仓</th>
                    <th class="px-2 py-2 text-right">可用</th>
                    <th class="px-2 py-2 text-right" title="支持券商摊薄口径下的负成本">成本</th>
                    <th class="px-2 py-2 text-right">截图现价</th>
                    <th class="px-2 py-2 text-left">相对上次快照</th>
                    <th class="px-2 py-2 text-left">校验</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in importRows" :key="row.row_id" class="border-t border-border align-top">
                    <td class="p-2"><input v-model="row.raw_symbol_text" class="h-8 w-full bg-input px-2 font-mono" placeholder="可留空" /></td>
                    <td class="p-2"><input v-model="row.raw_name_text" class="h-8 w-full bg-input px-2" /></td>
                    <td class="p-2"><input v-model.number="row.quantity" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" /></td>
                    <td class="p-2"><input v-model.number="row.available_quantity" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" /></td>
                    <td class="p-2"><input v-model.number="row.avg_cost" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" step="0.001" /></td>
                    <td class="p-2"><input v-model.number="row.broker_screenshot_price" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" step="0.001" /></td>
                    <td class="p-2">
                      <div class="font-medium text-foreground">{{ importAction(row).label }}</div>
                      <div class="mt-1 font-mono text-[10px] text-muted-foreground">{{ importAction(row).before }} → {{ importAction(row).after }}</div>
                    </td>
                    <td class="p-2">
                      <div v-if="row.normalized_symbol" class="font-mono text-[10px] text-positive">{{ row.normalized_symbol }}</div>
                      <div v-for="warning in row.validation_warnings" :key="warning" class="mt-1 text-[10px] leading-4 text-warning">{{ warning }}</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else class="overflow-x-auto border border-border">
              <table class="w-full min-w-[860px] table-fixed text-xs">
                <colgroup>
                  <col class="w-[120px]" />
                  <col class="w-[170px]" />
                  <col class="w-[90px]" />
                  <col class="w-[120px]" />
                  <col class="w-[120px]" />
                  <col class="w-[140px]" />
                  <col class="w-[210px]" />
                </colgroup>
                <thead class="bg-secondary/40 text-muted-foreground">
                  <tr>
                    <th class="px-2 py-2 text-left">代码</th>
                    <th class="px-2 py-2 text-left">证券名称</th>
                    <th class="px-2 py-2 text-left">方向</th>
                    <th class="px-2 py-2 text-right">成交均价</th>
                    <th class="px-2 py-2 text-right">成交量</th>
                    <th class="px-2 py-2 text-right">成交额</th>
                    <th class="px-2 py-2 text-left">校验</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in importTransactionRows" :key="row.row_id" class="border-t border-border align-top">
                    <td class="p-2"><input v-model="row.raw_symbol_text" class="h-8 w-full bg-input px-2 font-mono" placeholder="可留空" /></td>
                    <td class="p-2"><input v-model="row.raw_name_text" class="h-8 w-full bg-input px-2" /></td>
                    <td class="p-2">
                      <select v-model="row.side" class="h-8 w-full bg-input px-2">
                        <option value="buy">买入</option>
                        <option value="sell">卖出</option>
                      </select>
                    </td>
                    <td class="p-2"><input v-model.number="row.average_price" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" step="0.001" /></td>
                    <td class="p-2"><input v-model.number="row.quantity" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" /></td>
                    <td class="p-2"><input v-model.number="row.amount" class="h-8 w-full bg-input px-2 text-right font-mono" type="number" step="0.001" /></td>
                    <td class="p-2">
                      <div v-if="row.normalized_symbol" class="font-mono text-[10px] text-positive">{{ row.normalized_symbol }}</div>
                      <div v-for="warning in row.validation_warnings" :key="warning" class="mt-1 text-[10px] leading-4 text-warning">{{ warning }}</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="importDraft.screenshot_kind === 'trade_history'" class="border border-border p-3">
              <div class="text-xs font-medium text-foreground">交易记录处理方式</div>
              <div class="mt-2 grid gap-2 md:grid-cols-2">
                <label :class="['flex cursor-pointer gap-2 border p-3 text-xs', tradeApplyMode === 'record_only' ? 'border-primary bg-primary/10' : 'border-border']">
                  <input v-model="tradeApplyMode" type="radio" value="record_only" />
                  <span>
                    <span class="block font-medium text-foreground">仅记录交易</span>
                    <span class="mt-1 block text-[11px] leading-5 text-muted-foreground">当前持仓截图已包含这些成交时使用，不重复加减仓。</span>
                  </span>
                </label>
                <label :class="['flex cursor-pointer gap-2 border p-3 text-xs', tradeApplyMode === 'apply' ? 'border-primary bg-primary/10' : 'border-border']">
                  <input v-model="tradeApplyMode" type="radio" value="apply" />
                  <span>
                    <span class="block font-medium text-foreground">记录并更新持仓</span>
                    <span class="mt-1 block text-[11px] leading-5 text-muted-foreground">按成交量调整持仓与现金，买入按成交额计算加权成本。</span>
                  </span>
                </label>
              </div>
              <div
                v-if="importDraft.transaction_apply_reason"
                :class="['mt-2 text-[11px] leading-5', importDraft.transaction_apply_recommendation === 'apply' ? 'text-positive' : 'text-warning']"
              >
                系统建议：{{ importDraft.transaction_apply_reason }}
              </div>
              <div class="mt-3 border-t border-border pt-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div class="text-xs font-medium text-foreground">交易理由</div>
                    <div class="mt-1 text-[11px] text-muted-foreground">作为事后复盘依据；DeepSeek 草稿必须由你确认或修改。</div>
                  </div>
                  <button
                    type="button"
                    class="h-8 rounded border border-border px-3 text-xs text-foreground hover:bg-secondary disabled:opacity-50"
                    :disabled="tradeReasonLoading"
                    @click="generateTradeReasonDraft"
                  >
                    {{ tradeReasonLoading ? '生成中...' : 'AI 生成理由草稿' }}
                  </button>
                </div>
                <textarea
                  v-model="tradeDecisionReason"
                  rows="3"
                  class="mt-2 w-full resize-y rounded border border-border bg-background px-3 py-2 text-xs leading-5 text-foreground"
                  placeholder="例如：降低高波动敞口；兑现部分利润；切换到更有把握的方向。"
                ></textarea>
                <div v-if="tradeReasonQuestions.length" class="mt-2 text-[11px] leading-5 text-warning">
                  待补充：{{ tradeReasonQuestions.join('；') }}
                </div>
              </div>
            </div>

            <div v-if="importDraft.parse_warnings.length" class="space-y-1 text-[11px] text-warning">
              <div v-for="warning in importDraft.parse_warnings" :key="warning">{{ warning }}</div>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="text-[11px] text-muted-foreground">
                {{ importDraft.screenshot_kind === 'trade_history'
                  ? '确认后写入交易台账；只有选择“记录并更新持仓”时才生成新持仓快照。'
                  : '确认后保存新快照；旧快照保留，用于推导加仓、减仓、建仓和清仓记录。' }}
              </div>
              <div class="flex gap-2">
                <button type="button" class="h-8 rounded border border-border px-3 text-muted-foreground" :disabled="importConfirming" @click="discardImportDraft">放弃草稿</button>
                <button type="button" class="h-8 rounded bg-primary px-3 font-medium disabled:opacity-50" :disabled="importConfirming" @click="confirmImportedPortfolio">
                  {{ importConfirming
                    ? '保存中...'
                    : importDraft.screenshot_kind === 'trade_history'
                      ? tradeApplyMode === 'apply' ? '确认交易并更新持仓' : '确认并记录交易'
                      : '确认并更新持仓' }}
                </button>
              </div>
            </div>
          </div>

          <div v-if="importNotice" class="mt-2 text-xs text-positive">{{ importNotice }}</div>
          <div v-if="importError" class="mt-2 text-xs text-negative">{{ importError }}</div>
        </div>

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
            <div v-if="accountTotalPnl !== null" :class="['font-mono text-base font-semibold', accountTotalPnl >= 0 ? 'text-market-up' : 'text-market-down']">
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
          <table class="w-full min-w-[980px] table-fixed text-xs">
            <colgroup>
              <col class="w-[220px]" />
              <col class="w-[90px]" />
              <col class="w-[90px]" />
              <col class="w-[120px]" />
              <col class="w-[110px]" />
              <col class="w-[100px]" />
              <col class="w-[300px]" />
              <col class="w-[100px]" />
              <col class="w-[56px]" />
            </colgroup>
            <thead class="bg-secondary/40 text-muted-foreground">
              <tr>
                <th class="px-2 py-2 text-left">标的</th>
                <th class="px-2 py-2 text-right">持仓</th>
                <th class="px-2 py-2 text-right" title="支持卖出获利后形成的负摊薄成本">成本</th>
                <th class="px-2 py-2 text-right">现价 / 涨跌</th>
                <th class="px-2 py-2 text-right">
                  <button class="w-full text-right hover:text-foreground" type="button" @click="toggleMarketValueSort">
                    市值 {{ marketValueSort === 'desc' ? '↓' : '↑' }}
                  </button>
                </th>
                <th class="px-2 py-2 text-right">账户权重</th>
                <th class="px-2 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <span>关联方向</span>
                    <button
                      type="button"
                      class="rounded border border-border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                      @click="editingDirectionCatalog = !editingDirectionCatalog"
                    >
                      {{ editingDirectionCatalog ? '收起' : '标签管理' }}
                    </button>
                  </div>
                  <div v-if="editingDirectionCatalog" class="mt-2 space-y-2 rounded border border-border/60 bg-background/60 p-2 text-left">
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="tag in allDirectionOptions"
                        :key="tag"
                        class="inline-flex items-center gap-1 rounded border border-border/80 bg-secondary/30 px-2 py-1 text-[11px] text-foreground"
                      >
                        {{ themeLabel(tag) }}
                        <button type="button" class="text-negative" @click="removeCatalogDirection(tag)">×</button>
                      </span>
                    </div>
                    <div class="flex gap-1">
                      <input
                        v-model="directionCatalogDraft"
                        class="h-7 min-w-0 flex-1 rounded bg-input px-2 text-[11px]"
                        placeholder="新增标签，如 有色金属"
                        @keydown.enter.prevent="addCatalogDirection"
                      />
                      <button type="button" class="rounded border border-primary px-2 py-1 text-[11px]" @click="addCatalogDirection">
                        新增
                      </button>
                    </div>
                    <div class="text-[11px] text-muted-foreground">删除标签会同步从所有标的的关联方向中移除。</div>
                  </div>
                </th>
                <th class="px-2 py-2">角色</th>
                <th class="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in displayedRows" :key="row.row_id" class="border-t border-border/50 align-top">
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
                      <span v-if="marketBadge(row)" class="rounded bg-secondary px-1 text-muted-foreground">{{ marketBadge(row) }}</span>
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
                <td class="p-2"><input v-model.number="row.quantity" class="h-9 w-full rounded bg-input px-2 text-right font-mono" min="0" type="number" /></td>
                <td class="p-2"><input v-model.number="row.avg_cost" class="h-9 w-full rounded bg-input px-2 text-right font-mono" step="0.001" type="number" /></td>
                <td class="p-2 text-right font-mono">
                  <div>{{ fmt(displayPrice(row)) }}</div>
                  <div :class="['text-[11px]', Number(row.quote?.change_pct || 0) > 0 ? 'text-market-up' : Number(row.quote?.change_pct || 0) < 0 ? 'text-market-down' : 'text-muted-foreground']">
                    {{ row.asset_type === 'ipo_subscription' && !row.quote?.change_pct ? 'IPO/待上市' : signedFmt(row.quote?.change_pct, '%') }}
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
