import Taro from '@tarojs/taro'

export const readStorage = <T,>(key: string, fallback: T): T => {
  try {
    const value = Taro.getStorageSync(key)
    if (!value) return fallback
    if (typeof value === 'string') {
      return JSON.parse(value) as T
    }
    return value as T
  } catch (error) {
    console.error('[Storage] read failed', key, error)
    return fallback
  }
}

export const writeStorage = (key: string, value: unknown) => {
  try {
    Taro.setStorageSync(key, JSON.stringify(value))
  } catch (error) {
    console.error('[Storage] write failed', key, error)
  }
}
