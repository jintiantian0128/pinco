import Taro from '@tarojs/taro'

declare const wx: any

// 云托管公网域名（用于文件上传和 H5）
const REMOTE_BASE_URL = process.env.PINCO_API_BASE_URL || 'https://flask-jk7n-277209-9-1430442234.sh.run.tcloudbase.com'

export const getApiBaseUrl = () => {
  if (process.env.TARO_ENV === 'h5') {
    const hostname = typeof globalThis !== 'undefined' && globalThis.location ? globalThis.location.hostname : ''
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://127.0.0.1:8090'
    }
  }
  return REMOTE_BASE_URL
}

const isWeapp = process.env.TARO_ENV === 'weapp' || (typeof wx !== 'undefined' && wx.cloud)

// 微信云托管 callContainer 配置
const CLOUD_ENV = 'prod-d1g71nka2ab801ddb'
const CLOUD_SERVICE = 'flask-jk7n'
let apiSessionToken = ''

export interface ApiSessionRecoveryResult {
  previousUserId?: string
  userId: string
}

type ApiSessionRecoveryHandler = () => Promise<ApiSessionRecoveryResult>

let apiSessionRecoveryHandler: ApiSessionRecoveryHandler | null = null
let apiSessionRecoveryPromise: Promise<ApiSessionRecoveryResult> | null = null

export const setApiSessionToken = (token: string) => {
  apiSessionToken = token || ''
}

// 只在微信开发版注入回归入口，用于稳定验证“401 后自动恢复”。
// 体验版和正式版不会暴露该方法，也不会允许外部读取真实 token。
try {
  const envVersion = typeof wx !== 'undefined'
    ? wx.getAccountInfoSync?.()?.miniProgram?.envVersion
    : ''
  if (envVersion === 'develop') {
    wx.__pincoExpireSessionForTest = () => {
      apiSessionToken = 'expired-session-for-devtools-test'
    }
  }
} catch (error) {
  console.warn('[Session] devtools expiry hook unavailable', error)
}

export const setApiSessionRecoveryHandler = (handler: ApiSessionRecoveryHandler | null) => {
  apiSessionRecoveryHandler = handler
}

class ApiResponseError extends Error {
  statusCode: number

  constructor(message: string, statusCode: number) {
    super(message)
    this.name = 'ApiResponseError'
    this.statusCode = statusCode
  }
}

const getErrorMessage = (data: any, fallback: string) => {
  const detail = data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => typeof item?.msg === 'string' ? item.msg : '')
      .filter(Boolean)
    if (messages.length > 0) return messages.join('；')
  }
  if (typeof data?.message === 'string' && data.message.trim()) return data.message
  return fallback
}

export const canUseCallContainer = () => {
  return isWeapp && typeof wx !== 'undefined' && wx.cloud && typeof wx.cloud.callContainer === 'function'
}

const recoverApiSession = async () => {
  if (!apiSessionRecoveryHandler) {
    throw new ApiResponseError('用户会话已过期，请重新进入小程序', 401)
  }
  if (!apiSessionRecoveryPromise) {
    apiSessionToken = ''
    apiSessionRecoveryPromise = apiSessionRecoveryHandler().finally(() => {
      apiSessionRecoveryPromise = null
    })
  }
  return apiSessionRecoveryPromise
}

const remapRecoveredIdentity = (
  path: string,
  data: Record<string, unknown> | undefined,
  recovery: ApiSessionRecoveryResult
) => {
  const previousUserId = recovery.previousUserId || ''
  const replaceClaim = (value: unknown) => (
    !previousUserId || String(value || '') === previousUserId ? recovery.userId : value
  )
  const nextData = data ? { ...data } : data
  if (nextData && Object.prototype.hasOwnProperty.call(nextData, 'user_id')) {
    nextData.user_id = replaceClaim(nextData.user_id)
  }
  if (nextData && Object.prototype.hasOwnProperty.call(nextData, 'expert_user_id')) {
    nextData.expert_user_id = replaceClaim(nextData.expert_user_id)
  }

  let nextPath = path
  if (previousUserId) {
    const encodedPrevious = encodeURIComponent(previousUserId)
    const encodedNext = encodeURIComponent(recovery.userId)
    nextPath = nextPath
      .replace(new RegExp(`([?&]user_id=)${encodedPrevious}(?=&|$)`, 'g'), `$1${encodedNext}`)
      .replace(new RegExp(`([?&]expert_user_id=)${encodedPrevious}(?=&|$)`, 'g'), `$1${encodedNext}`)
  }
  return { path: nextPath, data: nextData }
}

export const apiUploadFile = async <T>(
  path: string,
  filePath: string,
  filename: string,
  formData: Record<string, string> = {}
): Promise<T> => {
  if (!filePath || !filename) {
    throw new Error('文件路径或文件名不能为空')
  }

  const fs = Taro.getFileSystemManager()

  // 临时文件路径（wxfile://、http://tmp/ 等）必须原样传给微信文件系统。
  // 之前先去掉协议会导致真实设备上读不到刚选择的图片/文件。
  try {
    const info = await Taro.getFileInfo({ filePath })
    const maxSize = 4 * 1024 * 1024
    if ((info as any).size > maxSize) {
      throw new Error('文件不能超过 4MB，请压缩后再上传')
    }
  } catch (error: any) {
    const message = String(error?.errMsg || error?.message || '')
    if (message.includes('不能超过')) throw error
    // 个别基础库不支持 getFileInfo；后续 readFile 仍会给出真实错误。
    console.warn('[Upload] getFileInfo skipped', message)
  }

  const fileContent = await new Promise<string>((resolve, reject) => {
    fs.readFile({
      filePath,
      encoding: 'base64',
      success: (res) => {
        console.info('[Upload] file read success, size=', (res.data as string).length)
        resolve(res.data as string)
      },
      fail: (err) => {
        console.error('[Upload] readFile failed', err)
        reject(new Error(`读取文件失败: ${err.errMsg || '未知错误'}`))
      }
    })
  })

  const data: Record<string, unknown> = {
    filename,
    content: fileContent,
    ...formData
  }

  return apiRequest<T>(path, 'POST', data)
}

export const apiRequest = async <T>(
  path: string,
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'GET',
  data?: Record<string, unknown>
): Promise<T> => {
  return apiRequestInternal<T>(path, method, data, true)
}

const apiRequestInternal = async <T>(
  path: string,
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  data: Record<string, unknown> | undefined,
  allowSessionRecovery: boolean
): Promise<T> => {
  const useCallContainer = canUseCallContainer()

  if (useCallContainer) {
    console.info('[API] callContainer', method, path, 'env=', CLOUD_ENV, 'service=', CLOUD_SERVICE)
    try {
      const res = await wx.cloud.callContainer({
        config: { env: CLOUD_ENV },
        path,
        header: {
          'X-WX-SERVICE': CLOUD_SERVICE,
          'Content-Type': 'application/json',
          ...(apiSessionToken ? { 'X-Pinco-Session': apiSessionToken } : {}),
        },
        method,
        data
      })

      if (res.statusCode >= 400) {
        console.error('[API] callContainer failed', path, res)
        if (res.statusCode === 401 && allowSessionRecovery && path !== '/api/v1/miniapp/bootstrap') {
          console.warn('[API] session expired, recovering once', path)
          const recovery = await recoverApiSession()
          const retry = remapRecoveredIdentity(path, data, recovery)
          return apiRequestInternal<T>(retry.path, method, retry.data, false)
        }
        throw new ApiResponseError(getErrorMessage(res.data, '服务暂时不可用'), res.statusCode)
      }
      console.info('[API] callContainer success', path, 'status=', res.statusCode)
      return res.data as T
    } catch (callErr: any) {
      // 后端已经明确返回了业务错误（如 ASR 未配置），公网重试只会重复提交。
      // 只有 callContainer 链路本身异常时才切换到 Taro.request。
      if (callErr instanceof ApiResponseError) throw callErr
      console.warn('[API] callContainer exception, will try Taro.request', path, callErr?.errMsg || callErr?.message || callErr)
    }
  }

  console.info('[API] Taro.request', method, path, 'useCallContainer=', useCallContainer, 'NODE_ENV=', process.env.NODE_ENV)

  // H5 / 其他环境 / callContainer失败回退：使用普通 HTTP 请求
  const baseUrl = getApiBaseUrl()
  console.info('[API] request', method, `${baseUrl}${path}`)
  const response = await Taro.request<T>({
    url: `${baseUrl}${path}`,
    method,
    data,
    timeout: 30000,
    header: {
      'Content-Type': 'application/json',
      ...(apiSessionToken ? { 'X-Pinco-Session': apiSessionToken } : {}),
    }
  })
  if (response.statusCode >= 400) {
    console.error('[API] request failed', path, response)
    if (response.statusCode === 401 && allowSessionRecovery && path !== '/api/v1/miniapp/bootstrap') {
      console.warn('[API] session expired, recovering once', path)
      const recovery = await recoverApiSession()
      const retry = remapRecoveredIdentity(path, data, recovery)
      return apiRequestInternal<T>(retry.path, method, retry.data, false)
    }
    throw new ApiResponseError(getErrorMessage(response.data, '服务暂时不可用'), response.statusCode)
  }
  return response.data
}
