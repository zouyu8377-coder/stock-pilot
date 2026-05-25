<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  confirmPortfolioImportDraft,
  createPortfolioAnalysisPacket,
  getPortfolio,
  getPortfolioImportParserProviders,
  getPortfolioSnapshot,
  rejectPortfolioImportDraft,
  savePortfolio,
  updatePortfolioImportDraft,
  uploadPortfolioScreenshot,
  type PortfolioImportDraft,
  type PortfolioState,
} from '../api/client'

const expanded = ref(false)
const loading = ref(false)
const saving = ref(false)
const importLoading = ref(false)
const parserStatus = ref<any | null>(null)
const state = ref<PortfolioState | null>(null)
const draft = ref<PortfolioImportDraft | null>(null)
const selectedFile = ref<File | null>(null)
const selectedPreview = ref('')
const importError = ref('')
const parserProvider = ref('local_noop')
const snapshotPreview = ref('')
const snapshotNotice = ref('')
const packetMarkdown = ref('')
const packetJson = ref('')
const packetCopied = ref(false)
const packetLoading = ref(false)

const accountDraft = ref({
  cash_available: 0,
  repo_amount: 0,
  total_assets: null as number | null,
  max_position_weight: 35,
  max_theme_weight: 50,
  min_cash_ratio: 5,
})

const positionDraft = ref({
  symbol: '',
  name: '',
  quantity: 0,
  available_quantity: null as number | null,
  avg_cost: 0,
  position_role: 'observation',
  primary_theme: '',
  theme_tags_text: '',
  user_plan: '',
  invalid_condition: '',
  target_max_weight: null as number | null,
})

const fmt = (v?: number | null, suffix = '') => {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const positions = computed(() => state.value?.snapshot.positions || [])
const metrics = computed(() => state.value?.metrics)
const isCloudParser = computed(() => parserProvider.value === 'volcengine_ark_vision')
const parseTags = (text: string) => text.split(',').map((x) => x.trim()).filter(Boolean)

const load = async () => {
  loading.value = true
  try {
    state.value = await getPortfolio()
    try {
      const providers = await getPortfolioImportParserProviders()
      parserStatus.value = providers
      parserProvider.value = providers.default_provider || 'local_noop'
    } catch {
      parserStatus.value = {
        default_provider: 'local_noop',
        providers: [
          { provider: 'local_noop', display_name: '手工补录', status: 'available' },
          { provider: 'volcengine_ark_vision', display_name: '云端视觉解析', status: 'backend_endpoint_unavailable' },
        ],
      }
      parserProvider.value = 'local_noop'
    }
    accountDraft.value.cash_available = state.value.snapshot.cash_available
    accountDraft.value.repo_amount = state.value.snapshot.repo_amount
    accountDraft.value.total_assets = state.value.snapshot.total_assets ?? null
    accountDraft.value.max_position_weight = state.value.snapshot.risk_limits.max_position_weight
    accountDraft.value.max_theme_weight = state.value.snapshot.risk_limits.max_theme_weight
    accountDraft.value.min_cash_ratio = state.value.snapshot.risk_limits.min_cash_ratio
  } finally {
    loading.value = false
  }
}

const persist = async (nextPositions: any[] = positions.value) => {
  saving.value = true
  try {
    state.value = await savePortfolio({
      portfolio_id: state.value?.snapshot.portfolio_id || 'local_default',
      snapshot_time: new Date().toISOString(),
      total_assets: accountDraft.value.total_assets,
      cash_available: Number(accountDraft.value.cash_available || 0),
      repo_amount: Number(accountDraft.value.repo_amount || 0),
      risk_limits: {
        max_position_weight: Number(accountDraft.value.max_position_weight || 35),
        max_theme_weight: Number(accountDraft.value.max_theme_weight || 50),
        min_cash_ratio: Number(accountDraft.value.min_cash_ratio || 5),
      },
      positions: nextPositions.map((p: any) => ({
        symbol: p.symbol,
        name: p.name,
        quantity: Number(p.quantity || 0),
        available_quantity: p.available_quantity === '' ? null : p.available_quantity ?? null,
        avg_cost: Number(p.avg_cost || 0),
        broker_screenshot_price: p.broker_screenshot_price ?? null,
        broker_screenshot_price_source: p.broker_screenshot_price_source ?? null,
        broker_screenshot_price_time: p.broker_screenshot_price_time ?? null,
        broker_screenshot_market_value: p.broker_screenshot_market_value ?? null,
        broker_screenshot_unrealized_pnl: p.broker_screenshot_unrealized_pnl ?? null,
        broker_screenshot_unrealized_pnl_pct: p.broker_screenshot_unrealized_pnl_pct ?? null,
        source_type: p.source_type || 'manual_account',
        source_name: p.source_name || null,
        import_draft_id: p.import_draft_id || null,
        confirmed_by_user: p.confirmed_by_user || false,
        position_role: p.position_role || 'observation',
        theme_tags: p.theme_tags || [],
        primary_theme: p.primary_theme || null,
        user_plan: p.user_plan || '',
        invalid_condition: p.invalid_condition || null,
        target_max_weight: p.target_max_weight ?? null,
        notes: p.notes || null,
      })),
    })
  } finally {
    saving.value = false
  }
}

const addPosition = async () => {
  await persist([
    ...positions.value,
    {
      ...positionDraft.value,
      theme_tags: parseTags(positionDraft.value.theme_tags_text),
      quantity: Number(positionDraft.value.quantity || 0),
      available_quantity: positionDraft.value.available_quantity,
      avg_cost: Number(positionDraft.value.avg_cost || 0),
    },
  ])
  positionDraft.value = {
    symbol: '',
    name: '',
    quantity: 0,
    available_quantity: null,
    avg_cost: 0,
    position_role: 'observation',
    primary_theme: '',
    theme_tags_text: '',
    user_plan: '',
    invalid_condition: '',
    target_max_weight: null,
  }
}

const removePosition = async (symbol: string) => {
  await persist(positions.value.filter((p) => p.symbol !== symbol))
}

const onFileChange = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  selectedFile.value = file || null
  selectedPreview.value = file ? URL.createObjectURL(file) : ''
  importError.value = ''
}

const uploadScreenshot = async () => {
  if (!selectedFile.value) return
  importLoading.value = true
  importError.value = ''
  try {
    draft.value = await uploadPortfolioScreenshot(selectedFile.value, {
      parser_provider: parserProvider.value,
      cloud_send_consent: isCloudParser.value,
      user_notice_acknowledged_at: isCloudParser.value ? new Date().toISOString() : null,
    })
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || error?.message || '识别失败'
  } finally {
    importLoading.value = false
  }
}

const addDraftRow = () => {
  if (!draft.value) return
  draft.value.holding_rows_draft.push({
    row_id: `row_${Date.now()}`,
    raw_symbol_text: '',
    raw_name_text: '',
    normalized_symbol: '',
    normalized_name: '',
    symbol_match_status: 'unresolved',
    symbol_candidates: [],
    quantity: null,
    available_quantity: null,
    avg_cost: null,
    broker_screenshot_price: null,
    broker_screenshot_market_value: null,
    broker_screenshot_unrealized_pnl: null,
    broker_screenshot_unrealized_pnl_pct: null,
    validation_warnings: ['手工新增行，请保存草稿后重新匹配。'],
    requires_user_confirmation: true,
    position_role: 'observation',
    primary_theme: '',
    theme_tags: [],
    user_plan: '',
    invalid_condition: '',
    target_max_weight: null,
    confirmed_by_user: true,
  })
}

const saveDraft = async () => {
  if (!draft.value) return
  draft.value = await updatePortfolioImportDraft(draft.value.draft_id, {
    account_summary_draft: draft.value.account_summary_draft,
    holding_rows_draft: draft.value.holding_rows_draft,
    parse_warnings: draft.value.parse_warnings,
  })
}

const confirmDraft = async () => {
  if (!draft.value) return
  try {
    await saveDraft()
    const result = await confirmPortfolioImportDraft(draft.value.draft_id)
    draft.value = result.draft
    state.value = result.portfolio
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || '确认失败，请检查未解决字段'
  }
}

const rejectDraft = async () => {
  if (!draft.value) return
  draft.value = await rejectPortfolioImportDraft(draft.value.draft_id)
}

const chooseCandidate = (row: any) => {
  const candidate = row.symbol_candidates?.find((item: any) => item.symbol === row.normalized_symbol)
  if (!candidate) return
  row.normalized_name = candidate.name
  row.external_driver_profile_id = candidate.external_driver_profile_id
  row.external_driver_mapping_status = candidate.external_driver_mapping_status
  row.symbol_match_status = 'name_candidate_match'
}

const buildSnapshot = async () => {
  const snap = await getPortfolioSnapshot()
  snapshotNotice.value = draft.value?.needs_user_confirmation
    ? '当前摘要只读取已确认的正式 portfolio snapshot；未确认草稿不会进入 evidence_count 或 target_symbols。'
    : ''
  snapshotPreview.value = JSON.stringify({
    snapshot_id: snap.snapshot_id,
    analysis_scope: snap.analysis_scope,
    evidence_count: snap.evidence_items?.length,
    target_symbols: snap.target_symbols,
    missing_data: snap.missing_data,
  }, null, 2)
}

const buildPortfolioPacket = async () => {
  packetLoading.value = true
  packetCopied.value = false
  try {
    const result = await createPortfolioAnalysisPacket()
    packetMarkdown.value = result.markdown
    packetJson.value = JSON.stringify(result.packet, null, 2)
  } finally {
    packetLoading.value = false
  }
}

const copyPortfolioPacket = async () => {
  if (!packetMarkdown.value) return
  await navigator.clipboard.writeText(packetMarkdown.value)
  packetCopied.value = true
}

onMounted(load)
</script>

<template>
  <section class="mb-4 rounded-lg border border-border bg-card">
    <button class="flex w-full items-center justify-between px-3 py-2 text-left" @click="expanded = !expanded">
      <div>
        <h2 class="text-sm font-semibold text-foreground">组合与本地账户快照</h2>
        <p class="text-[11px] text-muted-foreground">本地保存；截图识别结果先进入草稿，确认后才写入正式组合。</p>
      </div>
      <span class="text-xs text-muted-foreground">{{ expanded ? '收起' : '展开' }}</span>
    </button>

    <div v-if="expanded" class="space-y-4 border-t border-border p-3">
      <div v-if="loading" class="text-xs text-muted-foreground">加载组合...</div>
      <template v-if="state && metrics">
        <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">总资产</div><div class="font-mono">{{ fmt(metrics.total_assets) }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">总市值</div><div class="font-mono">{{ fmt(metrics.total_market_value) }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">可用现金</div><div class="font-mono">{{ fmt(metrics.cash_available) }} / {{ fmt(metrics.cash_ratio_pct, '%') }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">逆回购</div><div class="font-mono">{{ fmt(metrics.repo_amount) }} / {{ fmt(metrics.repo_ratio_pct, '%') }}</div></div>
          <div class="rounded bg-secondary/40 p-2"><div class="text-muted-foreground">持仓占比</div><div class="font-mono">{{ fmt(metrics.invested_ratio_pct, '%') }}</div></div>
        </div>

        <div class="overflow-x-auto rounded border border-border/60">
          <table class="w-full text-xs">
            <thead class="bg-secondary/40 text-muted-foreground">
              <tr>
                <th class="p-2 text-left">标的</th>
                <th>持仓数量</th>
                <th>可用数量</th>
                <th>平均成本</th>
                <th>系统行情价</th>
                <th>截图价格</th>
                <th>市值 / 盈亏</th>
                <th>主题</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in positions" :key="p.symbol" class="border-t border-border/50">
                <td class="p-2">{{ p.symbol }} {{ p.name }}</td>
                <td class="text-right">{{ fmt(p.quantity) }}</td>
                <td class="text-right">{{ fmt(p.available_quantity) }}</td>
                <td class="text-right">{{ fmt(p.avg_cost) }}</td>
                <td class="text-right">{{ fmt(p.system_quote_price ?? p.market_price) }}</td>
                <td class="text-right">{{ fmt(p.broker_screenshot_price) }}</td>
                <td class="text-right">{{ fmt(p.market_value) }} / {{ fmt(p.unrealized_pnl) }}</td>
                <td class="px-2">{{ p.primary_theme || '-' }} / {{ p.theme_tags.join(',') }}</td>
                <td class="p-2 text-right"><button class="text-negative" @click="removePosition(p.symbol)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="grid grid-cols-2 gap-2 text-xs md:grid-cols-6">
          <input v-model="positionDraft.symbol" class="rounded bg-input px-2 py-1" placeholder="标准代码，如 601899.SH" />
          <input v-model="positionDraft.name" class="rounded bg-input px-2 py-1" placeholder="名称" />
          <input v-model.number="positionDraft.quantity" class="rounded bg-input px-2 py-1" type="number" placeholder="持仓数量" />
          <input v-model.number="positionDraft.available_quantity" class="rounded bg-input px-2 py-1" type="number" placeholder="可用数量" />
          <input v-model.number="positionDraft.avg_cost" class="rounded bg-input px-2 py-1" type="number" placeholder="平均成本" />
          <button class="rounded bg-primary px-3 py-1" :disabled="saving" @click="addPosition">新增持仓</button>
          <input v-model.number="accountDraft.cash_available" class="rounded bg-input px-2 py-1" type="number" placeholder="可用现金" />
          <input v-model.number="accountDraft.repo_amount" class="rounded bg-input px-2 py-1" type="number" placeholder="逆回购金额" />
          <input v-model="positionDraft.primary_theme" class="rounded bg-input px-2 py-1" placeholder="primary_theme" />
          <input v-model="positionDraft.theme_tags_text" class="rounded bg-input px-2 py-1" placeholder="theme_tags，逗号分隔" />
          <input v-model="positionDraft.position_role" class="rounded bg-input px-2 py-1" placeholder="position_role" />
          <input v-model="positionDraft.invalid_condition" class="rounded bg-input px-2 py-1" placeholder="invalid_condition" />
        </div>

        <div class="rounded border border-border/60 p-3">
          <div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <select v-model="parserProvider" class="rounded bg-input px-2 py-1">
              <option value="local_noop">手工补录</option>
              <option value="volcengine_ark_vision">云端视觉解析</option>
            </select>
            <input type="file" accept="image/png,image/jpeg,image/webp" @change="onFileChange" />
            <button class="rounded bg-primary px-3 py-1" :disabled="!selectedFile || importLoading" @click="uploadScreenshot">
              {{ importLoading ? '正在识别...' : (isCloudParser ? '识别截图' : '创建草稿') }}
            </button>
            <button v-if="draft" class="rounded bg-secondary px-3 py-1" @click="addDraftRow">新增行</button>
            <button v-if="draft" class="rounded bg-negative px-3 py-1" @click="rejectDraft">放弃草稿</button>
          </div>
          <div v-if="parserStatus" class="mb-2 text-[11px] text-muted-foreground">
            <span v-for="item in parserStatus.providers" :key="item.provider" class="mr-3">{{ item.display_name }}: {{ item.status }}</span>
          </div>
          <div v-if="importLoading" class="mb-2 rounded border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
            正在识别，请稍候。云端视觉解析可能需要几十秒，超时后会返回可手工修正的草稿。
          </div>
          <img v-if="selectedPreview" :src="selectedPreview" class="mt-3 max-h-52 rounded border border-border/60 object-contain" alt="持仓截图预览" />
          <div v-if="importError" class="mt-2 text-xs text-negative">{{ importError }}</div>

          <div v-if="draft" class="mt-3 space-y-2 text-xs">
            <div class="text-muted-foreground">
              草稿 {{ draft.draft_id }} / {{ draft.parse_status }} / provider: {{ draft.parser_provider || draft.ocr_provider }} / cloud: {{ draft.cloud_parse_status || '-' }}
            </div>
            <div class="text-muted-foreground">截图价格不是系统实时行情；确认前不会写入正式账户。</div>
            <div v-for="warning in draft.parse_warnings" :key="warning" class="text-warning">{{ warning }}</div>
            <div v-if="draft.provider_error_summary" class="text-warning">错误摘要：{{ draft.provider_error_summary }}</div>

            <div class="overflow-x-auto rounded border border-border/60">
              <table class="w-full min-w-[1200px] text-xs">
                <thead class="bg-secondary/40 text-muted-foreground">
                  <tr>
                    <th class="p-2 text-left">识别代码</th>
                    <th>标准代码</th>
                    <th>标准名称</th>
                    <th>持仓数量</th>
                    <th>可用数量</th>
                    <th>平均成本</th>
                    <th>截图价格</th>
                    <th>截图市值</th>
                    <th>浮动盈亏</th>
                    <th>external driver</th>
                    <th>primary_theme</th>
                    <th>theme_tags</th>
                    <th>position_role</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in draft.holding_rows_draft" :key="row.row_id" class="border-t border-border/50">
                    <td class="p-1"><input v-model="row.raw_symbol_text" class="w-28 rounded bg-input px-2 py-1" /></td>
                    <td class="p-1">
                      <select v-if="row.symbol_candidates?.length" v-model="row.normalized_symbol" class="w-32 rounded bg-input px-2 py-1" @change="chooseCandidate(row)">
                        <option :value="row.normalized_symbol">{{ row.normalized_symbol || '请选择' }}</option>
                        <option v-for="candidate in row.symbol_candidates" :key="candidate.symbol" :value="candidate.symbol">{{ candidate.symbol }}</option>
                      </select>
                      <input v-else v-model="row.normalized_symbol" class="w-32 rounded bg-input px-2 py-1" />
                    </td>
                    <td class="p-1"><input v-model="row.normalized_name" class="w-28 rounded bg-input px-2 py-1" /></td>
                    <td class="p-1"><input v-model.number="row.quantity" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1"><input v-model.number="row.available_quantity" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1"><input v-model.number="row.avg_cost" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1"><input v-model.number="row.broker_screenshot_price" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1"><input v-model.number="row.broker_screenshot_market_value" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1"><input v-model.number="row.broker_screenshot_unrealized_pnl" class="w-24 rounded bg-input px-2 py-1" type="number" /></td>
                    <td class="p-1 text-muted-foreground">{{ row.external_driver_profile_id || row.external_driver_mapping_status || '-' }}</td>
                    <td class="p-1"><input v-model="row.primary_theme" class="w-28 rounded bg-input px-2 py-1" /></td>
                    <td class="p-1"><input :value="row.theme_tags?.join(',')" class="w-32 rounded bg-input px-2 py-1" @input="row.theme_tags = parseTags(($event.target as HTMLInputElement).value)" /></td>
                    <td class="p-1"><input v-model="row.position_role" class="w-28 rounded bg-input px-2 py-1" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-for="row in draft.holding_rows_draft" :key="`${row.row_id}-warnings`" class="text-warning">
              <span v-if="row.validation_warnings?.length">{{ row.normalized_symbol || row.raw_name_text || row.row_id }}：{{ row.validation_warnings.join('；') }}</span>
            </div>
            <button class="rounded bg-primary px-3 py-2 text-xs" :disabled="draft.parse_status === 'saved_as_portfolio_snapshot'" @click="confirmDraft">
              确认入账
            </button>
          </div>
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
              <h3 class="text-xs font-semibold">Portfolio Analysis Packet v1</h3>
              <p class="text-[11px] text-muted-foreground">用户主动生成；不会自动调用外部 LLM。</p>
            </div>
            <div class="flex gap-2">
              <button class="rounded bg-secondary px-3 py-1 text-xs" :disabled="!packetMarkdown" @click="copyPortfolioPacket">{{ packetCopied ? 'Copied' : 'Copy Markdown' }}</button>
              <button class="rounded bg-primary px-3 py-1 text-xs" :disabled="packetLoading" @click="buildPortfolioPacket">{{ packetLoading ? 'Generating...' : 'Generate Portfolio Packet' }}</button>
            </div>
          </div>
          <pre v-if="packetMarkdown" class="max-h-80 overflow-auto rounded bg-black/30 p-2 text-[11px] whitespace-pre-wrap">{{ packetMarkdown }}</pre>
          <details v-if="packetJson" class="mt-2 text-xs">
            <summary class="cursor-pointer text-muted-foreground">JSON snapshot</summary>
            <pre class="mt-2 max-h-60 overflow-auto rounded bg-black/30 p-2 text-[11px]">{{ packetJson }}</pre>
          </details>
        </div>
      </template>
    </div>
  </section>
</template>
