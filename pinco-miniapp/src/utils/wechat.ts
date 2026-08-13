import Taro from '@tarojs/taro'
import { getApiBaseUrl } from '@/services/api'
import { MiniappReadiness, MiniappRuntimeInfo } from '@/types/pinco'

const DEFAULT_APP_ID = 'wxf2840ca876909eb5'

const getPlatformName = () => {
  try {
    const env = Taro.getEnv?.()
    return typeof env === 'string' ? env.toLowerCase() : 'unknown'
  } catch (error) {
    console.warn('[Wechat] getEnv failed', error)
    return 'unknown'
  }
}

export const getMiniappRuntimeInfo = (loginCodeReady = false): MiniappRuntimeInfo => {
  const platform = getPlatformName()
  const isWeapp = platform === 'weapp'
  let appId = DEFAULT_APP_ID
  let envVersion = isWeapp ? 'develop' : platform

  try {
    if (isWeapp && Taro.getAccountInfoSync) {
      const accountInfo = Taro.getAccountInfoSync()
      appId = accountInfo?.miniProgram?.appId || appId
      envVersion = accountInfo?.miniProgram?.envVersion || envVersion
    }
  } catch (error) {
    console.warn('[Wechat] getAccountInfoSync failed', error)
  }

  return {
    platform,
    apiBaseUrl: getApiBaseUrl(),
    appId,
    envVersion,
    isTouristAppId: appId === DEFAULT_APP_ID,
    loginCodeReady,
  }
}

export const buildWechatSetupChecklist = (
  runtimeInfo: MiniappRuntimeInfo,
  readiness: MiniappReadiness | null
) => {
  const lines = [
    'Pinco 微信小程序接入清单',
    `- 平台: ${runtimeInfo.platform}`,
    `- AppID: ${runtimeInfo.appId}${runtimeInfo.isTouristAppId ? '（仍是 touristappid）' : ''}`,
    `- 运行环境: ${runtimeInfo.envVersion}`,
    `- API 域名: ${runtimeInfo.apiBaseUrl}`,
    `- 登录 code: ${runtimeInfo.loginCodeReady ? '已获取' : '未获取'}`,
    `- 后端准备度: ${readiness?.summary || '暂未拿到 readiness'}`,
  ]

  if (readiness?.items?.length) {
    lines.push('', '当前检查项:')
    readiness.items.forEach((item) => {
      lines.push(`- ${item.label}: ${item.ready ? '已完成' : '待补齐'} | ${item.detail}`)
    })
  }

  if (readiness?.next_steps?.length) {
    lines.push('', '下一步:')
    readiness.next_steps.forEach((step, index) => {
      lines.push(`${index + 1}. ${step}`)
    })
  }

  return lines.join('\n')
}
