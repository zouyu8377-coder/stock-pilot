export interface SearchHistoryItem {
  symbol: string
  name: string
  lastViewed: number
  count: number
}

const STORAGE_KEY = 'stock-pilot-search-history'
const MAX_ITEMS = 30

export function getSearchHistory(): SearchHistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const list: SearchHistoryItem[] = JSON.parse(raw)
    if (!Array.isArray(list)) return []
    return list.sort((a, b) => {
      if (b.lastViewed !== a.lastViewed) {
        return b.lastViewed - a.lastViewed
      }
      return b.count - a.count
    })
  } catch {
    return []
  }
}

export function updateSearchHistory(item: { symbol: string; name: string }): void {
  const list = getSearchHistory()
  const existing = list.find((x) => x.symbol === item.symbol)

  if (existing) {
    existing.name = item.name
    existing.count += 1
    existing.lastViewed = Date.now()
  } else {
    list.push({
      symbol: item.symbol,
      name: item.name,
      lastViewed: Date.now(),
      count: 1,
    })
  }

  const trimmed = list
    .sort((a, b) => {
      if (b.lastViewed !== a.lastViewed) {
        return b.lastViewed - a.lastViewed
      }
      return b.count - a.count
    })
    .slice(0, MAX_ITEMS)

  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
}
