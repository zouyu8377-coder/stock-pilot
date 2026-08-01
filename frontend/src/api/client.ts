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
  stale_count?: number
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
    rotation?: ColdDataStatus
  }
}

export interface RotationSector {
  sector_id: string
  name: string
  category: string
  proxy_type: string
  primary_symbol?: string | null
  selected_symbol?: string | null
  proxy_components?: Array<{
    symbol: string
    name?: string
    weight?: number
  }>
  ranking_enabled: boolean
  latest_date?: string | null
  latest_close?: number | null
  returns: Record<string, number | null>
  moving_averages: Record<string, number | null>
  benchmark: Record<string, any>
  relative_strength: Record<string, number | null>
  flow: Record<string, number | null>
  score: {
    trend: number
    momentum: number
    relative_strength: number
    flow: number
    total: number
  }
  score_delta_1d?: number | null
  score_delta_5d?: number | null
  score_delta_10d?: number | null
  maturity: string
  opportunity_stage?: string
  action_label?: string
  chasing_risk?: string
  opportunity_reason?: string
  ma20_distance_pct?: number | null
  data_quality: string
  missing_fields: string[]
  stale_days_to_market?: number | null
  account_exposure?: {
    main_exposure_value: number
    main_exposure_pct: number
    related_holdings: Array<Record<string, any>>
    relation: string
    mapping_rule: string
  }
  proxy_meta?: Record<string, any>
}

export interface RotationSecurityResearch {
  symbol: string
  name: string
  asset_type: 'stock' | 'etf'
  industry?: string | null
  role: 'direction_etf' | 'representative_stock'
  data_quality: string
  latest_date?: string | null
  latest_close?: number | null
  returns?: Record<string, number | null>
  relative_strength_20d?: number | null
  ma20_distance_pct?: number | null
  above_ma20?: boolean | null
  above_ma60?: boolean | null
  trend_state?: string
  amount_ratio_5d?: number | null
  volatility_20d?: number | null
  max_drawdown_60d?: number | null
}

export interface RotationSectorResearch extends RotationSector {
  research_generated_at: string
  research_as_of?: string | null
  research_universe: {
    etf_count: number
    representative_stock_count: number
    selection_note: string
  }
  securities: RotationSecurityResearch[]
  breadth: {
    constituent_count: number
    available_count: number
    above_ma20_pct?: number | null
    above_ma60_pct?: number | null
    advancing_5d_pct?: number | null
    positive_20d_pct?: number | null
    outperform_hs300_20d_pct?: number | null
    median_return_20d?: number | null
    return_dispersion_20d?: number | null
  }
  objective_metrics: {
    relative_win_rate_5d?: number | null
    volatility_20d?: number | null
    max_drawdown_60d?: number | null
    return_60d?: number | null
    data_coverage_pct: number
  }
  evidence_analysis: {
    method: string
    confidence: string
    conclusion: string
    supports: string[]
    cautions: string[]
  }
  trend_series: Array<{
    date: string
    sector: number
    benchmark: number
  }>
}

export interface RotationSummary {
  generated_at: string
  as_of?: string | null
  universe_version: string
  market_style: {
    headline: string
    cooling: string
    benchmark_note: string
  }
  summary: Record<string, number>
  strengthening: RotationSector[]
  cooling: RotationSector[]
  potential_opportunities?: RotationSector[]
  early_turning?: RotationSector[]
  wait_pullback?: RotationSector[]
  avoid_now?: RotationSector[]
  portfolio_alerts: RotationSector[]
  benchmarks: RotationSector[]
  sectors: RotationSector[]
  boundary: string
}

export interface AgentReviewDataStatus {
  usable: boolean
  stale_evidence_refs: string[]
  missing_evidence_refs: string[]
  summary: string
}

export interface AgentReviewItem {
  item_id: string
  subject: string
  conclusion: string
  confidence: 'high' | 'medium' | 'low'
  evidence_refs: string[]
  counter_evidence_refs: string[]
  action_semantics: string
  invalidation_conditions: string[]
}

export interface AgentReviewTask {
  priority: 'high' | 'medium' | 'low'
  subject: string
  task: string
  reason: string
  target_symbols?: string[]
  evidence_type?: 'market_snapshot' | 'rotation' | 'event_outcome' | 'announcement' | 'financial' | 'manual'
  missing_evidence?: string[]
  success_criteria?: string
}

export interface AgentReviewOutput {
  operation_review_period?: 'daily' | 'weekly'
  headline: string
  data_status: AgentReviewDataStatus
  opportunities: AgentReviewItem[]
  risks: AgentReviewItem[]
  watch_items: AgentReviewItem[]
  verification_tasks: AgentReviewTask[]
  changes_since_previous_review?: Array<{
    subject: string
    change_type: 'new' | 'strengthened' | 'weakened' | 'resolved' | 'unchanged'
    summary: string
    evidence_refs: string[]
  }>
  decision_focus?: Array<{
    priority: 'high' | 'medium' | 'low'
    subject: string
    action: 'verify' | 'monitor' | 'review_risk' | 'wait' | 'no_action'
    reason: string
    evidence_refs: string[]
  }>
  daily_operation_review?: {
    trading_date: string
    action_count: number
    items: Array<{
      action_id: string
      symbol: string
      name: string
      action_type: 'buy' | 'sell'
      operation_summary: string
      strategy_reflection: string
      next_review_condition: string
      evidence_refs: string[]
    }>
    overall_reflection: string
  }
  weekly_operation_review?: {
    window_start: string
    window_end: string
    trading_days: string[]
    action_count: number
    symbol_count: number
    items: Array<{
      symbol: string
      name: string
      operation_summary: string
      strategy_reflection: string
      next_review_condition: string
      evidence_refs: string[]
    }>
    overall_reflection: string
  }
  summary: string
}

export interface AgentReviewRun {
  contract_version: string
  run_id: string
  status: 'completed' | 'failed'
  review_mode?: 'initial' | 'verification_followup'
  parent_run_id?: string | null
  provider: string
  model: string
  started_at: string
  completed_at: string
  elapsed_ms: number
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  context?: {
    fingerprint: string
    data_time: Record<string, any>
    freshness: Record<string, any>
    evidence_count: number
    force_context: boolean
  }
  validation_warnings?: string[]
  review?: AgentReviewOutput
  error?: string
}

export interface AgentReviewTask {
  contract_version: string
  task_id: string
  task_key: string
  origin_run_id: string
  priority: 'high' | 'medium' | 'low'
  subject: string
  task: string
  reason: string
  target_symbols?: string[]
  evidence_type?: 'market_snapshot' | 'rotation' | 'event_outcome' | 'announcement' | 'financial' | 'manual'
  missing_evidence?: string[]
  success_criteria?: string
  status: 'pending' | 'running' | 'retry_wait' | 'completed' | 'partial' | 'failed' | 'manual_required' | 'dismissed' | 'superseded'
  tool: {
    name: 'stock_snapshot' | 'rotation_refresh' | 'event_snapshot' | 'disclosure_snapshot' | 'manual_review'
    label: string
    arguments: Record<string, any>
    auto_executable: boolean
    mapping_reason: string
  }
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  attempt_count: number
  max_attempts?: number
  next_retry_at?: string | null
  failure_category?: string | null
  recovery_count?: number
  result?: {
    evidence_ref: string
    tool_name: string
    completed_at: string
    payload: Record<string, any>
  } | null
  error?: string | null
}

export interface AgentReviewStatus {
  enabled: boolean
  provider: string
  model: string
  max_tokens: number
  timeout_seconds: number
  latest_run_id?: string | null
  latest_completed_at?: string | null
  latest_status?: string | null
  privacy_boundary: string
}

export interface AgentAutomationSettings {
  enabled: boolean
  run_time: string
  premarket_enabled: boolean
  premarket_time: string
  weekdays_only: boolean
  auto_execute_tools: boolean
  auto_model_review: boolean
  max_model_calls_per_day: number
  last_scheduled_date?: string | null
  last_premarket_date?: string | null
}

export interface AgentAutomationRun {
  automation_run_id: string
  trigger: string
  status: 'running' | 'completed' | 'failed'
  started_at_local: string
  completed_at_local?: string | null
  model_calls: number
  steps: Array<Record<string, any>>
  error?: string | null
}

export interface AgentAutomationStatus {
  settings: AgentAutomationSettings
  running: boolean
  model_calls_today: number
  scheduled_model_calls_today?: number
  latest_run?: AgentAutomationRun | null
  recent_runs: AgentAutomationRun[]
  task_health?: {
    total: number
    status_counts: Record<string, number>
    failure_counts: Record<string, number>
    retryable_count: number
    source_health?: Array<{
      tool_name: string
      attempt_count: number
      success_count?: number
      partial_count?: number
      failure_count?: number
      reliability_pct?: number
      last_status?: string
      last_attempt_at?: string
      last_failure_category?: string
    }>
  }
  trade_trigger?: {
    mode: string
    review_period?: 'daily' | 'weekly'
    run_time: string
    today_confirmed_action_count: number
    has_confirmed_trade_today: boolean
    last_scheduled_date?: string | null
  }
  premarket_trigger?: {
    enabled: boolean
    run_time: string
    pending_low_confidence_count: number
    last_premarket_date?: string | null
    latest_run_completed_at?: string | null
    model_call_policy: string
  }
  latest_review_completed_at?: string | null
  server_time: string
}

export interface AgentOutcomeRecord {
  recommendation_id: string
  category: 'opportunity' | 'risk' | 'watch'
  subject: string
  conclusion: string
  target_symbols: string[]
  status: string
  created_at: string
  lifecycle?: {
    state: string
    history: Array<{ state: string; at: string; reason: string }>
  }
  decision_snapshot?: {
    schema_version: string
    snapshot_status?: 'frozen' | 'unavailable_legacy'
    captured_at: string
    model?: string
    action_semantics?: string
    invalidation_conditions: string[]
    evidence: Array<Record<string, any>>
    notice?: string
  }
  outcome?: {
    verdict: 'supported' | 'not_supported' | 'mixed' | 'insufficient'
    reason: string
    method: string
    average_return_pct?: number | null
    excess_return_pct?: number | null
    reason_categories?: string[]
    decision_quality?: {
      assessment?: string
      direction_accuracy?: string
      timing_quality?: string
      risk_control_value?: string
      thesis_validity?: string
    }
  } | null
}

export interface PortfolioActionOutcome {
  action_id: string
  symbol: string
  name?: string
  action_type: 'opened' | 'increased' | 'reduced' | 'closed'
  quantity_before: number | null
  quantity_after: number | null
  snapshot_time: string
  source: string
  user_confirmed: boolean
  user_reason?: string | null
  decision_status?: 'candidate' | 'confirmed' | 'dismissed'
  record_quality?: string
  learning_eligible?: boolean
  ai_strategy_comparison?: {
    status: 'aligned' | 'conflicted' | 'mixed' | 'no_direct_recommendation'
    aligned_recommendation_ids: string[]
    conflicted_recommendation_ids: string[]
    matched_recommendations: Array<{
      recommendation_id: string
      category: string
      subject?: string
      conclusion?: string
    }>
    latest_review?: {
      run_id: string
      headline?: string
      summary?: string
    } | null
  }
  outcome?: {
    verdict: 'supported' | 'not_supported' | 'mixed'
    reason: string
    excess_return_pct?: number | null
    reason_categories?: string[]
    decision_quality?: {
      assessment?: string
      direction_accuracy?: string
      timing_quality?: string
      risk_control_value?: string
      thesis_validity?: string
    }
    strategy_fit?: string
    attribution?: {
      direction_effect: string
      estimated_position_effect_pnl?: number | null
      estimated_benchmark_adjusted_pnl?: number | null
      gross_notional_at_baseline?: number | null
      quantity_change_pct?: number | null
      path_interpretation?: string
      reason_capture?: string
      transaction_cost?: { status: string; estimated_fee?: number | null; notice?: string }
      boundary?: string
    }
  } | null
}

export interface WeeklyOperationAggregate {
  evidence_ref: string
  symbol: string
  name: string
  operation_count: number
  buy_count: number
  sell_count: number
  buy_quantity: number
  sell_quantity: number
  net_quantity: number
  quantity_before?: number | null
  quantity_after?: number | null
  pattern: 'accumulation' | 'distribution' | 'two_way_net_buy' | 'two_way_net_sell' | 'round_trip_flat'
  reversal_count: number
  strategy_comparison_counts: Record<string, number>
  sequence: Array<{
    action_id: string
    trading_date: string
    action_type: string
    quantity_delta: number
    average_price?: number | null
    amount?: number | null
    strategy_status: string
    user_reason?: string | null
  }>
  provisional_market_result: {
    status: string
    baseline_date?: string | null
    latest_date?: string | null
    return_pct?: number | null
    benchmark_return_pct?: number | null
    excess_return_pct?: number | null
    notice: string
  }
}

export interface AgentOutcomes {
  recommendations: AgentOutcomeRecord[]
  portfolio_actions: PortfolioActionOutcome[]
  snapshot_changes?: Array<{
    event_id: string
    snapshot_time: string
    account_changes: Record<string, number | null>
    position_changes: Array<Record<string, any>>
  }>
  weekly_operations?: {
    contract_version: string
    window_type: string
    window_start: string
    window_end: string
    trading_dates: string[]
    action_count: number
    symbol_count: number
    items: WeeklyOperationAggregate[]
    method: string
    boundary: string
  }
  summary: {
    recommendation_count: number
    recommendation_evaluated: number
    action_count: number
    action_evaluated: number
    action_candidates?: number
    action_dismissed?: number
    snapshot_change_count?: number
    action_strategy_compared?: number
    action_direct_strategy_compared?: number
  }
  loop_health?: {
    operation_capture_rate_pct?: number | null
    strategy_context_coverage_pct?: number | null
    direct_strategy_match_rate_pct?: number | null
    matured_evaluation_rate_pct?: number | null
    notice?: string
  }
}

export interface AgentMonthlyReport {
  contract_version: string
  month: string
  generated_at: string
  summary: string
  recommendations: {
    evaluated: number
    supported: number
    not_supported: number
    mixed: number
    support_rate_pct?: number | null
    average_excess_return_pct?: number | null
  }
  confirmed_actions: {
    evaluated: number
    supported: number
    not_supported: number
    mixed: number
    support_rate_pct?: number | null
    average_excess_return_pct?: number | null
  }
  unconfirmed_action_count: number
  reason_categories: Array<{ key: string; label: string; count: number }>
  category_stats: Array<Record<string, any>>
  method: string
}

export interface AgentLearningPolicyRegistry {
  contract_version: string
  generated_at?: string
  policies: Array<{
    policy_id: string
    version: number
    status: 'active' | 'monitoring'
    title: string
    trigger: string
    adjustment: string
    sample_count: number
    adverse_count: number
    adverse_rate_pct: number
    confidence: 'high' | 'medium' | 'low'
    evidence_refs: string[]
    updated_at?: string
  }>
  summary?: {
    policy_count: number
    active_count: number
    monitoring_count: number
  }
  boundary?: string
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
  screenshot_kind: 'current_holdings' | 'trade_history'
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
  transaction_rows_draft: Array<Record<string, any>>
  transaction_apply_recommendation?: 'apply' | 'record_only' | 'review_required' | null
  transaction_apply_reason?: string | null
  saved_transaction_batch_id?: string | null
  parse_warnings: string[]
  unrecognized_fields: string[]
  provider_error_summary?: string | null
  provider_model?: string | null
  provider_prompt_version?: string | null
  provider_finish_reason?: string | null
  provider_usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
  }
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
  overseas_tech_chain?: {
    generated_at?: string
    provider?: string
    data_status?: string
    indicator_count?: number
    available_indicator_count?: number
    risk_level?: Record<string, any>
    account_sensitivity_summary?: Record<string, any>
    open_sentiment_observation?: string
    sentiment_path?: string[]
    leading_signals?: Array<Record<string, any>>
    event_watchlist?: Array<Record<string, any>>
    indicators?: Array<Record<string, any>>
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

export async function getRotationSummary(force = false): Promise<RotationSummary> {
  const response = await client.get<{ success: boolean; data: RotationSummary }>(
    '/api/rotation/summary',
    { params: force ? { force: true } : undefined },
  )
  return response.data.data
}

export async function refreshRotationSummary(): Promise<RotationSummary> {
  const response = await client.post<{ success: boolean; data: RotationSummary }>('/api/rotation/refresh')
  return response.data.data
}

export async function getRotationSectorResearch(sectorId: string): Promise<RotationSectorResearch> {
  const response = await client.get<{ success: boolean; data: RotationSectorResearch }>(
    `/api/rotation/sectors/${sectorId}`,
  )
  return response.data.data
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
  options: {
    screenshot_kind?: 'current_holdings' | 'trade_history'
    parser_provider?: string
    cloud_send_consent?: boolean
    user_notice_acknowledged_at?: string | null
  } = {},
): Promise<PortfolioImportDraft> {
  const form = new FormData()
  form.append('file', file)
  form.append('screenshot_kind', options.screenshot_kind || 'current_holdings')
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

export async function confirmPortfolioImportDraft(
  draftId: string,
  options: { apply_transactions_to_portfolio?: boolean; user_reason?: string } = {},
): Promise<{ draft: PortfolioImportDraft; portfolio: PortfolioState; transaction_batch?: Record<string, any> | null }> {
  const response = await client.post<{
    success: boolean
    data: { draft: PortfolioImportDraft; portfolio: PortfolioState; transaction_batch?: Record<string, any> | null }
  }>(`/api/portfolio/import/drafts/${draftId}/confirm`, {
    apply_transactions_to_portfolio: options.apply_transactions_to_portfolio ?? true,
    user_reason: options.user_reason || null,
  })
  return response.data.data
}

export async function suggestPortfolioTradeReason(draftId: string): Promise<{
  reason_summary: string
  confidence: 'high' | 'medium' | 'low'
  questions: string[]
  model: string
}> {
  const response = await client.post<{ success: boolean; data: any }>(
    `/api/portfolio/import/drafts/${draftId}/suggest-reason`,
    null,
    { timeout: 240000 },
  )
  return response.data.data
}

export async function rejectPortfolioImportDraft(draftId: string): Promise<PortfolioImportDraft> {
  const response = await client.delete<{ success: boolean; data: PortfolioImportDraft }>(`/api/portfolio/import/drafts/${draftId}`)
  return response.data.data
}

export async function getAgentReviewStatus(): Promise<AgentReviewStatus> {
  const response = await client.get<{ success: boolean; data: AgentReviewStatus }>('/api/agent/review/status')
  return response.data.data
}

export async function getLatestAgentReview(): Promise<AgentReviewRun | null> {
  try {
    const response = await client.get<{ success: boolean; data: AgentReviewRun }>('/api/agent/review/latest')
    return response.data.data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function getAgentReviewHistory(limit = 8): Promise<AgentReviewRun[]> {
  const response = await client.get<{ success: boolean; items: AgentReviewRun[] }>(
    '/api/agent/review/history',
    { params: { limit } },
  )
  return response.data.items
}

export async function generateDailyAgentReview(forceContext = false): Promise<AgentReviewRun> {
  const response = await client.post<{ success: boolean; data: AgentReviewRun }>(
    '/api/agent/review/daily',
    null,
    { params: { force_context: forceContext }, timeout: 260000 },
  )
  return response.data.data
}

export async function getAgentReviewTasks(): Promise<AgentReviewTask[]> {
  const response = await client.get<{ success: boolean; items: AgentReviewTask[] }>('/api/agent/review/tasks')
  return response.data.items
}

export async function executeAgentReviewTask(taskId: string): Promise<AgentReviewTask> {
  const response = await client.post<{ success: boolean; data: AgentReviewTask }>(
    `/api/agent/review/tasks/${taskId}/execute`,
    null,
    { timeout: 180000 },
  )
  return response.data.data
}

export async function executePendingAgentReviewTasks(): Promise<AgentReviewTask[]> {
  const response = await client.post<{ success: boolean; items: AgentReviewTask[] }>(
    '/api/agent/review/tasks/execute-pending',
    null,
    { timeout: 240000 },
  )
  return response.data.items
}

export async function updateAgentReviewTaskStatus(
  taskId: string,
  status: 'pending' | 'manual_required' | 'dismissed',
): Promise<AgentReviewTask> {
  const response = await client.patch<{ success: boolean; data: AgentReviewTask }>(
    `/api/agent/review/tasks/${taskId}/status`,
    null,
    { params: { status } },
  )
  return response.data.data
}

export async function runAgentReviewCycle(): Promise<AgentReviewRun> {
  const response = await client.post<{ success: boolean; data: AgentReviewRun }>(
    '/api/agent/review/cycle',
    null,
    { timeout: 360000 },
  )
  return response.data.data
}

export async function getAgentAutomationStatus(): Promise<AgentAutomationStatus> {
  const response = await client.get<{ success: boolean; data: AgentAutomationStatus }>('/api/agent/review/automation')
  return response.data.data
}

export async function saveAgentAutomationSettings(
  payload: Partial<AgentAutomationSettings>,
): Promise<AgentAutomationSettings> {
  const response = await client.put<{ success: boolean; data: AgentAutomationSettings }>(
    '/api/agent/review/automation/settings',
    payload,
  )
  return response.data.data
}

export async function runAgentAutomationNow(): Promise<AgentAutomationRun> {
  const response = await client.post<{ success: boolean; data: AgentAutomationRun }>(
    '/api/agent/review/automation/run',
    null,
    { timeout: 420000 },
  )
  return response.data.data
}

export async function runAgentPremarketNow(): Promise<AgentAutomationRun> {
  const response = await client.post<{ success: boolean; data: AgentAutomationRun }>(
    '/api/agent/review/automation/premarket/run',
    null,
    { timeout: 420000 },
  )
  return response.data.data
}

export async function getAgentOutcomes(): Promise<AgentOutcomes> {
  const response = await client.get<{ success: boolean; data: AgentOutcomes }>(
    '/api/agent/review/outcomes',
    { timeout: 180000 },
  )
  return response.data.data
}

export async function getAgentMonthlyReport(month?: string): Promise<AgentMonthlyReport> {
  const response = await client.get<{ success: boolean; data: AgentMonthlyReport }>(
    '/api/agent/review/outcomes/monthly',
    { params: month ? { month } : undefined },
  )
  return response.data.data
}

export async function getAgentLearningPolicies(): Promise<AgentLearningPolicyRegistry> {
  const response = await client.get<{ success: boolean; data: AgentLearningPolicyRegistry }>(
    '/api/agent/review/learning-policies',
  )
  return response.data.data
}

export async function annotatePortfolioAction(
  actionId: string,
  payload: { confirmed: boolean; reason?: string; dismissed?: boolean },
): Promise<PortfolioActionOutcome> {
  const response = await client.patch<{ success: boolean; data: PortfolioActionOutcome }>(
    `/api/agent/review/outcomes/actions/${encodeURIComponent(actionId)}`,
    payload,
  )
  return response.data.data
}
