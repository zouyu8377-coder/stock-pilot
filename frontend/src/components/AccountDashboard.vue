<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  createPortfolioAnalysisPacket,
  getPortfolioDashboard,
  getPortfolio,
  type PortfolioDashboard,
  type PortfolioState,
} from '../api/client'

const emit = defineEmits<{
  (event: 'select-symbol', symbol: string): void
}>()

const loading = ref(false)
const contextLoading = ref(false)
const packetLoading = ref(false)
const error = ref('')
const notice = ref('')
const state = ref<PortfolioState | null>(null)
const dashboard = ref<PortfolioDashboard | null>(null)
const packetMarkdown = ref('')
const researchMode = ref<'theme' | 'position'>('theme')
const selectedThemeId = ref('')

const fmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const signedFmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value) > 0 ? '+' : ''}${fmt(value, suffix)}`
}

const compactSymbol = (symbol: string) => symbol.split('.', 1)[0].padStart(6, '0')
const activeHoldings = computed(() => (state.value?.snapshot.positions || []).filter((item) => Number(item.quantity || 0) > 0))
const watchlist = computed(() => (state.value?.snapshot.positions || []).filter((item) => Number(item.quantity || 0) === 0))
const holdings = computed(() => dashboard.value?.positions || [...activeHoldings.value, ...watchlist.value])
const account = computed(() => dashboard.value?.account_facts || state.value?.metrics || {})
const dataGaps = computed(() => dashboard.value?.data_gaps || state.value?.metrics.missing_data || [])
const eventRadar = computed(() => dashboard.value?.market_event_radar)
const marketEvents = computed(() => eventRadar.value?.events || [])
const nextMarketEvent = computed(() => eventRadar.value?.next_event)
const themeEvidenceRadar = computed(() => dashboard.value?.theme_evidence_radar)
const themeEvidenceRows = computed(() => themeEvidenceRadar.value?.themes || [])
const attractivenessRadar = computed(() => dashboard.value?.attractiveness_radar)

watch(themeEvidenceRows, (themes) => {
  if (!selectedThemeId.value && themes.length) selectedThemeId.value = themes[0].theme_id
}, { immediate: true })

const selectedTheme = computed(() =>
  themeEvidenceRows.value.find((theme) => theme.theme_id === selectedThemeId.value) || themeEvidenceRows.value[0],
)

const weightBySymbol = computed(() => {
  const map = new Map<string, number>()
  for (const item of state.value?.metrics.position_weights || []) {
    if (item?.symbol) map.set(compactSymbol(item.symbol), Number(item.weight_pct || 0))
  }
  for (const item of dashboard.value?.positions || []) {
    if (item?.symbol && item.portfolio_weight_pct !== null && item.portfolio_weight_pct !== undefined) {
      map.set(compactSymbol(item.symbol), Number(item.portfolio_weight_pct || 0))
    }
  }
  return map
})

const trendBySymbol = computed(() => {
  const map = new Map<string, Record<string, any>>()
  for (const item of dashboard.value?.positions || []) {
    if (item?.symbol) map.set(compactSymbol(item.symbol), item.trend || {})
  }
  return map
})

const riskBySymbol = computed(() => {
  const map = new Map<string, Record<string, any>>()
  for (const item of dashboard.value?.risk_queue || []) map.set(compactSymbol(item.symbol), item)
  return map
})

const opportunityBySymbol = computed(() => {
  const map = new Map<string, Record<string, any>>()
  for (const item of dashboard.value?.opportunity_queue || []) map.set(compactSymbol(item.symbol), item)
  return map
})

const themePositionRows = computed(() => {
  const rows: Array<Record<string, any>> = []
  for (const theme of themeEvidenceRows.value) {
    for (const position of theme.related_positions || []) {
      rows.push({ ...position, theme_id: theme.theme_id, theme_name: theme.theme_name })
    }
  }
  return rows
})

const thesisRows = computed<Array<Record<string, any>>>(() => {
  const strengthRank: Record<string, number> = { high: 3, medium: 2, weak: 1 }
  const best = new Map<string, Record<string, any>>()
  for (const row of themePositionRows.value) {
    const key = compactSymbol(row.symbol)
    const current = best.get(key)
    if (!current || (strengthRank[row.relation_strength] || 0) > (strengthRank[current.relation_strength] || 0)) {
      best.set(key, row)
    }
  }
  return holdings.value
    .map((position): Record<string, any> => {
      const key = compactSymbol(position.symbol)
      const thesis = best.get(key) || {}
      const trend = trendBySymbol.value.get(key) || {}
      return {
        ...position,
        ...thesis,
        symbol: position.symbol,
        name: position.name,
        quantity: position.quantity,
        market_value: position.market_value,
        portfolio_weight_pct: weightBySymbol.value.get(key) || 0,
        trend,
        risk_score: Number(riskBySymbol.value.get(key)?.score || 0),
        opportunity_score: Number(opportunityBySymbol.value.get(key)?.score || 0),
      }
    })
    .sort((a, b) => Number(b.quantity > 0) - Number(a.quantity > 0) || Number(b.portfolio_weight_pct) - Number(a.portfolio_weight_pct))
})

const thesisStatusLabel: Record<string, string> = {
  core_observation: '核心逻辑待验证',
  needs_verification: '关键证据待补',
  weak_relation_needs_verification: '弱关联待核验',
  beta_exposure: '主题 Beta 暴露',
  beta_exposure_needs_verification: 'Beta 关联待核验',
  watchlist_observation: '观察池跟踪',
}

const maturityLabel: Record<string, string> = {
  seed_only: '仅主题种子',
  watching: '观察中',
  thesis_active: 'Thesis 待持续验证',
  thesis_at_risk: 'Thesis 存在反证风险',
  archived: '已归档',
}

const largestTheme = computed(() => themeEvidenceRows.value[0])
const largestPosition = computed(() =>
  [...activeHoldings.value].sort((a, b) => Number(weightBySymbol.value.get(compactSymbol(b.symbol)) || 0) - Number(weightBySymbol.value.get(compactSymbol(a.symbol)) || 0))[0],
)

const evidenceHealth = computed(() => {
  const total = thesisRows.value.length
  const weak = thesisRows.value.filter((row) => !row.theme_id || row.relation_strength === 'weak').length
  return { total, weak, covered: Math.max(total - weak, 0) }
})

const clamp = (value: number, min = 0, max = 100) => Math.min(max, Math.max(min, Math.round(value)))

const themeById = computed(() => new Map(themeEvidenceRows.value.map((theme) => [theme.theme_id, theme])))

const relatedEventsForSymbol = (symbol: string) => {
  const compact = compactSymbol(symbol)
  return marketEvents.value.filter((event) =>
    (event.related_positions || []).some((position: Record<string, any>) => compactSymbol(position.symbol) === compact),
  )
}

const healthForPosition = (row: Record<string, any>) => {
  const theme = themeById.value.get(row.theme_id) as Record<string, any> | undefined
  const verification = row.announcement_verification || {}
  const verificationItems = verification.status === 'verified' ? (verification.items || []) : []
  const supportedCount = verificationItems.filter((item: Record<string, any>) => item.status === 'supported').length
  const partialCount = verificationItems.filter((item: Record<string, any>) => item.status === 'partially_supported').length
  const contradictedCount = verificationItems.filter((item: Record<string, any>) => item.status === 'contradicted').length
  const verifiedQuestionCount = supportedCount + partialCount + contradictedCount
  const relationBase: Record<string, number> = { high: 72, medium: 60, weak: 42 }
  let thesis = relationBase[row.relation_strength] ?? 35
  if (row.thesis_status === 'core_observation') thesis += 8
  if (String(row.thesis_status || '').includes('needs_verification')) thesis -= 5
  if (row.thesis_status === 'beta_exposure') thesis -= 3
  // Relation mappings and research templates alone are not verified operating evidence.
  thesis = Math.min(clamp(thesis), 65)
  thesis = clamp(thesis + supportedCount * 6 + partialCount * 3 - contradictedCount * 14)

  let thesisCoverage = 15
  if (row.theme_id) thesisCoverage += 20
  if (row.role_in_theme) thesisCoverage += 10
  if (row.invalid_condition) thesisCoverage += 10
  if (row.open_questions?.length) thesisCoverage += 10
  if (verification.status === 'verified') {
    thesisCoverage += Math.min(30, verifiedQuestionCount * 10)
  } else {
    thesisCoverage = Math.min(thesisCoverage, 65)
  }

  const trendDataAvailable = row.trend?.data_status === 'available'
  const priceVsMa20 = Number(row.trend?.price_vs_ma20_pct)
  const return20 = Number(row.trend?.return_20d_pct)
  let trend = 55
  if (trendDataAvailable) {
    if (Number.isFinite(priceVsMa20)) trend += Math.max(-20, Math.min(20, priceVsMa20 * 2))
    if (Number.isFinite(return20)) trend += Math.max(-15, Math.min(15, return20 * 0.6))
    const state = String(row.trend?.trend_state || '')
    if (state.includes('强')) trend += 8
    if (state.includes('弱') || state.includes('下方')) trend -= 8
  }
  trend = clamp(trend)
  const trendCoverage = trendDataAvailable ? 100 : 0

  const weight = Number(row.portfolio_weight_pct || 0)
  const themeWeight = Number(theme?.related_position_weight_pct || 0)
  let position = 100
  if (weight > 10) position -= Math.min(35, (weight - 10) * 2.5)
  if (themeWeight > 30) position -= Math.min(35, (themeWeight - 30) * 0.8)
  if ((row.risk_flags || []).includes('HIGH_VOLATILITY')) position -= 10
  position = clamp(position)

  const relatedEvents = relatedEventsForSymbol(row.symbol)
    .filter((event) => Number(event.days_until) >= 0)
    .sort((a, b) => Number(a.days_until) - Number(b.days_until))
  const macroEvent = marketEvents.value
    .filter((event) => Number(event.days_until) >= 0 && String(event.category || '').startsWith('macro_'))
    .sort((a, b) => Number(a.days_until) - Number(b.days_until))[0]
  const nearestEvent = relatedEvents[0] || macroEvent
  let event = 82
  if (nearestEvent) {
    const days = Number(nearestEvent.days_until)
    const impact = Number(nearestEvent.impact_score || 0)
    if (days <= 7) event -= impact * 0.28
    else if (days <= 14) event -= impact * 0.16
    else if (days <= 30) event -= impact * 0.08
  }
  event = clamp(event)
  const eventCoverage = nearestEvent ? 70 : 45

  const score = clamp(thesis * 0.35 + trend * 0.25 + position * 0.25 + event * 0.15)
  const rawCoverage = clamp(thesisCoverage * 0.35 + trendCoverage * 0.25 + 100 * 0.25 + eventCoverage * 0.15)
  const coverage = verification.status === 'verified' ? rawCoverage : Math.min(rawCoverage, 70)
  return {
    score,
    coverage,
    dimensions: [
      { key: 'thesis', label: 'Thesis 健康', score: thesis, weight: 35, coverage: thesisCoverage },
      { key: 'trend', label: '趋势与波动', score: trend, weight: 25, coverage: trendCoverage },
      { key: 'position', label: '仓位与集中度', score: position, weight: 25, coverage: 100 },
      { key: 'event', label: '事件环境', score: event, weight: 15, coverage: eventCoverage },
    ],
    nearestEvent,
    themeWeight,
    legacyRiskScore: Number(row.risk_score || 0),
    verification: {
      status: verification.status || 'unavailable',
      supportedCount,
      partialCount,
      contradictedCount,
      documents: verification.documents || [],
      summary: verification.overall_summary || '',
    },
    boundary: verification.status === 'verified'
      ? '公告结论仅计入已通过原文引用校验的项目。'
      : '关键业务与利润证据尚未完成公告正文验证，Thesis 覆盖率已封顶。',
  }
}

const attractivenessForPosition = (row: Record<string, any>) => {
  const value = row.attractiveness || {}
  return {
    score: value.score ?? null,
    coverage: Number(value.coverage || 0),
    confidence: value.confidence || '中低',
    scoreChange: value.score_change ?? null,
    dimensions: value.dimensions || [],
    topReasons: value.top_reasons || [],
    executionConstraints: value.execution_constraints || {},
    accountConstraints: value.account_constraints || {},
    accountReadiness: Number(value.account_readiness_score || 0),
    portfolioPriority: Number(value.portfolio_priority_score || 0),
    opportunityCost: value.opportunity_cost || {},
    dataHealth: value.data_health || {},
  }
}

const confidenceAssessment = (
  healthCoverage: number,
  attractionCoverage: number,
  hasConflict = false,
) => {
  const jointCoverage = Math.min(healthCoverage, attractionCoverage)
  const blendedCoverage = Math.round(healthCoverage * 0.5 + attractionCoverage * 0.5)
  const reasons: string[] = []
  if (healthCoverage < 85) reasons.push(`健康覆盖仅 ${healthCoverage}%`)
  if (attractionCoverage < 85) reasons.push(`吸引力覆盖仅 ${attractionCoverage}%`)
  if (hasConflict) reasons.push('健康度与吸引力或吸引力各维度存在明显分歧')
  const confidence = jointCoverage >= 85 && blendedCoverage >= 88 && !hasConflict
    ? '高'
    : jointCoverage >= 75 && blendedCoverage >= 80
      ? '中高'
      : jointCoverage >= 60
        ? '中'
        : '中低'
  return { confidence, jointCoverage, blendedCoverage, reasons }
}


const scoreBand = (score?: number | null) => {
  if (score === null || score === undefined || Number.isNaN(Number(score))) return '缺数据'
  const value = Number(score)
  if (value >= 75) return '强'
  if (value >= 60) return '可用'
  if (value >= 45) return '中性'
  return '弱'
}

const scoreTone = (score?: number | null) => {
  if (score === null || score === undefined || Number.isNaN(Number(score))) return 'text-muted-foreground'
  const value = Number(score)
  if (value >= 75) return 'text-positive'
  if (value >= 60) return 'text-sky-200'
  if (value >= 45) return 'text-warning'
  return 'text-negative'
}

const dimensionMeaning = (dimension: Record<string, any>) => {
  const score = dimension.score === null || dimension.score === undefined ? null : Number(dimension.score)
  const key = String(dimension.key || '')
  if (score === null || Number.isNaN(score)) return '缺少可用数据，本项只降低置信度，不给中性分。'
  if (key === 'evidence_change') {
    if (score >= 70) return '证据或预期差正在增强，可提高关注优先级。'
    if (score >= 55) return '已有证据但边际变化有限，支持持有观察，不单独支持加仓。'
    return '证据不足或边际走弱，不能作为新增买入理由。'
  }
  if (key === 'trend_strength') {
    if (score >= 70) return '趋势相对占优，可作为择时加分项。'
    if (score >= 55) return '走势尚可但未形成强确认，适合等待突破或回踩。'
    return '趋势不给力，新增仓位需要更强基本面或事件补偿。'
  }
  if (key === 'valuation_consensus') {
    if (score >= 70) return '价格位置或公开参考具备吸引力，支持提高买入理由强度。'
    if (score >= 55) return '估值不构成明显阻力，但也不是主要加分项。'
    return '估值/价格位置吸引力不足，追价需要谨慎。'
  }
  if (key === 'catalyst') {
    if (score >= 70) return '近期催化或时效性较好，适合重点跟踪触发条件。'
    if (score >= 55) return '催化一般，等待公告、业绩或主题证据更新。'
    return '缺少清晰催化，短期不宜因事件预期加仓。'
  }
  if (key === 'execution') {
    if (score >= 70) return '交易可执行性较好，没有明显涨跌停等硬约束。'
    if (score >= 55) return '可执行性一般，动作需要更严格价格条件。'
    return '存在执行约束，即使逻辑成立也不宜直接动作。'
  }
  return score >= 70 ? '该项明显加分。' : score >= 55 ? '该项中性略正。' : '该项拖累结论。'
}

const actionBreakdownForPosition = (row: Record<string, any>) => {
  const health = Number(row.health?.score || 0)
  const healthCoverage = Number(row.health?.coverage || 0)
  const attraction = row.attractiveness?.score === null || row.attractiveness?.score === undefined ? 0 : Number(row.attractiveness.score)
  const attractionCoverage = Number(row.attractiveness?.coverage || 0)
  const readiness = Number(row.attractiveness?.accountReadiness || 0)
  const weight = Number(row.portfolio_weight_pct || 0)
  const blockers = row.attractiveness?.accountConstraints?.blockers || []
  const execution = row.attractiveness?.executionConstraints || {}
  const hardBlocked = blockers.length > 0 || execution.limit_up || execution.limit_down
  const holdPermit = clamp(health * 0.7 + Math.min(healthCoverage, 100) * 0.3)
  const addPermitRaw = clamp(attraction * 0.52 + readiness * 0.28 + Math.min(attractionCoverage, 100) * 0.2)
  const addPermit = hardBlocked ? Math.min(addPermitRaw, 45) : addPermitRaw
  const riskPressure = clamp((100 - health) * 0.72 + Math.max(0, weight - 10) * 1.2 + (healthCoverage < 55 ? 10 : 0) - (attraction >= 70 ? 8 : 0))
  return [
    {
      label: '持有许可',
      score: holdPermit,
      tone: scoreTone(holdPermit),
      help: holdPermit >= 70 ? '当前逻辑支持继续持有。' : holdPermit >= 55 ? '可持有，但需要观察证据变化。' : '持有理由偏弱，需要提高风险关注。',
    },
    {
      label: '加仓许可',
      score: addPermit,
      tone: scoreTone(addPermit),
      help: addPermit >= 70 ? '具备进入增配候选的基础。' : addPermit >= 55 ? '有观察价值，但还缺少明确触发。' : '暂不支持新增风险敞口。',
    },
    {
      label: '减仓压力',
      score: riskPressure,
      tone: riskPressure >= 70 ? 'text-negative' : riskPressure >= 45 ? 'text-warning' : 'text-positive',
      help: riskPressure >= 70 ? '需要评估降低风险暴露。' : riskPressure >= 45 ? '风险不高但需要跟踪。' : '目前没有明显减仓压力。',
    },
  ]
}

const operationMeaningForPosition = (row: Record<string, any>) => {
  const health = Number(row.health?.score || 0)
  const attraction = row.attractiveness?.score === null || row.attractiveness?.score === undefined ? 0 : Number(row.attractiveness.score)
  const active = Number(row.quantity || 0) > 0
  const action = String(row.conclusion?.action || '')
  if (action.includes('减仓')) return '操作含义：不是机械卖出，而是进入风险复核优先级；若修复信号不足，应考虑降低风险暴露。'
  if (action.includes('利润保护')) return '操作含义：已有收益或趋势贡献较强，但仓位风险也高，重点是保护利润而不是继续追增。'
  if (action.includes('小幅增持')) return '操作含义：接近增持候选，但还缺少更强证据或更好的价格条件。'
  if (row.conclusion?.action?.includes('增配') || row.conclusion?.action?.includes('新增')) {
    return '操作含义：可以进入候选清单，但仍需要价格、事件或账户空间确认，不等于立即买入。'
  }
  if (!active) return '操作含义：仍是观察对象，未同时满足健康度、吸引力和账户约束。'
  if (health < 40) return '操作含义：优先检查是否需要降低风险，而不是寻找加仓理由。'
  if (health >= 55 && attraction < 70) return '操作含义：持有理由尚可，但新增买入理由不足，当前更适合维持仓位。'
  return '操作含义：维持当前仓位，等待证据、趋势或事件触发新的动作。'
}

const decisiveFactorsForPosition = (row: Record<string, any>) => {
  const factors: string[] = []
  factors.push(`健康度 ${row.health.score}/100：${scoreBand(row.health.score)}，决定是否还能安心持有。`)
  factors.push(`吸引力 ${row.attractiveness.score ?? '-'}/100：${scoreBand(row.attractiveness.score)}，决定是否值得新增风险敞口。`)
  const evidence = (row.attractiveness.dimensions || []).find((item: Record<string, any>) => item.key === 'evidence_change')
  if (evidence) factors.push(`证据变化 ${evidence.score ?? '-'}/100：${dimensionMeaning(evidence)}`)
  return factors.slice(0, 3)
}

const hasPositionSignalConflict = (health: Record<string, any>, attractiveness: Record<string, any>) => {
  const dimensionScores = (attractiveness.dimensions || [])
    .map((item: Record<string, any>) => item.score)
    .filter((score: unknown) => score !== null && score !== undefined)
    .map(Number)
  const dimensionSpread = dimensionScores.length
    ? Math.max(...dimensionScores) - Math.min(...dimensionScores)
    : 0
  const healthAttractionGap = attractiveness.score === null
    ? 0
    : Math.abs(Number(health.score || 0) - Number(attractiveness.score || 0))
  return dimensionSpread >= 50 || healthAttractionGap >= 30
}

const conclusionForPosition = (row: Record<string, any>, health: Record<string, any>) => {
  const active = Number(row.quantity || 0) > 0
  const weight = Number(row.portfolio_weight_pct || 0)
  const score = Number(health.score || 0)
  const coverage = Number(health.coverage || 0)
  const attractiveness = attractivenessForPosition(row)
  const attractionScore = attractiveness.score === null ? 0 : Number(attractiveness.score)
  const riskScore = Number(row.risk_score || 0)
  const opportunityScore = Number(row.opportunity_score || 0)
  const trendState = String(row.trend?.trend_state || '')
  const strategyObservation = String(row.trend?.strategy_observation || '')
  const confidenceResult = confidenceAssessment(
    coverage,
    attractiveness.coverage,
    hasPositionSignalConflict(health, attractiveness),
  )
  const { confidence, jointCoverage } = confidenceResult
  const executable = !attractiveness.executionConstraints.limit_up && !attractiveness.executionConstraints.limit_down
  const accountEligible = attractiveness.accountConstraints.eligible_after_account_constraints !== false

  if (score >= 55 && attractionScore >= 70 && attractiveness.coverage >= 55 && accountEligible) {
    return {
      action: active ? '进入增配候选' : '进入新增敞口候选',
      tone: executable
        ? 'border-positive/50 bg-positive/10 text-positive'
        : 'border-warning/50 bg-warning/10 text-warning',
      confidence,
      confidenceReasons: confidenceResult.reasons,
      jointCoverage,
      status: executable ? '双高候选' : '候选但暂不可执行',
      summary: executable
        ? '健康度、吸引力与账户准备度均达到候选门槛，但不构成执行指令。'
        : '健康度与吸引力达标，但涨跌停状态暂时阻断执行。',
      reasons: [
        `健康度 ${score}，吸引力 ${attractionScore}`,
        `账户准备度 ${attractiveness.accountReadiness}`,
        ...attractiveness.topReasons,
      ],
      change: row.invalid_condition || '健康度跌破 55、吸引力跌破 70或出现明确反证时移出候选。',
      rank: 180 + attractionScore + score / 10,
    }
  }

  if (!active) {
    return {
      action: score < 55 && attractionScore >= 70 ? '等待健康度修复' : '继续观察',
      tone: 'border-sky-400/40 bg-sky-400/10 text-sky-100',
      confidence,
      confidenceReasons: confidenceResult.reasons,
      jointCoverage,
      status: score < 55 && attractionScore >= 70 ? '有吸引力但逻辑未确认' : '观察池',
      summary: score < 55 && attractionScore >= 70
        ? '市场与催化信号较强，但持仓逻辑健康度不足，暂不进入新增敞口候选。'
        : '健康度或吸引力尚未同时达到新增敞口门槛。',
      reasons: [`健康度 ${score}，吸引力 ${attractionScore}`, ...attractiveness.topReasons],
      change: row.open_questions?.[0] || '等待健康度达到 55 且吸引力达到 70。',
      rank: 20 + attractionScore,
    }
  }
  if (riskScore >= 6 || (score < 45 && coverage >= 55)) {
    return {
      action: '减仓观察',
      tone: 'border-negative/50 bg-negative/10 text-negative',
      confidence,
      confidenceReasons: confidenceResult.reasons,
      jointCoverage,
      status: riskScore >= 6 ? '风险队列优先' : '健康度偏弱',
      summary: riskScore >= 6
        ? `该标的已进入风险队列，风险分 ${riskScore}。这不是立即卖出指令，但需要优先检查是否降低风险暴露。`
        : '综合健康度偏低且数据覆盖达到最低判断门槛，需要优先复核持仓理由。',
      reasons: [
        `健康度 ${score}，吸引力 ${attractionScore}，风险分 ${riskScore}`,
        strategyObservation || `趋势状态：${trendState || '未形成有效趋势结论'}`,
        ...attractiveness.topReasons,
      ],
      change: `若价格重新站回关键均线、健康度恢复至 55 以上，或${row.invalid_condition || '持仓逻辑未出现明确反证'}，可解除减仓观察；否则继续降级。`,
      rank: 170 + riskScore * 8 - score + weight / 10,
    }
  }
  if (active && riskScore >= 3 && opportunityScore >= 4 && weight >= 15) {
    return {
      action: '利润保护观察',
      tone: 'border-warning/50 bg-warning/10 text-warning',
      confidence,
      confidenceReasons: confidenceResult.reasons,
      jointCoverage,
      status: '高仓位强势持仓',
      summary: '趋势和收益贡献较强，但仓位或主题暴露已经偏高，当前重点不是追增，而是保护已有收益。',
      reasons: [
        `仓位 ${fmt(weight, '%')}，机会分 ${opportunityScore}，风险分 ${riskScore}`,
        strategyObservation || `趋势状态：${trendState || '未形成有效趋势结论'}`,
        ...attractiveness.topReasons,
      ],
      change: row.invalid_condition || '若跌破短期均线、主题证据转弱或风险分继续上升，则从利润保护升级为减仓观察；若回踩确认且账户约束解除，再评估增持。',
      rank: 145 + weight / 3 + opportunityScore,
    }
  }
  if (active && attractionScore >= 60 && attractiveness.coverage >= 55 && attractiveness.accountReadiness >= 60 && weight < 12 && riskScore < 4) {
    return {
      action: '小幅增持观察',
      tone: 'border-positive/50 bg-positive/10 text-positive',
      confidence,
      confidenceReasons: confidenceResult.reasons,
      jointCoverage,
      status: '接近增持候选',
      summary: '吸引力和账户准备度接近增配门槛，但证据或价格条件还不足以给出明确增持建议。',
      reasons: [
        `健康度 ${score}，吸引力 ${attractionScore}，账户准备度 ${attractiveness.accountReadiness}`,
        ...attractiveness.topReasons,
      ],
      change: row.invalid_condition || '吸引力升至 70、证据变化转正，且未触发账户约束时，升级为增持候选。',
      rank: 130 + attractionScore + opportunityScore,
    }
  }
  const status = score >= 75 ? '偏正面' : score >= 55 ? '中性' : '偏弱'
  const tone = score >= 75
      ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200'
      : score >= 55
      ? 'border-sky-400/40 bg-sky-400/10 text-sky-100'
      : 'border-amber-300/50 bg-amber-300/10 text-amber-200'
  return {
    action: score >= 75
      ? '持有，暂不加仓'
      : score >= 55
        ? '中性持有'
        : '弱势持有观察',
    tone,
    confidence,
    confidenceReasons: confidenceResult.reasons,
    jointCoverage,
    status,
    summary: score >= 75
      ? attractionScore >= 55
        ? '持仓逻辑健康，吸引力尚未达到增配候选门槛。'
        : '持仓逻辑健康，但当前新增风险敞口的吸引力不足。'
      : score >= 55
        ? attractionScore >= 55
          ? '健康度与吸引力均为中性，维持当前仓位。'
          : '现有逻辑尚可，但新增风险敞口缺少赔率或催化支持。'
        : '综合状态偏弱，维持仓位同时提高风险关注。',
    reasons: [`健康度 ${score}，吸引力 ${attractionScore}`, ...attractiveness.topReasons],
    change: score < 55
      ? '健康度跌破 40 且覆盖率足够时，升级为降低风险评估。'
      : row.invalid_condition || '健康度显著下降或出现明确反证时降级。',
    rank: score < 55 ? 100 - score + weight / 10 : 70 - score / 10 + weight / 20,
  }
}

const positionConclusions = computed<Array<Record<string, any>>>(() =>
  thesisRows.value
    .map((row) => {
      const health = healthForPosition(row)
      const attractiveness = attractivenessForPosition(row)
      return { ...row, health, attractiveness, conclusion: conclusionForPosition(row, health) }
    })
    .sort((a, b) => b.conclusion.rank - a.conclusion.rank),
)

const activeConclusions = computed(() => positionConclusions.value.filter((row) => Number(row.quantity || 0) > 0))
const holdingConclusions = computed(() =>
  [...positionConclusions.value].sort((a, b) =>
    Number(Number(b.quantity || 0) > 0) - Number(Number(a.quantity || 0) > 0)
    || Number(b.portfolio_weight_pct || 0) - Number(a.portfolio_weight_pct || 0)
    || Number(b.health.score || 0) - Number(a.health.score || 0),
  ),
)
const attractionCandidates = computed(() =>
  positionConclusions.value
    .filter((row) =>
      row.health.score >= 55
      && Number(row.attractiveness.score || 0) >= 70
      && row.attractiveness.coverage >= 55
      && row.attractiveness.accountConstraints.eligible_after_account_constraints !== false
      && row.attractiveness.opportunityCost.preferred_within_theme !== false
    )
    .sort((a, b) =>
      Number(b.attractiveness.accountReadiness) - Number(a.attractiveness.accountReadiness)
      || Number(b.attractiveness.score) - Number(a.attractiveness.score),
    )
    .slice(0, 5),
)

const accountConclusion = computed(() => {
  if (!dashboard.value) return null
  const highRisk = activeConclusions.value.filter((row) => row.health.score < 40 && row.health.coverage >= 55)
  const weakHealth = activeConclusions.value.filter((row) => row.health.score < 55)
  const weightedHealthDenominator = activeConclusions.value.reduce((sum, row) => sum + Number(row.portfolio_weight_pct || 0), 0)
  const weightedHealth = weightedHealthDenominator
    ? Math.round(activeConclusions.value.reduce((sum, row) => sum + Number(row.health.score) * Number(row.portfolio_weight_pct || 0), 0) / weightedHealthDenominator)
    : 0
  const themeWeight = Number(largestTheme.value?.related_position_weight_pct || 0)
  const nearEvent = marketEvents.value.find((event) => Number(event.days_until) >= 0 && Number(event.days_until) <= 7)
  const healthCoverage = weightedHealthDenominator
    ? Math.round(activeConclusions.value.reduce((sum, row) => sum + Number(row.health.coverage) * Number(row.portfolio_weight_pct || 0), 0) / weightedHealthDenominator)
    : 0
  const attractionCoverage = weightedHealthDenominator
    ? Math.round(activeConclusions.value.reduce((sum, row) => sum + Number(row.attractiveness.coverage) * Number(row.portfolio_weight_pct || 0), 0) / weightedHealthDenominator)
    : 0
  const conflictingPositions = activeConclusions.value.filter((row) =>
    hasPositionSignalConflict(row.health, row.attractiveness),
  )
  const confidenceResult = confidenceAssessment(healthCoverage, attractionCoverage, conflictingPositions.length > 0)
  const { confidence, jointCoverage } = confidenceResult
  const averageAttractiveness = weightedHealthDenominator
    ? Math.round(activeConclusions.value.reduce((sum, row) => sum + Number(row.attractiveness.score || 0) * Number(row.portfolio_weight_pct || 0), 0) / weightedHealthDenominator)
    : 0

  if (highRisk.length || weakHealth.length || themeWeight >= 50 || nearEvent) {
    return {
      verdict: attractionCandidates.value.length ? '存在通过账户约束初筛的新增敞口候选' : '暂不扩大整体风险暴露',
      tone: 'border-warning/50 bg-warning/10',
      confidence,
      summary: attractionCandidates.value.length
        ? `当前有 ${attractionCandidates.value.length} 个标的同时满足健康度与吸引力门槛。`
        : '账户当前更适合维持仓位、关注健康度偏弱持仓，并等待重要事件或证据更新。',
      reasons: [
        `持仓加权健康度 ${weightedHealth}；${weakHealth.length} 只持仓低于 55。`,
        `健康覆盖 ${healthCoverage}%，吸引力覆盖 ${attractionCoverage}%，联合覆盖 ${jointCoverage}%。`,
        themeWeight >= 50 ? `最大主题暴露 ${fmt(themeWeight, '%')}，集中度较高。` : `最大主题暴露 ${fmt(themeWeight, '%')}。`,
      ],
      change: '账户加权健康度改善、主题集中度缓解，或关键事件结果形成明确支持证据后，再评估新增风险暴露。',
      weightedHealth,
      averageAttractiveness,
      healthCoverage,
      attractionCoverage,
      jointCoverage,
      confidenceReasons: confidenceResult.reasons,
    }
  }
  return {
    verdict: '整体保持不动',
    tone: 'border-positive/40 bg-positive/10',
    confidence,
    summary: '当前没有足够强的风险或机会信号要求主动调整账户。',
    reasons: [
      '没有持仓进入高风险复核区间。',
      `健康覆盖 ${healthCoverage}%，吸引力覆盖 ${attractionCoverage}%，联合覆盖 ${jointCoverage}%。`,
      `最大主题暴露 ${fmt(themeWeight, '%')}，尚未触发高集中提醒。`,
    ],
    change: '当健康度、主题证据或重要事件结果发生显著变化时重新评估。',
    weightedHealth,
    averageAttractiveness,
    healthCoverage,
    attractionCoverage,
    jointCoverage,
    confidenceReasons: confidenceResult.reasons,
  }
})

const dataQualityItems = computed(() => [
  { label: '数据缺口', value: dataGaps.value.length, tone: dataGaps.value.length ? 'text-warning' : 'text-positive' },
  { label: '弱/未关联标的', value: evidenceHealth.value.weak, tone: evidenceHealth.value.weak ? 'text-warning' : 'text-positive' },
  { label: '主题注册版本', value: themeEvidenceRadar.value?.registry_version || '-', tone: 'text-foreground' },
  { label: '驾驶舱生成时间', value: dashboard.value?.generated_at ? new Date(dashboard.value.generated_at).toLocaleString() : '-', tone: 'text-foreground' },
  { label: '估值数据源', value: attractivenessRadar.value?.data_quality?.valuation_source_status === 'local_free' ? '本地免费口径' : '未配置', tone: attractivenessRadar.value?.data_quality?.valuation_source_status === 'local_free' ? 'text-positive' : 'text-warning' },
  {
    label: '相对强度基准',
    value: attractivenessRadar.value?.benchmark?.status === 'available'
      ? attractivenessRadar.value?.benchmark?.freshness?.status === 'stale'
        ? `已过期 ${attractivenessRadar.value?.benchmark?.freshness?.stale_days || 0} 天`
        : `沪深300 · ${attractivenessRadar.value?.benchmark?.as_of || '-'}`
      : '不可用',
    tone: attractivenessRadar.value?.benchmark?.freshness?.status === 'fresh' ? 'text-positive' : 'text-warning',
  },
  { label: '吸引力验证', value: attractivenessRadar.value?.validation?.status === 'available' ? `${attractivenessRadar.value?.validation?.completed_samples} 样本` : `样本不足 ${attractivenessRadar.value?.validation?.completed_samples || 0}/20`, tone: attractivenessRadar.value?.validation?.status === 'available' ? 'text-positive' : 'text-warning' },
])

const cacheStatusLabel = computed(() => {
  const cache = (dashboard.value as any)?._cache
  if (!cache) return ''
  const status = cache.status === 'hit' ? '缓存命中' : cache.status === 'refresh' ? '强制刷新' : '重新生成'
  const cachedAt = cache.cached_at ? new Date(cache.cached_at).toLocaleTimeString('zh-CN') : ''
  return cachedAt ? `${status} · ${cachedAt}` : status
})

const eventStatusLabel = (event: Record<string, any>) => {
  const days = Number(event.days_until)
  if (days < 0) return `已发布 ${Math.abs(days)} 天`
  if (days === 0) return '今日'
  return `${days} 天后`
}

const eventTone = (level?: string) => {
  if (level === 'high') return 'border-negative/50 bg-negative/10 text-negative'
  if (level === 'medium') return 'border-warning/50 bg-warning/10 text-warning'
  return 'border-border bg-secondary/20 text-muted-foreground'
}

const relationTone = (strength?: string) => {
  if (strength === 'high') return 'text-positive'
  if (strength === 'medium') return 'text-primary'
  return 'text-warning'
}

const openPosition = (symbol?: string) => {
  if (symbol) emit('select-symbol', compactSymbol(symbol))
}

const load = async (force = false) => {
  loading.value = true
  contextLoading.value = false
  error.value = ''
  notice.value = ''
  try {
    contextLoading.value = true
    const [nextState, nextDashboard] = await Promise.all([
      getPortfolio(),
      getPortfolioDashboard(force),
    ])
    state.value = nextState
    dashboard.value = nextDashboard
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '驾驶舱加载失败'
  } finally {
    loading.value = false
    contextLoading.value = false
  }
}

const generatePacket = async () => {
  packetLoading.value = true
  notice.value = ''
  try {
    const result = await createPortfolioAnalysisPacket()
    packetMarkdown.value = result.markdown
    dashboard.value = await getPortfolioDashboard()
    notice.value = '已刷新组合证据包和驾驶舱数据。'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '组合证据包生成失败'
  } finally {
    packetLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-foreground">账户决策工作台</h1>
        <p class="mt-1 text-xs text-muted-foreground">先识别需要处理的判断变化，再进入主题、持仓和证据详情。</p>
        <p v-if="cacheStatusLabel" class="mt-1 text-xs text-muted-foreground">{{ cacheStatusLabel }}</p>
      </div>
      <div class="flex gap-2 text-xs">
        <button class="h-9 rounded bg-secondary px-3 text-foreground" :disabled="loading" @click="load(true)">刷新</button>
        <button class="h-9 rounded bg-primary px-3 text-primary-foreground" :disabled="packetLoading" @click="generatePacket">
          {{ packetLoading ? '生成中...' : '刷新证据包' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="rounded border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{{ error }}</div>
    <div v-if="notice" class="rounded border border-positive/40 bg-positive/10 p-3 text-sm text-positive">{{ notice }}</div>
    <div v-if="loading" class="rounded border border-border bg-card p-4 text-sm text-muted-foreground">驾驶舱加载中...</div>
    <div v-else-if="contextLoading" class="rounded border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
      正在汇总趋势、主题、事件和持仓 Thesis。
    </div>

    <template v-if="!loading && state">
      <div class="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3 text-sm">
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">当前估算总资产</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ fmt(account.total_assets) }}</div>
          <div :class="['mt-1', Number(account.current_holding_unrealized_pnl || 0) >= 0 ? 'text-negative' : 'text-positive']">
            持仓 {{ signedFmt(account.current_holding_unrealized_pnl_pct, '%') }}
          </div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">仓位 / 现金</div>
          <div class="mt-2 font-mono text-lg font-semibold">{{ fmt(account.invested_ratio_pct, '%') }}</div>
          <div class="mt-1 text-muted-foreground">现金 {{ fmt(account.cash_ratio_pct, '%') }}</div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">最大主题暴露</div>
          <div class="mt-2 truncate text-sm font-semibold">{{ largestTheme?.theme_name || '-' }}</div>
          <div class="mt-1 font-mono text-warning">{{ fmt(largestTheme?.related_position_weight_pct, '%') }}</div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">最大单只持仓</div>
          <div class="mt-2 truncate text-sm font-semibold">{{ largestPosition?.name || '-' }}</div>
          <div class="mt-1 font-mono">{{ fmt(largestPosition ? weightBySymbol.get(compactSymbol(largestPosition.symbol)) : null, '%') }}</div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">账户加权健康度</div>
          <div class="mt-2 font-mono text-lg font-semibold text-warning">{{ accountConclusion?.weightedHealth ?? '-' }}</div>
          <div class="mt-1 text-muted-foreground">联合覆盖 {{ accountConclusion?.jointCoverage ?? '-' }}%</div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">平均吸引力</div>
          <div class="mt-2 font-mono text-lg font-semibold text-sky-300">{{ accountConclusion?.averageAttractiveness ?? '-' }}</div>
          <div class="mt-1 text-muted-foreground">候选 {{ attractionCandidates.length }} 个</div>
        </div>
        <div class="min-h-24 rounded border border-border bg-card p-3">
          <div class="text-muted-foreground">下一个重要事件</div>
          <div class="mt-2 truncate text-sm font-semibold">{{ nextMarketEvent?.title || '-' }}</div>
          <div class="mt-1 text-warning">{{ nextMarketEvent ? eventStatusLabel(nextMarketEvent) : '暂无' }}</div>
        </div>
      </div>

      <div v-if="accountConclusion" :class="['rounded border p-4', accountConclusion.tone]">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="text-xs text-muted-foreground">今日账户结论</div>
            <h2 class="mt-1 text-xl font-semibold text-foreground">{{ accountConclusion.verdict }}</h2>
            <p class="mt-2 text-sm text-muted-foreground">{{ accountConclusion.summary }}</p>
          </div>
          <div class="rounded border border-border/70 bg-card/60 px-3 py-2 text-center text-xs">
            <div class="text-muted-foreground">置信度</div>
            <div class="mt-1 font-semibold text-foreground">{{ accountConclusion.confidence }}</div>
            <div class="mt-1 font-mono text-muted-foreground">联合覆盖 {{ accountConclusion.jointCoverage }}%</div>
            <div class="mt-1 text-muted-foreground">健康 {{ accountConclusion.healthCoverage }}% · 吸引力 {{ accountConclusion.attractionCoverage }}%</div>
          </div>
        </div>
        <div v-if="accountConclusion.confidenceReasons.length" class="mt-3 text-xs leading-5 text-warning">
          置信度限制：{{ accountConclusion.confidenceReasons.join('；') }}
        </div>
        <div class="mt-4 grid gap-2 text-xs md:grid-cols-3">
          <div v-for="reason in accountConclusion.reasons" :key="reason" class="rounded bg-card/50 p-2 text-muted-foreground">{{ reason }}</div>
        </div>
        <div class="mt-3 border-t border-border/60 pt-3 text-xs">
          <span class="font-medium text-foreground">改变结论的条件：</span>
          <span class="text-muted-foreground">{{ accountConclusion.change }}</span>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <div class="rounded border border-border bg-card">
          <div class="border-b border-border px-3 py-2">
            <h2 class="text-sm font-semibold">全部持仓结论（按持仓比例）</h2>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">仓位越大，对账户影响越大；观察池标的排在持仓之后。</p>
          </div>
          <div class="divide-y divide-border/60">
            <button v-for="row in holdingConclusions" :key="`holding-${row.symbol}`" class="w-full p-3 text-left hover:bg-secondary/20" @click="openPosition(row.symbol)">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div class="font-medium text-foreground">{{ row.name || row.symbol }}</div>
                  <div class="mt-1 font-mono text-xs text-slate-300">
                    {{ row.symbol }} · 权重 {{ fmt(row.portfolio_weight_pct, '%') }}
                    <span v-if="Number(row.quantity || 0) === 0" class="ml-2 text-warning">观察池</span>
                  </div>
                </div>
                <div class="grid min-w-[252px] grid-cols-3 gap-2 text-center">
                  <div class="rounded border border-slate-500/50 bg-background/60 px-2 py-2">
                    <div class="font-mono text-xl font-semibold text-foreground">{{ row.health.score }}</div>
                    <div class="mt-1 text-xs font-medium text-slate-300">健康度</div>
                  </div>
                  <div class="rounded border border-sky-400/40 bg-sky-400/10 px-2 py-2">
                    <div class="font-mono text-xl font-semibold text-sky-200">{{ row.attractiveness.score ?? '-' }}</div>
                    <div class="mt-1 text-xs font-medium text-sky-200">
                      吸引力
                      <span v-if="row.attractiveness.scoreChange !== null" :class="['mt-1 block whitespace-nowrap text-xs', Number(row.attractiveness.scoreChange) >= 0 ? 'text-emerald-300' : 'text-rose-300']">
                        · 较上次 {{ signedFmt(row.attractiveness.scoreChange) }}
                      </span>
                    </div>
                  </div>
                  <div class="rounded border border-emerald-400/40 bg-emerald-400/10 px-2 py-2">
                    <div class="font-mono text-xl font-semibold text-emerald-200">{{ row.attractiveness.accountReadiness }}</div>
                    <div class="mt-1 text-xs font-medium text-emerald-200">准备度</div>
                  </div>
                </div>
              </div>
              <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
                <span :class="['inline-flex shrink-0 items-center rounded border bg-background/50 px-2.5 py-1.5 text-sm font-semibold', row.conclusion.tone]">{{ row.conclusion.action }}</span>
                <span class="min-w-0 text-sm leading-5 text-slate-300">状态：{{ row.conclusion.status }} · 置信度 {{ row.conclusion.confidence }}</span>
              </div>
              <p class="mt-2 text-sm leading-6 text-slate-300">{{ row.conclusion.summary }}</p>
              <p class="mt-1 text-sm leading-6 text-foreground">{{ operationMeaningForPosition(row) }}</p>
              <div class="mt-3 grid gap-2 sm:grid-cols-3">
                <div v-for="item in actionBreakdownForPosition(row)" :key="`${row.symbol}-action-${item.label}`" class="rounded border border-border/80 bg-background/40 p-2">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-muted-foreground">{{ item.label }}</span>
                    <span :class="['font-mono text-lg font-semibold', item.tone]">{{ item.score }}</span>
                  </div>
                  <div class="mt-1 text-xs leading-5 text-slate-300">{{ item.help }}</div>
                </div>
              </div>
              <div class="mt-3 grid gap-2 text-left sm:grid-cols-2 xl:grid-cols-3">
                <div v-for="factor in decisiveFactorsForPosition(row)" :key="`${row.symbol}-factor-${factor}`" class="rounded border border-border/70 bg-secondary/10 p-2 text-xs leading-5 text-slate-300">
                  {{ factor }}
                </div>
              </div>
              <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
                <div v-for="dimension in row.attractiveness.dimensions" :key="`${row.symbol}-attraction-${dimension.key}`" class="flex min-h-28 flex-col justify-between rounded border border-border/80 bg-background/40 px-2 py-2">
                  <div class="text-xs leading-4 text-slate-300">{{ dimension.label }} · 权重 {{ dimension.weight }}%</div>
                  <div :class="['mt-1 font-mono text-base font-semibold', scoreTone(dimension.score)]">{{ dimension.score ?? '缺数据' }}<span v-if="dimension.score !== null && dimension.score !== undefined" class="text-xs font-normal text-muted-foreground">/100</span></div>
                  <div class="mt-1 text-xs leading-5 text-muted-foreground">{{ dimensionMeaning(dimension) }}</div>
                </div>
              </div>
              <div class="mt-2 text-xs leading-5 text-muted-foreground">
                健康覆盖 {{ row.health.coverage }}% · 吸引力覆盖 {{ row.attractiveness.coverage }}% · 联合覆盖 {{ row.conclusion.jointCoverage }}% · {{ row.conclusion.confidence }}置信度
              </div>
              <div v-if="row.conclusion.confidenceReasons.length" class="mt-1 text-xs leading-5 text-warning">
                置信度限制：{{ row.conclusion.confidenceReasons.join('；') }}
              </div>
              <div v-if="row.attractiveness.accountConstraints.blockers?.length" class="mt-1 text-xs leading-5 text-warning">
                账户约束：{{ row.attractiveness.accountConstraints.blockers.join('；') }}
              </div>
              <div v-if="row.attractiveness.opportunityCost.dominated_by_symbol" class="mt-1 text-xs leading-5 text-warning">
                机会成本：同主题优先级低于 {{ row.attractiveness.opportunityCost.dominated_by_name || row.attractiveness.opportunityCost.dominated_by_symbol }}，差 {{ row.attractiveness.opportunityCost.priority_gap }} 分。
              </div>
              <div v-if="row.health.boundary" class="mt-1 text-xs leading-5 text-muted-foreground">{{ row.health.boundary }}</div>
              <div v-if="row.health.verification.status === 'verified'" class="mt-1 text-xs leading-5 text-muted-foreground">
                公告验证：支持 {{ row.health.verification.supportedCount }} · 部分支持 {{ row.health.verification.partialCount }} · 反证 {{ row.health.verification.contradictedCount }}
              </div>
              <div class="mt-2 border-t border-border/50 pt-2 text-xs leading-5 text-warning">改变条件：{{ row.conclusion.change }}</div>
            </button>
            <div v-if="!holdingConclusions.length" class="p-4 text-sm text-muted-foreground">暂无持仓或观察池标的。</div>
          </div>
        </div>

        <div class="rounded border border-border bg-card">
          <div class="border-b border-border px-3 py-2">
            <h2 class="text-sm font-semibold">新增风险敞口候选</h2>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">健康度不低于 55、吸引力不低于 70且覆盖达到门槛；仍需检查账户空间和执行限制。</p>
          </div>
          <div class="space-y-2 p-3">
            <button v-for="row in attractionCandidates" :key="`candidate-${row.symbol}`" class="w-full rounded border border-positive/30 bg-positive/5 p-2 text-left hover:bg-positive/10" @click="openPosition(row.symbol)">
              <div class="flex items-center justify-between gap-2">
                <span class="font-medium text-foreground">{{ row.name || row.symbol }}</span>
                <span class="font-mono text-sm text-positive">{{ row.health.score }} / {{ row.attractiveness.score }} / {{ row.attractiveness.accountReadiness }} / {{ row.attractiveness.portfolioPriority }}</span>
              </div>
              <div class="mt-1 text-xs leading-5 text-muted-foreground">
                健康 / 吸引力 / 准备度 / 组合优先 · {{ row.conclusion.action }} · 吸引力覆盖 {{ row.attractiveness.coverage }}%
              </div>
              <div class="mt-1 text-xs leading-5 text-muted-foreground">{{ row.attractiveness.topReasons.join('；') }}</div>
            </button>
            <div v-if="!attractionCandidates.length" class="text-xs text-muted-foreground">当前没有同时满足健康度、吸引力和覆盖门槛的标的。</div>
          </div>
        </div>
      </div>

      <details class="rounded border border-border bg-card">
        <summary class="cursor-pointer px-3 py-3 text-sm font-medium text-foreground">
          查看主题与持仓判断依据
          <span class="ml-2 text-xs font-normal text-muted-foreground">四张证据表与完整 Thesis 明细</span>
        </summary>
        <div class="border-t border-border">
      <div>
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2">
          <div>
            <h2 class="text-sm font-semibold">研究工作区</h2>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">主题视角回答账户在押注什么，持仓视角回答为什么继续跟踪。</p>
          </div>
          <div class="flex rounded bg-secondary/40 p-1 text-xs">
            <button :class="['rounded px-3 py-1.5', researchMode === 'theme' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground']" @click="researchMode = 'theme'">主题研究</button>
            <button :class="['rounded px-3 py-1.5', researchMode === 'position' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground']" @click="researchMode = 'position'">单只持仓</button>
          </div>
        </div>

        <div v-if="researchMode === 'theme'" class="grid min-h-[520px] lg:grid-cols-[330px_minmax(0,1fr)]">
          <div class="border-b border-border p-3 lg:border-b-0 lg:border-r">
            <div class="mb-2 text-xs font-medium text-muted-foreground">账户相关主题表</div>
            <button
              v-for="theme in themeEvidenceRows"
              :key="theme.theme_id"
              :class="['mb-2 w-full rounded border p-3 text-left', selectedTheme?.theme_id === theme.theme_id ? 'border-primary/60 bg-primary/10' : 'border-border/70 bg-secondary/10 hover:bg-secondary/30']"
              @click="selectedThemeId = theme.theme_id"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="truncate font-medium text-foreground">{{ theme.theme_name }}</div>
                  <div class="mt-1 text-xs text-muted-foreground">{{ maturityLabel[theme.evidence_maturity] || theme.evidence_maturity }}</div>
                </div>
                <span class="font-mono text-primary">{{ theme.portfolio_relevance_score }}</span>
              </div>
              <div class="mt-3 flex items-center justify-between text-xs">
                <span class="text-muted-foreground">相关权重</span>
                <span class="font-mono text-warning">{{ fmt(theme.related_position_weight_pct, '%') }}</span>
              </div>
              <div class="mt-2 flex flex-wrap gap-1">
                <span v-for="position in theme.related_positions?.slice(0, 4) || []" :key="`${theme.theme_id}-${position.symbol}`" class="rounded bg-secondary/60 px-1.5 py-0.5 text-xs text-slate-300">
                  {{ position.name || position.symbol }}
                </span>
              </div>
            </button>
            <div v-if="!themeEvidenceRows.length" class="rounded bg-secondary/20 p-3 text-xs text-muted-foreground">暂无账户相关主题。</div>
          </div>

          <div v-if="selectedTheme" class="space-y-4 p-3">
            <div class="rounded border border-border/70 bg-secondary/10 p-3">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-foreground">{{ selectedTheme.theme_name }}</h3>
                  <p class="mt-1 max-w-3xl text-xs text-muted-foreground">{{ selectedTheme.description }}</p>
                </div>
                <div class="text-right text-xs">
                  <div class="text-muted-foreground">账户相关分</div>
                  <div class="mt-1 font-mono text-xl font-semibold text-primary">{{ selectedTheme.portfolio_relevance_score }}</div>
                </div>
              </div>
              <p class="mt-3 text-xs text-muted-foreground">{{ selectedTheme.portfolio_readout }}</p>
            </div>

            <div>
              <div class="mb-2 text-xs font-medium text-muted-foreground">产业链层级表</div>
              <div class="overflow-x-auto rounded border border-border/70">
                <table class="w-full min-w-[760px] text-xs">
                  <thead class="bg-secondary/30 text-muted-foreground">
                    <tr><th class="px-3 py-2 text-left">层级</th><th class="px-3 py-2 text-left">物理约束</th><th class="px-3 py-2 text-left">待核验问题</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="layer in selectedTheme.chain_layers || []" :key="layer.layer_id" class="border-t border-border/60 align-top">
                      <td class="px-3 py-2 font-medium text-foreground">{{ layer.layer_name }}</td>
                      <td class="px-3 py-2 text-muted-foreground">{{ layer.physical_constraint }}</td>
                      <td class="px-3 py-2 text-muted-foreground">{{ (layer.evidence_questions || []).join('；') }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <div class="mb-2 text-xs font-medium text-muted-foreground">催化 / 反证事件表</div>
              <div class="grid gap-3 md:grid-cols-2">
                <div class="rounded border border-positive/30 bg-positive/5 p-3">
                  <div class="text-xs font-medium text-positive">确认信号</div>
                  <ul class="mt-2 space-y-2 text-xs text-muted-foreground">
                    <li v-for="event in selectedTheme.confirming_events || []" :key="event">· {{ event }}</li>
                  </ul>
                </div>
                <div class="rounded border border-warning/40 bg-warning/5 p-3">
                  <div class="text-xs font-medium text-warning">反证信号</div>
                  <ul class="mt-2 space-y-2 text-xs text-muted-foreground">
                    <li v-for="event in selectedTheme.invalidating_events || []" :key="event">· {{ event }}</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[1100px] table-fixed text-xs">
            <colgroup>
              <col class="w-[160px]" />
              <col class="w-[150px]" />
              <col class="w-[180px]" />
              <col class="w-[150px]" />
              <col class="w-[250px]" />
              <col class="w-[250px]" />
              <col class="w-[100px]" />
              <col class="w-[120px]" />
            </colgroup>
            <thead class="bg-secondary/30 text-muted-foreground">
              <tr>
                <th class="px-3 py-2 text-left">标的 / 仓位</th>
                <th class="px-3 py-2 text-left">相关主题</th>
                <th class="px-3 py-2 text-left">产业链角色</th>
                <th class="px-3 py-2 text-left">Thesis 状态</th>
                <th class="px-3 py-2 text-left">下一项待核验</th>
                <th class="px-3 py-2 text-left">失效条件</th>
                <th class="px-3 py-2 text-right">健康度 / 覆盖率</th>
                <th class="px-3 py-2 text-right">吸引力 / 覆盖率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in thesisRows" :key="row.symbol" class="cursor-pointer border-t border-border/60 align-top hover:bg-secondary/20" @click="openPosition(row.symbol)">
                <td class="px-3 py-2">
                  <div class="font-medium text-foreground">{{ row.name || row.symbol }}</div>
                  <div class="mt-1 font-mono text-muted-foreground">{{ row.symbol }} · {{ fmt(row.portfolio_weight_pct, '%') }}</div>
                  <div v-if="Number(row.quantity || 0) === 0" class="mt-1 text-warning">观察池</div>
                </td>
                <td class="px-3 py-2 text-muted-foreground">{{ row.theme_name || '待建立主题关系' }}</td>
                <td class="px-3 py-2 text-muted-foreground">{{ row.role_in_theme || '产业链角色待核验' }}</td>
                <td class="px-3 py-2">
                  <div :class="relationTone(row.relation_strength)">{{ thesisStatusLabel[row.thesis_status] || row.thesis_status || '证据不足' }}</div>
                  <div class="mt-1 text-muted-foreground">{{ row.relation_label || '待核验' }}</div>
                </td>
                <td class="px-3 py-2 text-muted-foreground">{{ row.open_questions?.[0] || '补齐主营、财务或公告证据。' }}</td>
                <td class="px-3 py-2 text-muted-foreground">{{ row.invalid_condition || '尚未建立可验证的失效条件。' }}</td>
                <td class="px-3 py-2 text-right">
                  <div class="font-mono text-base text-foreground">{{ healthForPosition(row).score }} / {{ healthForPosition(row).coverage }}%</div>
                  <div class="mt-1 text-muted-foreground">旧提醒分仅留作审计</div>
                </td>
                <td class="px-3 py-2 text-right">
                  <div class="font-mono text-base text-primary">{{ attractivenessForPosition(row).score ?? '-' }} / {{ attractivenessForPosition(row).coverage }}%</div>
                  <div class="mt-1 text-muted-foreground">{{ attractivenessForPosition(row).confidence }}置信度</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
        </div>
      </details>

      <details class="rounded border border-border bg-card">
        <summary class="cursor-pointer px-3 py-3 text-sm font-medium text-foreground">
          查看事件、数据质量与系统边界
          <span class="ml-2 text-xs font-normal text-muted-foreground">{{ marketEvents.length }} 个事件 · {{ dataGaps.length }} 个数据缺口</span>
        </summary>
      <div class="grid gap-4 border-t border-border xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <div class="rounded border border-border bg-card">
          <div class="flex items-center justify-between border-b border-border px-3 py-2">
            <div>
              <h2 class="text-sm font-semibold">事件与账户影响</h2>
              <p class="mt-1 text-xs leading-5 text-muted-foreground">事件发生后仍需回填结果，当前只表示可能的影响路径。</p>
            </div>
            <span class="rounded bg-secondary/40 px-2 py-1 text-xs text-slate-300">{{ eventRadar?.window_days || 45 }} 天窗口</span>
          </div>
          <div class="grid gap-3 p-3 md:grid-cols-2">
            <div v-for="event in marketEvents.slice(0, 6)" :key="event.event_id" class="rounded border border-border/70 bg-secondary/10 p-3 text-xs">
              <div class="flex items-start justify-between gap-2">
                <div>
                  <div class="font-medium text-foreground">{{ event.title }}</div>
                  <div class="mt-1 text-muted-foreground">{{ event.date }} · {{ eventStatusLabel(event) }}</div>
                </div>
                <span :class="['rounded border px-2 py-1 font-mono text-xs', eventTone(event.impact_level)]">{{ event.impact_score }}</span>
              </div>
              <p class="mt-2 text-muted-foreground">{{ event.portfolio_readout }}</p>
              <div v-if="event.related_positions?.length" class="mt-2 flex flex-wrap gap-1">
                <span v-for="position in event.related_positions.slice(0, 4)" :key="`${event.event_id}-${position.symbol}`" class="rounded bg-secondary/60 px-1.5 py-0.5 font-mono text-xs text-slate-300">
                  {{ position.symbol }} {{ fmt(position.portfolio_weight_pct, '%') }}
                </span>
              </div>
            </div>
            <div v-if="!marketEvents.length" class="text-xs text-muted-foreground">未来窗口内暂无已配置事件。</div>
          </div>
        </div>

        <div class="rounded border border-border bg-card">
          <div class="border-b border-border px-3 py-2">
            <h2 class="text-sm font-semibold">数据质量与边界</h2>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">数据不足时降级为待核验，不生成确定动作。</p>
          </div>
          <div class="grid grid-cols-2 gap-2 p-3 text-xs">
            <div v-for="item in dataQualityItems" :key="item.label" class="rounded bg-secondary/20 p-2">
              <div class="text-muted-foreground">{{ item.label }}</div>
              <div :class="['mt-1 break-words font-mono', item.tone]">{{ item.value }}</div>
            </div>
          </div>
          <div class="border-t border-border px-3 py-3 text-xs">
            <div class="mb-2 font-medium text-foreground">主要数据缺口</div>
            <div class="space-y-2 text-muted-foreground">
              <p v-for="(gap, idx) in dataGaps.slice(0, 6)" :key="idx">
                {{ typeof gap === 'string' ? gap : `${gap.symbol ? gap.symbol + ' · ' : ''}${gap.key || '数据缺口'}：${gap.reason || gap.raw_reason || '-'}` }}
              </p>
              <p v-if="!dataGaps.length" class="text-positive">当前未发现已登记的数据缺口。</p>
            </div>
          </div>
        </div>
      </div>
      </details>

      <div class="rounded border border-border bg-card">
        <details>
          <summary class="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">账户明细与原始证据包</summary>
          <div class="grid gap-3 border-t border-border p-3 lg:grid-cols-2">
            <div>
              <div class="mb-2 text-xs font-medium text-foreground">持仓与观察池</div>
              <div class="max-h-72 overflow-auto rounded border border-border/70">
                <button v-for="position in thesisRows" :key="`detail-${position.symbol}`" class="flex w-full items-center justify-between gap-3 border-b border-border/50 px-3 py-2 text-left text-xs last:border-0 hover:bg-secondary/20" @click="openPosition(position.symbol)">
                  <span><span class="font-medium text-foreground">{{ position.name || position.symbol }}</span><span class="ml-2 font-mono text-muted-foreground">{{ position.symbol }}</span></span>
                  <span class="font-mono text-muted-foreground">{{ fmt(position.portfolio_weight_pct, '%') }}</span>
                </button>
              </div>
            </div>
            <div>
              <div class="mb-2 text-xs font-medium text-foreground">最近生成的组合证据包</div>
              <pre v-if="packetMarkdown" class="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-3 text-xs">{{ packetMarkdown }}</pre>
              <div v-else class="rounded border border-border/70 p-3 text-xs text-muted-foreground">点击“刷新证据包”后可在这里查看完整 Markdown。</div>
            </div>
          </div>
        </details>
      </div>

      <p class="text-xs leading-5 text-muted-foreground">
        {{ themeEvidenceRadar?.boundary }} {{ eventRadar?.boundary }}
      </p>
    </template>
  </section>
</template>
