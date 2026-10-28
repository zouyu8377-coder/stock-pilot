import { ref } from 'vue'
import { investmentAgentRequest } from '../api/client'

export const assistantStatus = ref<any>(null)
export const assistantStatusError = ref(false)
let pending: Promise<void> | null = null

export function refreshAssistantStatus() {
  if (pending) return pending
  pending = (async () => {
    try {
      assistantStatus.value = await investmentAgentRequest('/assistant-status')
      assistantStatusError.value = false
    } catch {
      assistantStatusError.value = true
    } finally { pending = null }
  })()
  return pending
}

export function getAssistantStatus(key: string) {
  if (assistantStatusError.value) return { level: 'red', text: '状态不可用', reasons: ['无法获取工作状态，请检查后端连接或重启服务加载新版本。'] }
  return assistantStatus.value?.assistants?.[key] || { level: 'yellow', text: '检查中', reasons: ['正在读取数据和分析入口状态，不会触发模型。'] }
}
