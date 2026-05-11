import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
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

export async function analyzeStock(symbol: string): Promise<AnalyzeResponse> {
  const response = await client.post<AnalyzeResponse>('/api/analyze', {
    symbols: [symbol],
  })
  return response.data
}