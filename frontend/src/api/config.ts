const currentHost = typeof window === 'undefined' ? '127.0.0.1' : window.location.hostname

export const API_BASE_STORAGE_KEY = 'stock-pilot.api-base-url'
export const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${currentHost}:8000`

export const normalizeApiBaseUrl = (value: string): string => {
  const input = value.trim()
  if (!input) throw new Error('请输入 API 端口或完整地址')

  const portMatch = input.match(/^:?(\d{1,5})$/)
  const candidate = portMatch ? `http://${currentHost}:${portMatch[1]}` : input
  const parsed = new URL(candidate)
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('API 地址仅支持 http 或 https')
  }
  if (portMatch) {
    const port = Number(portMatch[1])
    if (port < 1 || port > 65535) throw new Error('端口必须在 1 到 65535 之间')
  }
  return candidate.replace(/\/+$/, '')
}

const storedApiBaseUrl = (() => {
  if (typeof window === 'undefined') return ''
  try {
    const stored = window.localStorage.getItem(API_BASE_STORAGE_KEY)
    return stored ? normalizeApiBaseUrl(stored) : ''
  } catch {
    return ''
  }
})()

export const API_BASE_URL = storedApiBaseUrl || DEFAULT_API_BASE_URL

export const saveApiBaseUrl = (value: string): string => {
  const normalized = normalizeApiBaseUrl(value)
  window.localStorage.setItem(API_BASE_STORAGE_KEY, normalized)
  return normalized
}

export const resetApiBaseUrl = () => {
  window.localStorage.removeItem(API_BASE_STORAGE_KEY)
}

export const API_BASE_LABEL = API_BASE_URL
  .replace(`http://${currentHost}:`, ':')
  .replace('http://127.0.0.1:', ':')
  .replace('http://localhost:', ':')
