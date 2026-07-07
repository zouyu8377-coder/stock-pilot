<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  getDisclosureFacts,
  getDragonTigerFacts,
  getEtfFacts,
  type DisclosureFacts,
  type DragonTigerEvent,
  type EtfFacts,
  type FactResponse,
} from '../api/client'

const props = defineProps<{
  symbol: string
}>()

const loading = ref(false)
const error = ref('')
const etfData = ref<FactResponse<EtfFacts | null> | null>(null)
const dragonData = ref<FactResponse<{
  latest_event: DragonTigerEvent | null
  events: DragonTigerEvent[]
  empty_message: string
  interpretation_limit: string
}> | null>(null)
const disclosureData = ref<FactResponse<DisclosureFacts> | null>(null)
const showDragonHistory = ref(false)

const isEtf = computed(() => /^(15|16|51|56|58)/.test(props.symbol))
const hasEtfData = computed(() => Boolean(isEtf.value && etfData.value?.success && etfData.value.data))
const hasDragonData = computed(() => Boolean(!isEtf.value && dragonData.value?.success && dragonData.value.data.latest_event))
const latestDragonEvent = computed(() => dragonData.value?.data.latest_event)
const hasDisclosureData = computed(() => Boolean(
  !isEtf.value
  && disclosureData.value?.success
  && ((disclosureData.value.data.announcements?.length || 0) > 0 || (disclosureData.value.data.surveys?.length || 0) > 0),
))

const fmt = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const signed = (value?: number | null, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
}

const load = async () => {
  loading.value = true
  error.value = ''
  etfData.value = null
  dragonData.value = null
  disclosureData.value = null
  showDragonHistory.value = false
  try {
    if (isEtf.value) {
      etfData.value = await getEtfFacts(props.symbol)
    } else {
      const [dragon, disclosure] = await Promise.all([
        getDragonTigerFacts(props.symbol),
        getDisclosureFacts(props.symbol),
      ])
      dragonData.value = dragon
      disclosureData.value = disclosure
    }
  } catch (e: any) {
    error.value = e.message || '事实层数据暂不可用'
  } finally {
    loading.value = false
  }
}

watch(() => props.symbol, load, { immediate: true })
</script>

<template>
  <div class="space-y-3">
    <div v-if="loading" class="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
      正在加载自动事实层...
    </div>
    <div v-if="error" class="rounded-lg border border-border bg-card p-3 text-xs text-warning">
      {{ error }}
    </div>

    <div v-if="hasEtfData && etfData?.data" class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/30">
        <div>
          <h3 class="text-sm font-semibold text-foreground">ETF资金观察</h3>
          <p class="text-[11px] text-muted-foreground">{{ etfData.data.name || etfData.symbol }}</p>
        </div>
        <span class="rounded bg-primary/30 px-2 py-1 text-[11px] text-foreground">
          {{ etfData.data.quadrant_label }}
        </span>
      </div>
      <div class="p-3 space-y-3">
        <div class="grid grid-cols-4 gap-2 text-xs">
          <div class="rounded bg-secondary/40 p-2">
            <div class="text-muted-foreground">份额</div>
            <div class="font-mono text-foreground">{{ fmt(etfData.data.latest_share) }}</div>
          </div>
          <div class="rounded bg-secondary/40 p-2">
            <div class="text-muted-foreground">规模</div>
            <div class="font-mono text-foreground">{{ fmt(etfData.data.latest_size) }}</div>
          </div>
          <div class="rounded bg-secondary/40 p-2">
            <div class="text-muted-foreground">NAV</div>
            <div class="font-mono text-foreground">{{ fmt(etfData.data.nav) }}</div>
          </div>
          <div class="rounded bg-secondary/40 p-2">
            <div class="text-muted-foreground">收盘</div>
            <div class="font-mono text-foreground">{{ fmt(etfData.data.close) }}</div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-xs">
          <div class="rounded bg-secondary/30 p-2">
            <div class="text-muted-foreground">1日份额</div>
            <div class="font-mono">{{ signed(etfData.data.share_change['1d']) }} / {{ signed(etfData.data.share_change['1d_pct'], '%') }}</div>
          </div>
          <div class="rounded bg-secondary/30 p-2">
            <div class="text-muted-foreground">5日份额</div>
            <div class="font-mono">{{ signed(etfData.data.share_change['5d']) }} / {{ signed(etfData.data.share_change['5d_pct'], '%') }}</div>
          </div>
          <div class="rounded bg-secondary/30 p-2">
            <div class="text-muted-foreground">20日份额</div>
            <div class="font-mono">{{ signed(etfData.data.share_change['20d']) }} / {{ signed(etfData.data.share_change['20d_pct'], '%') }}</div>
          </div>
        </div>
        <div class="text-[11px] text-muted-foreground">
          截止 {{ etfData.data.as_of_date || '--' }} · {{ etfData.data.interpretation_limit }}
        </div>
      </div>
    </div>

    <div v-if="hasDragonData && dragonData && latestDragonEvent" class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/30">
        <h3 class="text-sm font-semibold text-foreground">龙虎榜事件</h3>
        <button
          v-if="dragonData.data.events.length > 1"
          class="text-xs text-muted-foreground hover:text-foreground"
          @click="showDragonHistory = !showDragonHistory"
        >
          {{ showDragonHistory ? '收起' : '展开历史' }}
        </button>
      </div>
      <div class="p-3">
        <div class="space-y-3">
          <div class="grid grid-cols-4 gap-2 text-xs">
            <div><span class="text-muted-foreground">日期</span><div>{{ latestDragonEvent.trade_date }}</div></div>
            <div><span class="text-muted-foreground">收盘</span><div>{{ fmt(latestDragonEvent.close) }}</div></div>
            <div><span class="text-muted-foreground">涨跌</span><div>{{ signed(latestDragonEvent.pct_change, '%') }}</div></div>
            <div><span class="text-muted-foreground">净买入</span><div>{{ fmt(latestDragonEvent.net_buy) }}</div></div>
          </div>
          <p class="text-xs text-foreground/80">{{ latestDragonEvent.reason }}</p>
          <div class="flex gap-2 text-[11px]">
            <span v-if="latestDragonEvent.has_institutional_seat" class="rounded bg-primary/25 px-2 py-1">机构专用</span>
            <span v-if="latestDragonEvent.has_stock_connect_seat" class="rounded bg-primary/25 px-2 py-1">股通席位</span>
          </div>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div class="mb-1 text-muted-foreground">前五买入</div>
              <div v-for="seat in latestDragonEvent.top_buy_seats" :key="seat.seat" class="truncate text-foreground/80">
                {{ seat.seat }} · {{ fmt(seat.buy) }}
              </div>
            </div>
            <div>
              <div class="mb-1 text-muted-foreground">前五卖出</div>
              <div v-for="seat in latestDragonEvent.top_sell_seats" :key="seat.seat" class="truncate text-foreground/80">
                {{ seat.seat }} · {{ fmt(seat.sell) }}
              </div>
            </div>
          </div>
          <div v-if="showDragonHistory" class="space-y-1 border-t border-border/50 pt-2 text-xs">
            <div v-for="item in dragonData.data.events.slice(1)" :key="`${item.trade_date}-${item.reason}`" class="flex justify-between gap-2 text-muted-foreground">
              <span>{{ item.trade_date }} · {{ item.reason }}</span>
              <span class="font-mono">{{ fmt(item.net_buy) }}</span>
            </div>
          </div>
          <div class="text-[11px] text-muted-foreground">{{ dragonData.data.interpretation_limit }}</div>
        </div>
      </div>
    </div>

    <div v-if="hasDisclosureData && disclosureData?.data" class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="px-3 py-2 border-b border-border bg-secondary/30">
        <h3 class="text-sm font-semibold text-foreground">公告 / 机构调研索引</h3>
      </div>
      <div class="p-3 space-y-3">
        <div>
          <div class="mb-1 text-xs font-medium text-muted-foreground">公告</div>
          <div v-if="disclosureData.data.announcements.length === 0" class="text-xs text-muted-foreground">最近90日无公告索引</div>
          <a
            v-for="item in disclosureData.data.announcements.slice(0, 5)"
            :key="`${item.ann_date}-${item.title}`"
            :href="item.url"
            target="_blank"
            rel="noreferrer"
            class="block rounded bg-secondary/30 p-2 text-xs hover:bg-secondary/50"
          >
            <div class="flex items-center gap-2">
              <span class="font-mono text-muted-foreground">{{ item.ann_date }}</span>
              <span class="rounded bg-primary/25 px-1.5 py-0.5 text-[10px]">{{ item.category_label }}</span>
            </div>
            <div class="mt-1 text-foreground/85">{{ item.title }}</div>
          </a>
          <div class="mt-1 text-[11px] text-muted-foreground">{{ disclosureData.data.announcement_interpretation_limit }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs font-medium text-muted-foreground">机构调研</div>
          <div v-if="disclosureData.data.surveys.length === 0" class="text-xs text-muted-foreground">最近90日无机构调研索引</div>
          <div
            v-for="item in disclosureData.data.surveys.slice(0, 5)"
            :key="`${item.surv_date}-${item.rece_org}`"
            class="mb-1 rounded bg-secondary/30 p-2 text-xs"
          >
            <div class="font-mono text-muted-foreground">{{ item.surv_date }}</div>
            <div class="text-foreground/85">{{ item.rece_mode || '-' }} · {{ item.rece_org || '-' }}</div>
            <div class="text-muted-foreground">{{ item.org_type || '-' }} · {{ item.comp_rece || '-' }}</div>
          </div>
          <div class="mt-1 text-[11px] text-muted-foreground">{{ disclosureData.data.survey_interpretation_limit }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
