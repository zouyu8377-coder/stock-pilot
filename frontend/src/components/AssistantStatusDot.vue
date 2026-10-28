<script setup lang="ts">
import { computed, ref } from 'vue'
import { getAssistantStatus } from '../composables/useAssistantStatus'
const props = defineProps<{ assistant: string; label: string }>()
const state = computed(() => getAssistantStatus(props.assistant))
const formatReason = (reason: string) => reason.replace(/\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})/g, value => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }))
const opened = ref(false)
const position = ref({ left: '12px', top: '60px' })
function show(event: Event) {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect()
  position.value = { left: `${Math.max(8, Math.min(box.left, window.innerWidth - 328))}px`, top: `${box.bottom + 10}px` }
  opened.value = true
}
</script>
<template>
  <span class="assistant-indicator" tabindex="0" :aria-label="`${label}助手：${state.text}`" :aria-describedby="opened ? `assistant-tooltip-${assistant}` : undefined" @mouseenter="show" @mouseleave="opened = false" @focus="show" @blur="opened = false" @keydown.esc="opened = false">
    <span :class="['assistant-dot', state.level]" aria-hidden="true" />
    <span class="sr-only">{{ state.text }}</span>
    <Teleport to="body"><div v-if="opened" :id="`assistant-tooltip-${assistant}`" role="tooltip" class="assistant-tooltip" :style="position"><strong>{{ label }}助手 · {{ state.text }}</strong><ul><li v-for="reason in state.reasons" :key="reason">{{ formatReason(reason) }}</li></ul><p>工作状态，不是投资风险评级。模型登录与额度未预检。</p></div></Teleport>
  </span>
</template>
<style scoped>
.assistant-indicator { display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 20px; flex-shrink: 0; border-radius: 3px; }
.assistant-indicator:focus-visible { outline: 2px solid #7dd3fc; }
.assistant-dot { display: block; width: 7px; height: 7px; border-radius: 50%; }
.green { background: #4ade80; } .yellow { background: #facc15; } .red { background: #fb7185; }
.assistant-tooltip { position: fixed; z-index: 100; width: 312px; max-width: calc(100vw - 16px); padding: 14px; border: 1px solid #435273; border-radius: 6px; background: #101c31; color: #e2e8f0; box-shadow: 0 8px 28px #0006; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; pointer-events: none; }
.assistant-tooltip ul { margin: 8px 0; padding-left: 16px; list-style: disc; }
.assistant-tooltip p { color: #a8b7cc; border-top: 1px solid #34425b; padding-top: 8px; }
</style>
