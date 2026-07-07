const currentHost = typeof window === 'undefined' ? '127.0.0.1' : window.location.hostname

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${currentHost}:8000`

export const API_BASE_LABEL = API_BASE_URL
  .replace(`http://${currentHost}:`, ':')
  .replace('http://127.0.0.1:', ':')
  .replace('http://localhost:', ':')
