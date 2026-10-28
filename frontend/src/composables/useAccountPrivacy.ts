import { ref } from 'vue'
const key = 'stock-pilot:account-privacy'
function saved() {
  try { return localStorage.getItem(key) === 'hidden' } catch { return false }
}
export const accountPrivacyHidden = ref(saved())
export function toggleAccountPrivacy() {
  accountPrivacyHidden.value = !accountPrivacyHidden.value
  try { localStorage.setItem(key, accountPrivacyHidden.value ? 'hidden' : 'visible') } catch { /* Session-only when storage is unavailable. */ }
}
window.addEventListener('storage', event => { if (event.key === key) accountPrivacyHidden.value = event.newValue === 'hidden' })
