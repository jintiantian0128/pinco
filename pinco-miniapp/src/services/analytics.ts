import Taro from '@tarojs/taro'
import { apiRequest } from './api'

const SESSION_KEY = 'pinco_analytics_session_v1'

const getSessionId = () => {
  try {
    const existing = Taro.getStorageSync(SESSION_KEY)
    if (existing) return String(existing)
    const created = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    Taro.setStorageSync(SESSION_KEY, created)
    return created
  } catch {
    return `session-${Date.now()}`
  }
}

export const trackProductEvent = (
  name: string,
  userId?: string,
  properties: Record<string, string | number | boolean | null | undefined> = {}
) => {
  apiRequest('/api/v1/events', 'POST', {
    name,
    user_id: userId,
    session_id: getSessionId(),
    properties,
  }).catch((error) => {
    console.warn('[Analytics] event delivery failed', name, error)
  })
}
