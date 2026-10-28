import type { AgentReviewItem, RotationSector } from '../api/client'

const code = (value: string) => value.match(/\d{6}/)?.[0] || value
const title = (value: string) => value.replace(/板块|潜在机会|早期机会|方向|\s/g, '').toLowerCase()

export function sectorIdentity(item: AgentReviewItem, sectors: RotationSector[]): string {
  const refs = item.evidence_refs || []
  const linked = sectors.find(sector => refs.includes(`rotation:${sector.sector_id}`))
    || sectors.find(sector => title(item.subject) === title(sector.name))
    || sectors.find(sector => (item.target_symbols || []).some(symbol =>
      [sector.primary_symbol, sector.selected_symbol, ...(sector.proxy_components || []).map(p => p.symbol)]
        .some(proxy => proxy && code(proxy) === code(symbol))))
  return linked ? `sector:${linked.sector_id}` : `subject:${title(item.subject)}`
}

export function uniqueModelOpportunities(items: AgentReviewItem[], sectors: RotationSector[]): AgentReviewItem[] {
  const seen = new Set<string>()
  return items.filter(item => {
    const key = sectorIdentity(item, sectors)
    if (seen.has(key)) return false
    seen.add(key); return true
  })
}
