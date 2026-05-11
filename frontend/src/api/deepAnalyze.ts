import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
})

export interface PriceLevel {
  price: number
  type: string
  meaning: string
}

export interface TimeframeView {
  view: string
  action: string
}

export interface DeepAnalysisResult {
  // 交易假设与策略
  trade_thesis: string
  trading_bias: string
  strategy_type: string
  trading_advice: string

  // 评分体系
  confidence_score: number
  odds_score: number
  risk_level: string

  // 多空力量
  bull_score: number
  bear_score: number

  // 核心驱动
  key_drivers: string[]

  // 结构化价格位
  key_price_levels: PriceLevel[]

  // 触发条件与失效条件
  invalid_condition: string
  bullish_triggers: string[]
  bearish_triggers: string[]

  // 短中长期
  short_term: TimeframeView | string
  medium_term: TimeframeView | string
  long_term: TimeframeView | string

  // Alpha / Beta
  company_alpha: string
  industry_beta: string
  industry_analysis: string

  // 风险与数据缺口
  risk_factors: string[]
  missing_data: string[]

  // 交易环境
  market_regime: string
  selected_models: string[]

  // 总结
  summary: string

  // 兼容旧字段
  sector_capital_flow?: string
  market_state?: string
  win_rate?: number
  profit_loss_ratio?: number
}

export interface DeepAnalyzeResponse {
  success: boolean
  data?: DeepAnalysisResult
  message?: string
}

export async function deepAnalyze(symbol: string): Promise<DeepAnalyzeResponse> {
  const response = await client.get<DeepAnalyzeResponse>(`/api/deep-analyze/${symbol}`)
  return response.data
}
