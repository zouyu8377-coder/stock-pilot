import axios from 'axios'
import { API_BASE_URL } from './config'

export { API_BASE_URL }

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000,
})

export interface Indicator {
  ma5: number
  ma10: number
  ma20: number
  ma30: number
  ma60: number
  rsi14: number
  macd: number
}

export interface Analysis {
  trend: string
  signal: string
  support: string
  resistance: string
  summary: string
}

export interface Stock {
  symbol: string
  price: number
  change_pct: number
  name: string
  volume: number
  provider: string
  hot_status: string
  cold_status: string
  ai_status: string
  history_ready: boolean
  indicators: Indicator
  analysis: Analysis
  market_cap?: number
  float_market_cap?: number
  pe?: number
  pb?: number
  turnover_rate?: number
  volume_ratio?: number
  industry?: string
  area?: string
  list_date?: string
}

export interface AnalyzeResponse {
  status: string
  stocks: Stock[]
}

export interface ColdDataStatus {
  status: string
  provider: string
  target_date: string
  last_trading_date: string | null
  completed_count: number
  failed_count: number
  total_symbols: number
  remaining_count: number
  processed_count: number
  current_symbol?: string | null
  progress: number
  updated_at?: string | null
  failure_reasons: Record<string, number>
  phase?: string | null
  core_total?: number
  core_completed?: number
  core_failed?: number
  core_status?: string | null
  core_last_trading_date?: string | null
  market_total?: number
  market_processed?: number
  deferred_reason?: string | null
  average_symbol_seconds?: number | null
  components?: {
    stock?: ColdDataStatus
    etf?: ColdDataStatus
  }
}

export interface StockSearchItem {
  symbol: string
  name: string
  industry?: string
  area?: string
  asset_type?: string
  ipo_status?: string | null
  issue_price?: number | null
  fund_type?: string
  management?: string
}

export interface StockQuoteInfo extends StockSearchItem {
  price?: number | null
  change_pct?: number | null
  volume?: number | null
  provider?: string | null
  quote_status: string
  quote_error?: string | null
  list_date?: string | null
  asset_type?: string
  ipo_status?: string | null
  issue_price?: number | null
  fund_type?: string
  management?: string
}

export interface FactEvidence {
  evidence_type: string
  category: string
  title: string
  source: string
  as_of_date?: string | null
  reliability: string
  llm_usage: string
  interpretation_limit?: string | null
  data_status: string
}

export interface EtfFacts {
  symbol: string
  name: string
  full_name?: string
  index_name?: string
  manager?: string
  as_of_date?: string | null
  latest_share?: number | null
  latest_size?: number | null
  nav?: number | null
  close?: number | null
  share_change: Record<string, number | null>
  price_change: Record<string, number | null>
  share_streak_days: number
  quadrant_label: string
  interpretation_limit: string
}

export interface DragonTigerEvent {
  trade_date: string
  reason: string
  close?: number | null
  pct_change?: number | null
  amount?: number | null
  total_buy?: number | null
  total_sell?: number | null
  net_buy?: number | null
  net_buy_amount_rate?: number | null
  top_buy_seats: Array<Record<string, any>>
  top_sell_seats: Array<Record<string, any>>
  has_institutional_seat: boolean
  has_stock_connect_seat: boolean
  interpretation_limit: string
}

export interface DisclosureFacts {
  announcements: Array<{
    ann_date: string
    title: string
    url: string
    category_label: string
    interpretation_limit: string
  }>
  surveys: Array<{
    surv_date: string
    rece_mode: string
    rece_org: string
    org_type: string
    comp_rece: string
    rece_place: string
    interpretation_limit: string
  }>
  announcement_interpretation_limit: string
  survey_interpretation_limit: string
  empty_message: string
}

export interface FactResponse<T> {
  success: boolean
  symbol: string
  message?: string
  data_status: string
  data: T
  evidence: FactEvidence[]
}

export interface PortfolioPosition {
  symbol: string
  name: string
  quantity: number
  available_quantity?: number | null
  avg_cost: number
  broker_screenshot_price?: number | null
  broker_screenshot_price_source?: string | null
  broker_screenshot_price_time?: string | null
  broker_screenshot_market_value?: number | null
  broker_screenshot_unrealized_pnl?: number | null
  broker_screenshot_unrealized_pnl_pct?: number | null
  asset_type?: string
  ipo_status?: string | null
  issue_price?: number | null
  expected_list_date?: string | null
  system_quote_price?: number | null
  system_quote_retrieved_at?: string | null
  system_quote_market_time?: string | null
  quote_time_status?: string
  position_status?: string
  valuation_scope?: string
  source_type?: string
  source_name?: string | null
  import_draft_id?: string | null
  confirmed_by_user?: boolean
  market_price?: number | null
  market_value?: number | null
  unrealized_pnl?: number | null
  unrealized_pnl_pct?: number | null
  data_status?: string
  missing_data?: string[]
  position_role: string
  theme_tags: string[]
  primary_theme?: string | null
  directions: string[]
  risk_flags: string[]
  semantic_classification_status?: string
  semantic_classification_source?: string | null
  semantic_classification_confirmed_at?: string | null
  user_plan: string
  invalid_condition?: string | null
  target_max_weight?: number | null
  notes?: string | null
}

export interface PortfolioImportDraft {
  draft_id: string
  source_type: string
  source_name: string
  uploaded_at: string
  image_reference: string
  parser_provider: string
  cloud_send_consent: boolean
  user_notice_acknowledged_at?: string | null
  cloud_parse_status?: string | null
  ocr_provider: string
  ocr_status: string
  ocr_raw_text: string
  parse_status: string
  needs_user_confirmation: boolean
  account_summary_draft: Record<string, any>
  holding_rows_draft: Array<Record<string, any>>
  parse_warnings: string[]
  unrecognized_fields: string[]
  provider_error_summary?: string | null
  confirmed_at?: string | null
  saved_snapshot_id?: string | null
}

export interface PortfolioParserProviderStatus {
  default_provider: string
  providers: Array<Record<string, any>>
}

export interface PortfolioState {
  snapshot: {
    portfolio_id: string
    snapshot_time: string
    total_assets?: number | null
    cash_available: number
    account_actual_total_cost?: number | null
    account_actual_total_cost_source?: string | null
    account_actual_total_cost_confirmed_at?: string | null
    repo_amount: number
    repo_available_date?: string | null
    notes?: string | null
    risk_limits: {
      max_position_weight: number
      max_theme_weight: number
      min_cash_ratio: number
    }
    positions: PortfolioPosition[]
  }
  metrics: {
    total_assets: number
    total_market_value: number
    cash_available: number
    account_actual_total_cost?: number | null
    account_total_pnl?: number | null
    account_total_pnl_pct?: number | null
    current_holding_cost_basis?: number | null
    current_holding_unrealized_pnl?: number | null
    current_holding_unrealized_pnl_pct?: number | null
    repo_amount: number
    cash_ratio_pct: number
    repo_ratio_pct: number
    invested_ratio_pct: number
    position_weights: Array<Record<string, any>>
    pnl_contributors: Array<Record<string, any>>
    primary_theme_exposures: Array<Record<string, any>>
    risk_tag_exposures: Array<Record<string, any>>
    warnings: string[]
    composite_exposure_notes: string[]
    missing_data: Array<Record<string, any>>
    active_position_count?: number
    watchlist_position_count?: number
    watchlist_symbols?: string[]
  }
  supported_directions: string[]
  supported_risk_flags: string[]
  supported_theme_tags: string[]
  supported_primary_themes: string[]
  supported_position_roles: string[]
}

export interface HoldingSemanticSuggestion {
  symbol: string
  suggested_primary_theme?: string | null
  suggested_theme_tags: string[]
  suggested_directions: string[]
  suggested_risk_flags: string[]
  suggested_position_role: string
  source: string
  source_detail?: string | null
  requires_user_confirmation: boolean
  note?: string | null
}

export interface ManualEvidenceRecord {
  evidence_id: string
  symbol?: string | null
  evidence_type: string
  title: string
  value?: any
  text: string
  as_of_time?: string | null
  as_of_date?: string | null
  recorded_at: string
  source: string
  reliability: string
  llm_usage: string
  attachment_path?: string | null
  image_reference?: string | null
  notes?: string | null
  include_in_analysis_packet: boolean
  holder_num?: number | null
  end_date?: string | null
  announcement_date?: string | null
  change_from_previous?: number | null
  screenshot?: string | null
}

export interface AnalysisPacketResponse {
  success: boolean
  packet: Record<string, any>
  markdown: string
  saved_paths?: {
    json_path: string
    markdown_path: string
  }
}

export interface PortfolioDashboard {
  generated_at: string
  account_facts: Record<string, any>
  positions: Array<PortfolioPosition & {
    portfolio_weight_pct?: number | null
    trend?: Record<string, any>
    attractiveness?: Record<string, any>
  }>
  opportunity_queue: Array<Record<string, any>>
  risk_queue: Array<Record<string, any>>
  strategy_matrix: Array<Record<string, any>>
  primary_direction_grouping: Array<Record<string, any>>
  risk_observations: Record<string, any>
  data_gaps: Array<Record<string, any> | string>
  market_event_radar?: {
    generated_at: string
    window_days: number
    high_impact_count: number
    next_event?: Record<string, any> | null
    events: Array<Record<string, any>>
    boundary: string
  }
  theme_evidence_radar?: {
    generated_at?: string
    registry_version?: string
    registry_updated_at?: string
    themes: Array<Record<string, any>>
    boundary?: string
  }
  attractiveness_radar?: {
    generated_at: string
    model: string
    positions: Array<Record<string, any>>
    benchmark?: Record<string, any>
    validation?: Record<string, any>
    data_quality?: Record<string, any>
    boundary: string
  }
  external_ai_tasks: string[]
  boundaries: Record<string, any>
}

export async function analyzeStock(symbol: string): Promise<AnalyzeResponse> {
  const response = await client.post<AnalyzeResponse>('/api/analyze', {
    symbols: [symbol],
  })
  return response.data
}

export async function getColdDataStatus(): Promise<ColdDataStatus> {
  const response = await client.get<ColdDataStatus>('/api/system/cold-data-status')
  return response.data
}

export async function searchStocks(query: string, limit = 20): Promise<StockSearchItem[]> {
  const response = await client.get<{ items: StockSearchItem[] }>('/api/stocks/search', {
    params: {
      q: query,
      limit,
    },
  })
  return response.data.items
}

export async function getStockQuote(symbol: string): Promise<StockQuoteInfo> {
  const response = await client.get<{ success: boolean; data: StockQuoteInfo }>(`/api/stocks/${symbol}/quote`)
  return response.data.data
}

export async function getEtfFacts(symbol: string): Promise<FactResponse<EtfFacts | null>> {
  const response = await client.get<FactResponse<EtfFacts | null>>(`/api/facts/etf/${symbol}`)
  return response.data
}

export async function getDragonTigerFacts(symbol: string): Promise<FactResponse<{
  latest_event: DragonTigerEvent | null
  events: DragonTigerEvent[]
  empty_message: string
  interpretation_limit: string
}>> {
  const response = await client.get<FactResponse<any>>(`/api/facts/dragon-tiger/${symbol}`)
  return response.data
}

export async function getDisclosureFacts(symbol: string): Promise<FactResponse<DisclosureFacts>> {
  const response = await client.get<FactResponse<DisclosureFacts>>(`/api/facts/disclosures/${symbol}`)
  return response.data
}

export async function getPortfolio(): Promise<PortfolioState> {
  const response = await client.get<{ success: boolean; data: PortfolioState }>('/api/portfolio')
  return response.data.data
}

export async function savePortfolio(payload: any): Promise<PortfolioState> {
  const response = await client.put<{ success: boolean; data: PortfolioState }>('/api/portfolio', payload)
  return response.data.data
}

export async function getPortfolioSemanticSuggestions(): Promise<HoldingSemanticSuggestion[]> {
  const response = await client.get<{ success: boolean; items: HoldingSemanticSuggestion[] }>('/api/portfolio/semantic-suggestions')
  return response.data.items
}

export async function updateHoldingSemantics(payload: any): Promise<PortfolioState> {
  const response = await client.patch<{ success: boolean; data: PortfolioState }>('/api/portfolio/holding-semantics', payload)
  return response.data.data
}

export async function getAccountAnalysisContext(): Promise<any> {
  const response = await client.get<{ success: boolean; data: any }>('/api/portfolio/account-analysis-context')
  return response.data.data
}

export async function getPortfolioDashboard(force = false): Promise<PortfolioDashboard> {
  const response = await client.get<{ success: boolean; data: PortfolioDashboard }>(
    '/api/portfolio/dashboard',
    { params: force ? { force: true } : undefined },
  )
  return response.data.data
}

export async function listManualEvidence(): Promise<ManualEvidenceRecord[]> {
  const response = await client.get<{ success: boolean; items: ManualEvidenceRecord[] }>('/api/portfolio/manual-evidence')
  return response.data.items
}

export async function addManualEvidence(payload: any): Promise<ManualEvidenceRecord> {
  const response = await client.post<{ success: boolean; data: ManualEvidenceRecord }>('/api/portfolio/manual-evidence', payload)
  return response.data.data
}

export async function deleteManualEvidence(evidenceId: string): Promise<void> {
  await client.delete(`/api/portfolio/manual-evidence/${evidenceId}`)
}

export async function updateManualEvidenceInclude(evidenceId: string, include: boolean): Promise<ManualEvidenceRecord> {
  const response = await client.patch<{ success: boolean; data: ManualEvidenceRecord }>(
    `/api/portfolio/manual-evidence/${evidenceId}/include`,
    { include_in_analysis_packet: include },
  )
  return response.data.data
}

export async function simulateTrade(payload: any): Promise<any> {
  const response = await client.post<{ success: boolean; data: any }>('/api/portfolio/simulate', payload)
  return response.data.data
}

export async function getPortfolioSnapshot(): Promise<any> {
  const response = await client.get<{ success: boolean; data: any }>('/api/portfolio/analysis-snapshot')
  return response.data.data
}

export async function createSingleAnalysisPacket(symbol: string, userQuestion = ''): Promise<AnalysisPacketResponse> {
  const response = await client.post<AnalysisPacketResponse>(`/api/analysis-packet/single/${symbol}`, null, {
    params: userQuestion ? { user_question: userQuestion } : undefined,
  })
  return response.data
}

export async function createPortfolioAnalysisPacket(userQuestion = '', options: { staleDraft?: boolean } = {}): Promise<AnalysisPacketResponse> {
  const response = await client.post<AnalysisPacketResponse>('/api/analysis-packet/portfolio', null, {
    params: {
      ...(userQuestion ? { user_question: userQuestion } : {}),
      ...(options.staleDraft ? { stale_draft: true } : {}),
    },
  })
  return response.data
}

export async function getPortfolioImportParserProviders(): Promise<PortfolioParserProviderStatus> {
  const response = await client.get<{ success: boolean; data: PortfolioParserProviderStatus }>('/api/portfolio/import/parser-providers')
  return response.data.data
}

export async function uploadPortfolioScreenshot(
  file: File,
  options: { parser_provider?: string; cloud_send_consent?: boolean; user_notice_acknowledged_at?: string | null } = {},
): Promise<PortfolioImportDraft> {
  const form = new FormData()
  form.append('file', file)
  form.append('parser_provider', options.parser_provider || 'local_noop')
  form.append('cloud_send_consent', String(options.cloud_send_consent || false))
  if (options.user_notice_acknowledged_at) form.append('user_notice_acknowledged_at', options.user_notice_acknowledged_at)
  const response = await client.post<{ success: boolean; data: PortfolioImportDraft }>('/api/portfolio/import/screenshot', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data.data
}

export async function updatePortfolioImportDraft(draftId: string, payload: any): Promise<PortfolioImportDraft> {
  const response = await client.patch<{ success: boolean; data: PortfolioImportDraft }>(`/api/portfolio/import/drafts/${draftId}`, payload)
  return response.data.data
}

export async function confirmPortfolioImportDraft(draftId: string): Promise<{ draft: PortfolioImportDraft; portfolio: PortfolioState }> {
  const response = await client.post<{ success: boolean; data: { draft: PortfolioImportDraft; portfolio: PortfolioState } }>(`/api/portfolio/import/drafts/${draftId}/confirm`)
  return response.data.data
}

export async function rejectPortfolioImportDraft(draftId: string): Promise<PortfolioImportDraft> {
  const response = await client.delete<{ success: boolean; data: PortfolioImportDraft }>(`/api/portfolio/import/drafts/${draftId}`)
  return response.data.data
}
