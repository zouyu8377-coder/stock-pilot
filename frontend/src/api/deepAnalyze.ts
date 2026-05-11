import axios from 'axios'

const client = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 120000,
})

export interface DeepAnalysisResult {
  trading_bias: string
  trading_advice: string
  win_rate: number
  profit_loss_ratio: number
  risk_level: string
  bull_score: number
  bear_score: number
  key_drivers: string[]
  sector_capital_flow: string
  key_price_levels: string[]
  short_term: string
  medium_term: string
  long_term: string
  industry_analysis: string
  risk_factors: string[]
  summary: string
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