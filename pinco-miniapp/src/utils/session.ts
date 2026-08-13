import Taro from '@tarojs/taro'

const DEVICE_KEY = 'pinco_device_id_v1'

const generateId = () => `device_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`

export const getDeviceId = () => {
  let deviceId = Taro.getStorageSync(DEVICE_KEY)
  if (!deviceId) {
    deviceId = generateId()
    Taro.setStorageSync(DEVICE_KEY, deviceId)
  }
  return deviceId as string
}

export const getBootstrapPayload = async () => {
  const device_id = getDeviceId()
  let code = ''
  try {
    if (process.env.TARO_ENV === 'weapp') {
      const result = await Taro.login()
      code = result.code || ''
    }
  } catch (error) {
    console.warn('[Session] login failed, fallback to device id only', error)
  }

  return {
    device_id,
    code,
    platform: process.env.TARO_ENV || 'unknown',
    nickname: ''
  }
}
