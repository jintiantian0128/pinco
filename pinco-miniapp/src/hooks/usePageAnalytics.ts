import { useDidShow } from '@tarojs/taro'
import { usePincoStore } from '@/store/usePincoStore'
import { trackProductEvent } from '@/services/analytics'

/** Page views are useful for funnel analysis; never attach user-entered content. */
export const usePageAnalytics = (page: string) => {
  useDidShow(() => {
    const userId = usePincoStore.getState().userProfile?.user_id
    trackProductEvent('screen.viewed', userId, { page })
  })
}
