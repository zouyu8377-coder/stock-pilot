<script setup lang="ts">
defineProps<{
  hotStatus: string
  coldStatus: string
  aiStatus: string
}>()

function getStatusColor(status: string): string {
  if (status === 'ready') return 'bg-emerald-500'
  if (status === 'loading') return 'bg-amber-400'
  return 'bg-red-500'
}

function getStatusText(status: string): string {
  if (status === 'ready') return 'Ready'
  if (status === 'loading') return 'Loading'
  return 'Error'
}
</script>

<template>
  <div class="flex items-center justify-center gap-6 py-4 border-t border-border/50 mt-4">
    <div class="flex items-center gap-2">
      <div :class="['w-2 h-2 rounded-full', getStatusColor(hotStatus)]"></div>
      <span class="text-xs text-slate-400">Hot {{ getStatusText(hotStatus) }}</span>
    </div>
    <div class="flex items-center gap-2">
      <div :class="['w-2 h-2 rounded-full', getStatusColor(coldStatus)]"></div>
      <span class="text-xs text-slate-400">Cold {{ getStatusText(coldStatus) }}</span>
    </div>
    <div class="flex items-center gap-2">
      <div :class="['w-2 h-2 rounded-full', getStatusColor(aiStatus)]"></div>
      <span class="text-xs text-slate-400">AI {{ getStatusText(aiStatus) }}</span>
    </div>
  </div>
</template>