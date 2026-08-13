import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Image, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import classnames from 'classnames'
import styles from './index.module.scss'
import { usePincoStore } from '@/store/usePincoStore'
import { ConversationScenario, JobProgressItem, MessageItem } from '@/types/pinco'
import { getApiBaseUrl, apiUploadFile } from '@/services/api'
import { buildConversationTitle } from '@/utils/format'

const promptMap: Record<ConversationScenario, string> = {
  general: '你先根据我现在的情况，帮我判断今天最值得先做的一步。',
  resume: '我想做一轮简历诊断，请先问我最关键的背景信息。',
  interview: '帮我开始一轮模拟面试，从自我介绍开始。',
  emotion: '我最近在求职里有点内耗，你先接住我的情绪，再给我两个今天能做的动作。',
  expert: '请帮我生成一份专家连线前的 15 分钟备战清单。',
  garden: '请把我刚看的内容转成今天就能做的动作清单。',
  jd: '请帮我解读这段岗位描述，提取核心要求、面试重点和谈薪建议。'
}

type ChatAction = { label: string; prompt?: string; kind?: 'prompt' | 'resume' | 'jd' | 'interview' | 'progress' | 'bind' | 'review' | 'search' }

const quickStartCards: Array<{ title: string; desc: string; scenario: ConversationScenario; kind?: ChatAction['kind']; prompt: string }> = [
  { title: '简历诊断', desc: '上传/粘贴简历，直接看怎么改', scenario: 'resume', kind: 'resume', prompt: promptMap.resume },
  { title: 'JD 解读', desc: '拆岗位要求、面试重点和薪资信号', scenario: 'jd', kind: 'jd', prompt: promptMap.jd },
  { title: '模拟面试', desc: '按目标岗位追问并给复盘', scenario: 'interview', kind: 'interview', prompt: promptMap.interview },
  { title: '搜岗位', desc: '只返回带可打开来源链接的结果', scenario: 'general', kind: 'search', prompt: '' },
  { title: '求职进度', desc: '把投递、面试、复盘沉淀下来', scenario: 'general', kind: 'progress', prompt: '帮我整理现在的求职进度，并告诉我今天最该推进哪一步。' }
]

const scenarioTabs: Array<{ label: string; scenario: ConversationScenario; icon: string; isSearch?: boolean }> = [
  { label: '简历诊断', scenario: 'resume', icon: '📄' },
  { label: '职业规划', scenario: 'general', icon: '🎯' },
  { label: '模拟面试', scenario: 'interview', icon: '🎤' },
  { label: '情感树洞', scenario: 'emotion', icon: '🌰' },
  { label: '搜岗位', scenario: 'general', icon: '🔍', isSearch: true },
]

const pickPriorityJob = (jobs: JobProgressItem[]) => jobs.find((job) => ['interview2', 'interview1', 'hr'].includes(job.status)) || jobs[0]

type PrivacyResolve = (option: {
  event: 'exposureAuthorization' | 'agree' | 'disagree'
  buttonId?: string
}) => void

const PRIVACY_AGREE_BUTTON_ID = 'pinco-privacy-agree'
let privacyListenerBound = false
let pendingPrivacyResolve: PrivacyResolve | null = null
let showPrivacyPrompt: ((referrer: string) => void) | null = null

function ensurePrivacyListener() {
  if (privacyListenerBound || !Taro.onNeedPrivacyAuthorization) return
  privacyListenerBound = true
  Taro.onNeedPrivacyAuthorization((resolve, eventInfo) => {
    console.info('[Privacy] authorization requested', eventInfo)
    pendingPrivacyResolve = resolve
    resolve({ event: 'exposureAuthorization' })
    showPrivacyPrompt?.(eventInfo?.referrer || '')
  })
}

function formatTime(ts: number) {
  const diff = Date.now() - ts
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const ConversationPage: React.FC = () => {
  const [draft, setDraft] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [recordHint, setRecordHint] = useState('')
  const [showInterviewInput, setShowInterviewInput] = useState(false)
  const [interviewInput, setInterviewInput] = useState('')
  const [interviewDuration, setInterviewDuration] = useState<5 | 10 | 20 | 30>(10)
  const [interviewCompany, setInterviewCompany] = useState('')
  const [interviewRound, setInterviewRound] = useState('')
  const [interviewDate, setInterviewDate] = useState('')
  const [interviewAnxiety, setInterviewAnxiety] = useState('')
  const [interviewPracticeStyle, setInterviewPracticeStyle] = useState<'warmup' | 'real' | 'pressure'>('real')
  const [interviewJobId, setInterviewJobId] = useState('')
  const [interviewSourcePostId, setInterviewSourcePostId] = useState('')
  const [interviewJdText, setInterviewJdText] = useState('')
  const messages = usePincoStore((state) => state.messages)
  const conversationMeta = usePincoStore((state) => state.conversationMeta)
  const isSending = usePincoStore((state) => state.isSending)
  const isStreaming = usePincoStore((state) => state.isStreaming)
  const streamingContent = usePincoStore((state) => state.streamingContent)
  const interviewState = usePincoStore((state) => state.interviewState)
  const jobProgress = usePincoStore((state) => state.jobProgress)
  const pendingJobEvent = usePincoStore((state) => state.pendingJobEvent)
  const confirmPendingJobEvent = usePincoStore((state) => state.confirmPendingJobEvent)
  const dismissPendingJobEvent = usePincoStore((state) => state.dismissPendingJobEvent)
  const bindLatestMaterialToJob = usePincoStore((state) => state.bindLatestMaterialToJob)
  const openConversation = usePincoStore((state) => state.openConversation)
  const sendMessage = usePincoStore((state) => state.sendMessage)
  const seedConversation = usePincoStore((state) => state.seedConversation)
  const regenerateMessage = usePincoStore((state) => state.regenerateMessage)
  const startInterview = usePincoStore((state) => state.startInterview)
  const requestInterviewRescue = usePincoStore((state) => state.requestInterviewRescue)
  const endInterview = usePincoStore((state) => state.endInterview)
  const jobSearchResults = usePincoStore((state) => state.jobSearchResults)
  const searchJobs = usePincoStore((state) => state.searchJobs)
  const conversationHistory = usePincoStore((state) => state.conversationHistory)
  const createNewConversation = usePincoStore((state) => state.createNewConversation)
  const switchToConversation = usePincoStore((state) => state.switchToConversation)
  const deleteConversation = usePincoStore((state) => state.deleteConversation)
  const loadConversationHistory = usePincoStore((state) => state.loadConversationHistory)
  const supportFeedbackCheckInId = usePincoStore((state) => state.supportFeedbackCheckInId)
  const submitSupportFeedback = usePincoStore((state) => state.submitSupportFeedback)
  const scrollRef = useRef<any>(null)

  const [showHistory, setShowHistory] = useState(false)
  const [privacyPromptVisible, setPrivacyPromptVisible] = useState(false)
  const [privacyReferrer, setPrivacyReferrer] = useState('')
  const [voiceMessageMode, setVoiceMessageMode] = useState(false)
  const [messageFeedbacks, setMessageFeedbacks] = useState<Record<string, 'like' | 'dislike'>>({})
  const [showShareMenu, setShowShareMenu] = useState(false)
  const [shareTargetMessage, setShareTargetMessage] = useState<MessageItem | null>(null)
  const [messageActionTarget, setMessageActionTarget] = useState<MessageItem | null>(null)
  const [selectionMessage, setSelectionMessage] = useState<MessageItem | null>(null)
  const [selectionRange, setSelectionRange] = useState({ start: 0, end: 0 })
  const [draftFocused, setDraftFocused] = useState(false)
  const [draftSelection, setDraftSelection] = useState({ start: -1, end: -1 })

  useEffect(() => {
    loadConversationHistory()
  }, [])

  useEffect(() => {
    showPrivacyPrompt = (referrer) => {
      setPrivacyReferrer(referrer)
      setPrivacyPromptVisible(true)
    }
    ensurePrivacyListener()
    return () => {
      showPrivacyPrompt = null
    }
  }, [])

  const declinePrivacyAuthorization = () => {
    console.info('[Privacy] user declined')
    pendingPrivacyResolve?.({ event: 'disagree' })
    pendingPrivacyResolve = null
    setPrivacyPromptVisible(false)
  }

  const agreePrivacyAuthorization = () => {
    if (!pendingPrivacyResolve) {
      setPrivacyPromptVisible(false)
      return
    }
    console.info('[Privacy] user agreed with verified button')
    pendingPrivacyResolve({ event: 'agree', buttonId: PRIVACY_AGREE_BUTTON_ID })
    pendingPrivacyResolve = null
    setPrivacyPromptVisible(false)
  }

  const recorderManager = useMemo(() => {
    if (process.env.TARO_ENV === 'weapp') {
      return Taro.getRecorderManager()
    }
    return null
  }, [])

  useLoad((options) => {
    const scenario = ((options?.scenario as ConversationScenario) || 'general')
    const prompt = typeof options?.prompt === 'string' ? decodeURIComponent(options.prompt) : ''
    const jdText = typeof options?.jd_text === 'string' ? decodeURIComponent(options.jd_text) : ''
    const position = typeof options?.position === 'string' ? decodeURIComponent(options.position) : ''
    const company = typeof options?.company === 'string' ? decodeURIComponent(options.company) : ''
    const jobId = typeof options?.job_id === 'string' ? decodeURIComponent(options.job_id) : ''
    const sourcePostId = typeof options?.source_post_id === 'string' ? decodeURIComponent(options.source_post_id) : ''
    const duration = Number(options?.duration)
    openConversation(scenario, '把问题交给学姐一起拆')
    Taro.setNavigationBarTitle({ title: buildConversationTitle(scenario) })
    if (scenario === 'interview' && (position || jobId || sourcePostId)) {
      setInterviewInput(position || 'AI 求职面试')
      setInterviewCompany(company)
      setInterviewJobId(jobId)
      setInterviewSourcePostId(sourcePostId)
      setInterviewJdText(jdText)
      if ([5, 10, 20, 30].includes(duration)) setInterviewDuration(duration as 5 | 10 | 20 | 30)
      setShowInterviewInput(true)
    } else if (jdText) {
      jdAnalyze(jdText)
    } else if (prompt) {
      seedConversation(scenario, prompt, '把问题交给学姐一起拆')
    }
  })

  useEffect(() => {
  }, [messages.length, streamingContent])

  const hasMessages = messages.length > 1 // welcome message counts as 1
  const latestMessage = [...messages].reverse().find((item) => item.id !== 'welcome')
  const priorityJob = pickPriorityJob(jobProgress)

  const handleCopyMessage = (content: string) => {
    const text = String(content || '').trim()
    if (!text) {
      Taro.showToast({ title: '内容为空，无法复制', icon: 'none' })
      return
    }

    // 始终走 Taro 适配层；直接调用全局 wx 在开发者工具/H5 兼容层会出现
    // “回调成功但剪贴板为空”的情况。
    Taro.setClipboardData({
      data: text,
      success: async () => {
        try {
          const result = await Taro.getClipboardData()
          if (result.data !== text) throw new Error('clipboard content mismatch')
          console.info('[Copy] verified, length=', text.length)
          Taro.showToast({ title: '已复制', icon: 'success' })
        } catch (error) {
          console.error('[Copy] verification failed', error)
          Taro.showToast({ title: '复制未完成，可长按正文复制', icon: 'none', duration: 2500 })
        }
      },
      fail: (err) => {
        console.error('[Copy] failed', err)
        Taro.showToast({ title: '复制失败，可长按正文复制', icon: 'none', duration: 2500 })
      }
    })
  }

  const handleFeedback = (messageId: string, type: 'like' | 'dislike') => {
    setMessageFeedbacks((prev) => ({ ...prev, [messageId]: type }))
    Taro.showToast({ title: type === 'like' ? '感谢点赞' : '已收到反馈', icon: 'none' })
  }

  const handleShare = (message: MessageItem) => {
    setShareTargetMessage(message)
    setShowShareMenu(true)
  }

  const handleShareOption = (option: 'link' | 'wechat') => {
    if (!shareTargetMessage) return
    if (option === 'link') {
      Taro.setClipboardData({
        data: shareTargetMessage.content,
        success: () => Taro.showToast({ title: '内容已复制', icon: 'success' })
      })
    } else if (option === 'wechat') {
      Taro.showShareMenu({ withShareTicket: true })
      Taro.showToast({ title: '请使用右上角菜单转发', icon: 'none' })
    }
    setShowShareMenu(false)
  }

  const handleSelectAllDraft = () => {
    if (!draft) return
    setDraftFocused(false)
    setDraftSelection({ start: 0, end: draft.length })
    setTimeout(() => setDraftFocused(true), 30)
  }

  const handleOpenTextSelection = (message: MessageItem) => {
    setMessageActionTarget(null)
    setSelectionRange({ start: 0, end: message.content.length })
    setSelectionMessage(message)
  }

  const handleCopySelection = () => {
    if (!selectionMessage) return
    const start = Math.min(selectionRange.start, selectionRange.end)
    const end = Math.max(selectionRange.start, selectionRange.end)
    const selected = selectionMessage.content.slice(start, end) || selectionMessage.content
    handleCopyMessage(selected)
  }

  const handleRegenerate = async (message: MessageItem) => {
    setMessageActionTarget(null)
    try {
      await regenerateMessage(message.id)
      Taro.showToast({ title: '已重新生成', icon: 'success' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '重新生成失败，请重试', icon: 'none', duration: 2500 })
    }
  }

  const handleSend = async () => {
    if (!draft.trim()) return
    const value = draft
    setDraft('')

    const searchTriggers = /找|搜|推荐|有没有|想看|看看|求职|招聘|岗位|职位|工作|机会|实习/
    const jobKeywords = /AI|产品|前端|后端|Java|Python|数据|算法|设计|运营|市场|销售|人力|财务|测试|运维|架构|移动|iOS|Android|Go|C\+\+|全栈|大模型|AIGC|LLM|NLP|CV|推荐|搜索|广告|增长|商业化|出海|电商|社交|内容|社区|SaaS|B端|C端|金融|教育|医疗|游戏/
    let searchContext = ''

    // 情绪场景下不触发岗位搜索
    if (conversationMeta.scenario !== 'emotion' && searchTriggers.test(value) && jobKeywords.test(value)) {
      const cityMatch = value.match(/(?:北京|上海|广州|深圳|杭州|成都|武汉|西安|南京|苏州|长沙|重庆|厦门|青岛|大连|天津|合肥|郑州|济南|沈阳|珠海)/)
      let query = value
        .replace(/帮我|请|能不能|可以|想|要|我|你|给|在|的|了|吗|呢|啊|吧|一下|一些|有没有|推荐|搜索|找|看看|想看|什么|哪些|那些|这个|那个|相关|合适|好|不错|新|最新|近期|最近|工作|岗位|职位|招聘|机会|实习/g, '')
        .trim()
      if (!query || query.length < 2) {
        const kwMatch = value.match(jobKeywords)
        query = kwMatch ? kwMatch[0] : '产品经理'
      }
      await searchJobs(query, cityMatch?.[0])
      const results = usePincoStore.getState().jobSearchResults
      if (results.length > 0) {
        const jobLines = results.slice(0, 6).map((j, i) =>
          `${i + 1}. 【${j.source || j.platform || '网络'}】${j.title} - ${j.company} · ${j.location}${j.salary ? ' · ' + j.salary : ''}\n   ${j.summary}\n   来源链接：${j.url}`
        ).join('\n')
        searchContext = `\n\n[系统提示：以下是检索接口刚返回的 ${results.length} 条带可打开来源链接的岗位结果。只能依据链接和摘要推荐，不要扩写公司、薪资或招聘状态：]\n${jobLines}`
      }
    }

    await sendMessage(value + searchContext)
  }

  const resumeUpload = usePincoStore((state) => state.resumeUpload)
  const jdAnalyze = usePincoStore((state) => state.jdAnalyze)
  const [showActionMenu, setShowActionMenu] = useState(false)
  const [showJDInput, setShowJDInput] = useState(false)
  const [jdInputText, setJdInputText] = useState('')

  const handleChatAction = async (item: { label?: string; prompt?: string; kind?: ChatAction['kind'] }) => {
    if (item.kind === 'search') {
      Taro.navigateTo({ url: '/pages/job-search/index' })
      return
    }
    if (item.kind === 'resume') {
      await handleResumeUpload()
      return
    }
    if (item.kind === 'jd') {
      setShowJDInput(true)
      return
    }
    if (item.kind === 'interview') {
      setShowInterviewInput(true)
      return
    }
    if (item.kind === 'progress') {
      Taro.switchTab({ url: '/pages/mine/index' })
      return
    }
    if (item.kind === 'review') {
      endInterview()
      return
    }
    if (item.kind === 'bind') {
      const job = priorityJob
      if (!job) {
        Taro.showToast({ title: '先在对话里提到一个岗位，我来帮你记录', icon: 'none' })
        return
      }
      const material = latestMessage?.type === 'jd' ? 'jdBound' : latestMessage?.type === 'interview' ? 'reviewBound' : 'resumeBound'
      bindLatestMaterialToJob(job.id, material)
      return
    }
    if (item.prompt?.includes('模拟面试')) {
      setShowInterviewInput(true)
      return
    }
    if (item.prompt) {
      await seedConversation(conversationMeta.scenario, item.prompt, conversationMeta.subtitle)
    }
  }

  const handleStartInterview = async () => {
    if (!interviewInput.trim()) return
    await startInterview(interviewInput.trim(), interviewDuration, {
      company: interviewCompany.trim(),
      interviewRound: interviewRound.trim(),
      interviewDate: interviewDate.trim(),
      anxietyFocus: interviewAnxiety.trim(),
      practiceStyle: interviewPracticeStyle,
      jobId: interviewJobId || undefined,
      sourcePostId: interviewSourcePostId || undefined,
      jdText: interviewJdText || undefined,
    })
    setShowInterviewInput(false)
    setInterviewInput('')
    setInterviewJobId('')
    setInterviewSourcePostId('')
    setInterviewJdText('')
  }

  const handleResumeUpload = async () => {
    setShowActionMenu(false)
    try {
      const res = await Taro.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['pdf', 'docx'],
      })
      const filePath = res.tempFiles[0].path
      const fileName = res.tempFiles[0].name
      if (filePath) {
        await resumeUpload(filePath, fileName)
      }
    } catch (e: any) {
      const errMsg = e?.errMsg || ''
      if (errMsg.includes('cancel')) {
        console.info('[Resume] file selection canceled')
        return
      }
      console.error('[Resume] chooseMessageFile failed', e)
      if (errMsg.includes('not supported')) {
        Taro.showToast({ title: '当前微信版本不支持文件选择，请升级后重试', icon: 'none', duration: 3000 })
      } else {
        Taro.showToast({ title: '选择文件失败：' + errMsg, icon: 'none', duration: 3000 })
      }
    }
  }

  const saveMessages = usePincoStore((state) => state.saveMessages)

  const handleImageSend = async () => {
    setShowActionMenu(false)
    try {
      const res = await Taro.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera']
      })

      const filePath = res.tempFilePaths?.[0]
      if (!filePath) return

      // chooseImage 的 compressed 只保证微信进行压缩，并不保证一定低于后端
      // 4MB 限制。临界大图再压一轮，避免用户选完图才得到无法上传的错误。
      let uploadPath = filePath
      try {
        const info = await Taro.getFileInfo({ filePath })
        if ((info as any).size > 3.5 * 1024 * 1024) {
          Taro.showLoading({ title: '正在压缩图片...' })
          const compressed = await Taro.compressImage({ src: filePath, quality: 65 })
          uploadPath = compressed.tempFilePath || filePath
        }
      } catch (compressError) {
        console.warn('[Image] pre-upload compression skipped', compressError)
      }

      // Upload image to backend via base64 + callContainer
      Taro.showLoading({ title: '上传中...' })
      const data = await apiUploadFile<any>('/api/v1/image/upload', uploadPath, uploadPath.split('/').pop() || 'image.jpg', { type: 'image' })
      Taro.hideLoading()
      Taro.showToast({ title: data.message || '图片已校验', icon: 'none', duration: 3000 })
      // 当前 DeepSeek 对话模型不接收视觉输入；保留微信本地预览，并把
      // 能力边界写进消息，禁止模型根据文件名猜测图片内容。
      await sendMessage(
        `我上传了一张图片「${data.filename || filePath.split('/').pop() || '图片'}」。系统只完成了文件完整性校验，当前模型没有读取画面的能力。请不要猜测或描述图片内容；请告诉我怎样把其中的文字粘贴出来，再继续做 JD、简历或面试分析。`,
        'image',
        { mediaUrl: filePath, fileName: data.filename }
      )
    } catch (e: any) {
      Taro.hideLoading()
      const errMsg = e?.errMsg || e?.message || ''
      if (errMsg.includes('cancel')) {
        console.info('[Image] selection canceled')
        return
      }
      console.error('[Image] upload failed', e)
      Taro.showToast({ title: '图片上传失败：' + (errMsg || '网络异常'), icon: 'none', duration: 3000 })
    }
  }

  const handleJDSubmit = async () => {
    if (!jdInputText.trim()) return
    setShowJDInput(false)
    const text = jdInputText
    setJdInputText('')
    await jdAnalyze(text)
  }

  const recordTimeoutRef = useRef<any>(null)
  const isRecordingRef = useRef(false)
  const recordStartPendingRef = useRef(false)
  const nativeRecorderStartedRef = useRef(false)
  const discardRecordingRef = useRef(false)
  // 隐私授权弹窗出现时，用户可能已经松开按钮。单独记录按压状态，
  // 避免授权完成后才开始录音，从而留下一个无法松开的录音会话。
  const recordPressActiveRef = useRef(false)
  const recordTouchStartedAtRef = useRef(0)
  const tapRecordingModeRef = useRef(false)
  const lastVoiceTouchEndAtRef = useRef(0)
  const voiceMessageModeRef = useRef(false)

  useEffect(() => {
    voiceMessageModeRef.current = voiceMessageMode
  }, [voiceMessageMode])

  const ensurePrivacyAuthorized = async () => {
    if (process.env.TARO_ENV !== 'weapp' || typeof wx === 'undefined') return true
    if (typeof wx.getPrivacySetting !== 'function') return true

    return new Promise<boolean>((resolve) => {
      wx.getPrivacySetting({
        success: (setting: { needAuthorization?: boolean }) => {
          if (!setting.needAuthorization) {
            resolve(true)
            return
          }
          if (typeof wx.requirePrivacyAuthorize !== 'function') {
            Taro.showToast({ title: '请先同意隐私保护指引后使用录音', icon: 'none', duration: 2500 })
            resolve(false)
            return
          }
          wx.requirePrivacyAuthorize({
            success: () => resolve(true),
            fail: (error: any) => {
              console.warn('[Privacy] voice authorization declined', error)
              Taro.showToast({ title: '未同意隐私保护指引，无法录音', icon: 'none', duration: 2500 })
              resolve(false)
            }
          })
        },
        fail: (error: any) => {
          // 获取隐私状态失败时不应把按钮卡住，继续让 RecorderManager 给出实际错误。
          console.warn('[Privacy] getPrivacySetting failed', error)
          resolve(true)
        }
      })
    })
  }

  useEffect(() => {
    if (!recorderManager) return

    recorderManager.onStart(() => {
      recordStartPendingRef.current = false
      nativeRecorderStartedRef.current = true
      // 微信的 onStart 可能晚于 touchend。短按已经切换到点按录音模式时，
      // 即使手指已经松开也必须保留录音，等待用户再次点按发送。
      if (!recordPressActiveRef.current && !tapRecordingModeRef.current) {
        console.info('[Voice] record started after release, discarding')
        discardRecordingRef.current = true
        isRecordingRef.current = true
        setIsRecording(false)
        setRecordHint('')
        try { recorderManager.stop() } catch {}
        return
      }
      console.info('[Voice] record started')
      discardRecordingRef.current = false
      isRecordingRef.current = true
      setIsRecording(true)
    })

    recorderManager.onError((err) => {
      console.error('[Voice] record error', err)
      isRecordingRef.current = false
      recordStartPendingRef.current = false
      nativeRecorderStartedRef.current = false
      recordPressActiveRef.current = false
      tapRecordingModeRef.current = false
      setIsRecording(false)
      setRecordHint('')
      if (recordTimeoutRef.current) {
        clearTimeout(recordTimeoutRef.current)
        recordTimeoutRef.current = null
      }
      Taro.showToast({ title: '录音出错，请重试', icon: 'none' })
    })

    recorderManager.onStop(async (res) => {
      const shouldDiscard = discardRecordingRef.current
      discardRecordingRef.current = false
      isRecordingRef.current = false
      recordStartPendingRef.current = false
      nativeRecorderStartedRef.current = false
      recordPressActiveRef.current = false
      tapRecordingModeRef.current = false
      setIsRecording(false)
      setRecordHint('')
      if (recordTimeoutRef.current) {
        clearTimeout(recordTimeoutRef.current)
        recordTimeoutRef.current = null
      }
      if (shouldDiscard) {
        console.info('[Voice] discarded recording released during authorization')
        return
      }
      if (!res.tempFilePath) {
        Taro.showToast({ title: '录音失败，请重试', icon: 'none' })
        return
      }
      Taro.showToast({ title: voiceMessageModeRef.current ? '正在发送…' : '正在识别…', icon: 'loading', duration: 10000, mask: false })
      try {
        const data = await apiUploadFile<any>('/api/v1/voice/upload', res.tempFilePath, `voice_${Date.now()}.mp3`, { type: 'voice' })
        if (voiceMessageModeRef.current) {
          setVoiceMessageMode(false)
          if (data.text) {
            await sendMessage(data.text, 'voice')
          } else {
            Taro.showToast({ title: '没听清，再说一次', icon: 'none' })
          }
        } else {
          if (data.text) {
            setDraft((prev) => prev + data.text)
          } else {
            Taro.showToast({ title: '没听清，再说一次', icon: 'none' })
          }
        }
      } catch (e: any) {
        console.error('[Voice] upload failed', e)
        if (voiceMessageModeRef.current) setVoiceMessageMode(false)
        const errMsg = e?.errMsg || e?.message || ''
        if (errMsg.includes('cancel')) {
          return
        }
        Taro.showToast({ title: '语音识别失败：' + (errMsg || '网络异常'), icon: 'none', duration: 3000 })
      } finally {
        Taro.hideToast()
      }
    })

    return () => {
      if (recordTimeoutRef.current) {
        clearTimeout(recordTimeoutRef.current)
        recordTimeoutRef.current = null
      }
      // RecorderManager 是全局单例。页面卸载时必须移除回调，
      // 否则再次进入会重复上传并把页面留在录音态。
      recorderManager.offStart?.()
      recorderManager.offError?.()
      recorderManager.offStop?.()
    }
  }, [recorderManager])

  const startRecord = async () => {
    // 点按录音模式下，再按一次即停止并发送。长按模式仍然走 touchend。
    if (recorderManager && isRecordingRef.current && tapRecordingModeRef.current) {
      tapRecordingModeRef.current = false
      recordPressActiveRef.current = false
      isRecordingRef.current = false
      setIsRecording(false)
      setRecordHint('')
      if (nativeRecorderStartedRef.current) {
        try { recorderManager.stop() } catch (error) { console.error('[Voice] stop failed', error) }
      } else {
        // 用户极快地再次点按时，原生录音可能尚未触发 onStart。
        // 标记丢弃，等 onStart 到达后再安全停止，避免留下后台录音。
        discardRecordingRef.current = true
      }
      return
    }
    if (!recorderManager || isRecordingRef.current || recordStartPendingRef.current) {
      if (!recorderManager) Taro.showToast({ title: '当前环境不支持语音', icon: 'none' })
      return
    }
    recordTouchStartedAtRef.current = Date.now()
    recordPressActiveRef.current = true
    recordStartPendingRef.current = true
    nativeRecorderStartedRef.current = false
    discardRecordingRef.current = false
    const authorized = await ensurePrivacyAuthorized()
    // 用户在隐私弹窗期间松开，或授权被拒绝时，绝不能再启动录音。
    if (!authorized) {
      recordStartPendingRef.current = false
      recordPressActiveRef.current = false
      tapRecordingModeRef.current = false
      return
    }
    if (isRecordingRef.current) return
    if (!recordPressActiveRef.current && !tapRecordingModeRef.current) {
      recordStartPendingRef.current = false
      Taro.showToast({ title: '已同意，请再次按住录音', icon: 'none', duration: 2000 })
      return
    }
    setRecordHint(voiceMessageMode ? '正在录音，松开发送语音消息' : '正在录音，松开发送')
    isRecordingRef.current = true
    try {
      recorderManager.start({
        duration: 60000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 48000,
        format: 'mp3'
      })
      // 安全超时：如果 65 秒内没有收到 onStop，强制重置状态
      if (recordTimeoutRef.current) clearTimeout(recordTimeoutRef.current)
      recordTimeoutRef.current = setTimeout(() => {
        console.warn('[Voice] safety timeout triggered')
        isRecordingRef.current = false
        recordPressActiveRef.current = false
        tapRecordingModeRef.current = false
        setIsRecording(false)
        setRecordHint('')
        try { recorderManager.stop() } catch {}
      }, 65000)
    } catch (e) {
      console.error('[Voice] start failed', e)
      isRecordingRef.current = false
      recordStartPendingRef.current = false
      nativeRecorderStartedRef.current = false
      recordPressActiveRef.current = false
      tapRecordingModeRef.current = false
      setIsRecording(false)
      setRecordHint('')
      Taro.showToast({ title: '启动录音失败', icon: 'none' })
    }
  }

  const stopRecord = () => {
    lastVoiceTouchEndAtRef.current = Date.now()
    if (!recorderManager) {
      recordPressActiveRef.current = false
      return
    }

    // 短点按不再立刻结束成一段空录音，而是切换为“再点一次发送”。
    // onStart 在开发者工具和首次授权时可能明显晚于 touchend，所以启动中的
    // 松手也要保留为点按录音，不能提前丢弃。
    const pressDuration = Date.now() - recordTouchStartedAtRef.current
    if (!tapRecordingModeRef.current && pressDuration < 1000 && (isRecordingRef.current || recordStartPendingRef.current)) {
      tapRecordingModeRef.current = true
      recordPressActiveRef.current = true
      setIsRecording(true)
      setRecordHint('正在录音，再点一次发送')
      return
    }

    if (!isRecordingRef.current && !recordStartPendingRef.current) {
      recordPressActiveRef.current = false
      return
    }

    tapRecordingModeRef.current = false
    recordPressActiveRef.current = false
    isRecordingRef.current = false
    setIsRecording(false)
    setRecordHint('')
    if (nativeRecorderStartedRef.current) {
      try {
        recorderManager.stop()
      } catch (e) {
        console.error('[Voice] stop failed', e)
      }
    } else {
      // 录音尚未真正启动，等 onStart 到达后由回调安全停止并丢弃。
      discardRecordingRef.current = true
    }
  }

  const handleVoiceClick = async () => {
    // 真机 touchend 后通常还会合成 click；这一次 click 必须忽略，
    // 否则刚松手结束的录音会被意外重新启动。
    if (Date.now() - lastVoiceTouchEndAtRef.current < 500) return
    if (isRecordingRef.current) {
      tapRecordingModeRef.current = true
      stopRecord()
      return
    }
    await startRecord()
    if (isRecordingRef.current) {
      tapRecordingModeRef.current = true
      recordPressActiveRef.current = true
      setRecordHint('正在录音，再点一次发送')
    }
  }

  const renderMessageContent = (content: string) => {
    // Simple markdown-like formatting
    const parts = content.split(/(\*\*.*?\*\*)/g)
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <Text key={i} className={styles.boldText}>{part.slice(2, -2)}</Text>
      }
      return <Text key={i}>{part}</Text>
    })
  }

  interface Recommendation {
    icon: string
    title: string
    subtitle: string
    action: () => void
  }

  const getRecommendations = (scenario: ConversationScenario): Recommendation[] => {
    const recs: Recommendation[] = []

    if (scenario === 'resume') {
      recs.push({
        icon: '📄',
        title: 'STAR法则实战手册',
        subtitle: '用数据说话，让简历脱颖而出',
        action: () => Taro.navigateTo({ url: '/pages/article/index?id=g5' }),
      })
      recs.push({
        icon: '👤',
        title: 'Sarah · 外企500强HRBP',
        subtitle: '简历精修 · 薪资谈判',
        action: () => Taro.switchTab({ url: '/pages/experts/index' }),
      })
    }

    if (scenario === 'interview') {
      recs.push({
        icon: '🎯',
        title: 'AI面试必背八股文',
        subtitle: '高频题拆解 + 回答框架',
        action: () => Taro.navigateTo({ url: '/pages/article/index?id=g1' }),
      })
      recs.push({
        icon: '🎤',
        title: '开始模拟面试',
        subtitle: 'AI面试官5轮实战演练',
        action: () => setShowInterviewInput(true),
      })
    }

    if (scenario === 'jd') {
      recs.push({
        icon: '📝',
        title: 'JD智能解读',
        subtitle: '拆解核心要求 + 隐性门槛',
        action: () => setShowJDInput(true),
      })
      recs.push({
        icon: '👤',
        title: '林深 · 前阿里P8面试官',
        subtitle: '技术面试 · 晋升答辩',
        action: () => Taro.switchTab({ url: '/pages/experts/index' }),
      })
    }

    if (scenario === 'emotion') {
      recs.push({
        icon: '🌰',
        title: '去树洞看看',
        subtitle: '大家都在经历类似的困惑',
        action: () => Taro.switchTab({ url: '/pages/hub/index' }),
      })
    }

    if (scenario === 'expert') {
      recs.push({
        icon: '📞',
        title: '预约专家咨询',
        subtitle: '大厂导师1v1针对性辅导',
        action: () => Taro.switchTab({ url: '/pages/experts/index' }),
      })
    }

    if (scenario === 'general') {
      recs.push({
        icon: '🔍',
        title: '搜岗位',
        subtitle: '发现匹配你的真实职位',
        action: () => Taro.switchTab({ url: '/pages/job-search/index' }),
      })
    }

    return recs.slice(0, 2)
  }

  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === 'assistant' && m.id !== 'welcome')
  const recommendations = lastAssistantMessage ? getRecommendations(conversationMeta.scenario) : []
  const privacyDescription = useMemo(() => {
    const referrer = privacyReferrer.toLowerCase()
    if (referrer.includes('record') || referrer.includes('privacyauthorize')) {
      return '仅当你主动按住麦克风时，Pinco 才会使用录音能力，用于把语音转换为文字。'
    }
    if (referrer.includes('chooseimage') || referrer.includes('choosemedia')) {
      return '仅当你主动选择或拍摄图片时，Pinco 才会读取这张图片，用于上传求职截图或简历图片。'
    }
    if (referrer.includes('choosemessagefile')) {
      return '仅当你主动选择文件时，Pinco 才会读取所选的 PDF 或 DOCX，用于简历诊断。'
    }
    if (referrer.includes('clipboard')) {
      return '仅当你主动点击“复制”时，Pinco 才会使用剪贴板，用于复制会话内容。'
    }
    return 'Pinco 只会在你主动触发当前功能时使用所需信息，并且仅用于完成本次操作。'
  }, [privacyReferrer])

  return (
    <View className={styles.page}>
      {/* 顶部场景 Tab 横排 —— 固定在顶部，不随对话滚动 */}
      <View className={styles.stickyHeader}>
        <View className={styles.scenarioTabBar}>
          {scenarioTabs.map((tab) => (
            <View
              key={tab.label}
              className={classnames(styles.scenarioTab, !tab.isSearch && conversationMeta.scenario === tab.scenario && styles.scenarioTabActive)}
              onClick={() => {
                if (tab.isSearch) {
                  Taro.navigateTo({ url: '/pages/job-search/index' })
                  return
                }
                openConversation(tab.scenario, tab.label)
                Taro.setNavigationBarTitle({ title: buildConversationTitle(tab.scenario) })
                const prompt = promptMap[tab.scenario]
                if (prompt) seedConversation(tab.scenario, prompt, tab.label)
              }}
            >
              <Text className={styles.scenarioTabIcon}>{tab.icon}</Text>
              <Text className={styles.scenarioTabLabel}>{tab.label}</Text>
            </View>
          ))}
        </View>

        {/* 对话操作栏 */}
        <View className={styles.actionBar}>
          <View className={styles.actionBarButton} onClick={createNewConversation}>
            <Text className={styles.actionBarIcon}>+</Text>
            <Text className={styles.actionBarLabel}>新建</Text>
          </View>
          <View className={styles.actionBarDivider} />
          <View className={styles.actionBarButton} onClick={() => setShowHistory(true)}>
            <Text className={styles.actionBarIcon}>📜</Text>
            <Text className={styles.actionBarLabel}>历史 {conversationHistory.length > 0 ? `(${conversationHistory.length})` : ''}</Text>
          </View>
        </View>
      </View>

      <ScrollView
        ref={scrollRef}
        className={styles.messageScroll}
        scrollY
        enhanced
        showScrollbar={false}
        scrollIntoView={hasMessages ? `msg-${messages.length - 1}` : undefined}
      >

        {/* 空状态引导 */}
        {!hasMessages && (
          <View className={styles.welcomeWrap}>
            <View className={styles.welcomeCard}>
              <Text className={styles.welcomeTitle}>{conversationMeta.title}</Text>
              <Text className={styles.welcomeDesc}>{conversationMeta.subtitle}</Text>
            </View>
            <View className={styles.quickGrid}>
              {quickStartCards.map((item) => (
                <View key={item.title} className={styles.quickItem} onClick={() => handleChatAction(item)}>
                  <Text className={styles.quickLabel}>{item.title}</Text>
                  <Text className={styles.quickDesc}>{item.desc}</Text>
                </View>
              ))}
            </View>
            <Text className={styles.welcomeTip}>也可以直接把求职状态告诉我，比如“昨天投了字节 AI 产品岗”。</Text>
          </View>
        )}

        {/* 消息列表 */}
        {messages.map((message, idx) => (
          <View
            key={message.id}
            id={`msg-${idx}`}
            className={classnames(styles.messageRow, message.role === 'user' && styles.messageRowUser)}
          >
            <View className={classnames(styles.avatar, message.role === 'user' ? styles.avatarUser : styles.avatarAssistant)}>
              <Text>{message.role === 'user' ? '我' : '姐'}</Text>
            </View>
            <View className={styles.messageContentWrap}>
              <View
                className={classnames(styles.messageBubble, message.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant)}
                onLongPress={message.role === 'assistant' && message.id !== 'welcome'
                  ? () => setMessageActionTarget(message)
                  : undefined}
              >
                <Text className={styles.messageContent} userSelect>
                  {renderMessageContent(message.content)}
                </Text>
                {message.type === 'image' && message.mediaUrl && (
                  <Image
                    className={styles.messageImage}
                    src={message.mediaUrl}
                    mode="widthFix"
                    onClick={() => Taro.previewImage({ urls: [message.mediaUrl!], current: message.mediaUrl })}
                  />
                )}
                {message.type === 'voice' && (
                  <View
                    className={styles.voiceBubble}
                    onClick={() => {
                      const innerAudioContext = Taro.createInnerAudioContext()
                      innerAudioContext.src = message.mediaUrl || ''
                      innerAudioContext.play()
                    }}
                  >
                    <Text className={styles.voiceIcon}>🎙️</Text>
                    <Text className={styles.voiceDuration}>{message.duration || 1}″</Text>
                  </View>
                )}
                <Text className={styles.timeText}>{formatTime(message.createdAt)}</Text>
              </View>
              {/* AI消息操作按钮 */}
              {message.role === 'assistant' && message.id !== 'welcome' && !isStreaming && (
                <View className={styles.messageActions}>
                  <View className={styles.actionBtn} onClick={() => handleCopyMessage(message.content)}>
                    <Text className={styles.actionBtnIcon}>📋</Text>
                    <Text className={styles.actionBtnText}>复制</Text>
                  </View>
                  <View
                    className={classnames(styles.actionBtn, messageFeedbacks[message.id] === 'like' && styles.actionBtnActive)}
                    onClick={() => handleFeedback(message.id, 'like')}
                  >
                    <Text className={styles.actionBtnIcon}>👍</Text>
                    <Text className={styles.actionBtnText}>有用</Text>
                  </View>
                  <View
                    className={classnames(styles.actionBtn, messageFeedbacks[message.id] === 'dislike' && styles.actionBtnActive)}
                    onClick={() => handleFeedback(message.id, 'dislike')}
                  >
                    <Text className={styles.actionBtnIcon}>👎</Text>
                    <Text className={styles.actionBtnText}>无用</Text>
                  </View>
                  <View className={styles.actionBtn} onClick={() => handleShare(message)}>
                    <Text className={styles.actionBtnIcon}>↗️</Text>
                    <Text className={styles.actionBtnText}>分享</Text>
                  </View>
                </View>
              )}
            </View>
          </View>
        ))}

        {conversationMeta.scenario === 'emotion' && supportFeedbackCheckInId && !isStreaming && (
          <View className={styles.supportFeedbackCard}>
            <Text className={styles.supportFeedbackTitle}>刚才有多大程度让你觉得“被理解”？</Text>
            <Text className={styles.supportFeedbackDesc}>只记录这次感受分级，用来调整陪伴方式，不保存新的倾诉正文。</Text>
            <View className={styles.supportFeedbackActions}>
              <View className={styles.supportFeedbackGhost} onClick={() => submitSupportFeedback(false, 1)}><Text>没被理解</Text></View>
              <View className={styles.supportFeedbackGhost} onClick={() => submitSupportFeedback(true, 3)}><Text>有一点</Text></View>
              <View className={styles.supportFeedbackPrimary} onClick={() => submitSupportFeedback(true, 5)}><Text>被理解了</Text></View>
            </View>
          </View>
        )}

        {interviewState?.active && interviewState.sessionId && !isStreaming && (
          <View className={styles.supportFeedbackCard}>
            <Text className={styles.supportFeedbackTitle}>这一题卡住了？</Text>
            <Text className={styles.supportFeedbackDesc}>只给三步思考骨架，不代答，也不会消耗或跳过当前题。</Text>
            <View className={styles.supportFeedbackActions}>
              <View className={styles.supportFeedbackGhost} onClick={requestInterviewRescue}><Text>给我一个救场框架</Text></View>
            </View>
          </View>
        )}

        {/* 识别到求职状态时只给轻量 inline 确认，不再悬浮挡住输入区 */}
        {pendingJobEvent && (
          <View className={styles.inlineConfirmCard}>
            <View className={styles.confirmMain}>
              <Text className={styles.confirmTitle}>顺手记到求职进度？</Text>
              <Text className={styles.confirmDesc}>{pendingJobEvent.company} · {pendingJobEvent.position} · {pendingJobEvent.statusLabel}</Text>
            </View>
            <View className={styles.confirmActions}>
              <View className={styles.confirmGhost} onClick={dismissPendingJobEvent}><Text>忽略</Text></View>
              <View className={styles.confirmPrimary} onClick={confirmPendingJobEvent}><Text>记录</Text></View>
            </View>
          </View>
        )}

        {/* 职位搜索结果 - 情绪场景下不显示 */}
        {conversationMeta.scenario !== 'emotion' && jobSearchResults.length > 0 && (
          <View className={styles.messageRow}>
            <View className={classnames(styles.avatar, styles.avatarAssistant)}>
              <Text>姐</Text>
            </View>
            <View className={styles.recCardWrap}>
              <Text className={styles.recLabel}>🔍 找到 {jobSearchResults.length} 个相关岗位</Text>
              {jobSearchResults.map((job, idx) => (
                <View key={idx} className={styles.jobCard}>
                  <View className={styles.jobCardHeader}>
                    <Text className={styles.jobTitle}>{job.title}</Text>
                    {job.salary && <Text className={styles.jobSalary}>{job.salary}</Text>}
                  </View>
                  <Text className={styles.jobCompany}>{job.company} · {job.location}</Text>
                  <Text className={styles.jobSummary}>{job.summary}</Text>
                  <View className={styles.jobCardFooter}>
                    <Text className={styles.jobSource}>来源: {job.source}</Text>
                    <View
                      className={styles.jobActionButton}
                      onClick={() => {
                        const jdContent = `${job.title} - ${job.company}\n地点: ${job.location}\n${job.summary}`
                        jdAnalyze(jdContent)
                      }}
                    >
                      <Text className={styles.jobActionText}>解读 JD</Text>
                    </View>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* 推荐卡片 — 只在前 3 轮对话展示，避免反复打扰 */}
        {!isStreaming && recommendations.length > 0 && messages.length <= 4 && (
          <View className={styles.messageRow}>
            <View className={classnames(styles.avatar, styles.avatarAssistant)}>
              <Text>姐</Text>
            </View>
            <View className={styles.recCardWrap}>
              <Text className={styles.recLabel}>相关推荐</Text>
              {recommendations.map((rec, idx) => (
                <View key={idx} className={styles.recCard} onClick={rec.action}>
                  <Text className={styles.recIcon}>{rec.icon}</Text>
                  <View className={styles.recBody}>
                    <Text className={styles.recTitle}>{rec.title}</Text>
                    <Text className={styles.recSubtitle}>{rec.subtitle}</Text>
                  </View>
                  <Text className={styles.recArrow}>›</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* 流式输出中 */}
        {isStreaming && streamingContent && (
          <View className={styles.messageRow}>
            <View className={classnames(styles.avatar, styles.avatarAssistant)}>
              <Text>姐</Text>
            </View>
            <View className={classnames(styles.messageBubble, styles.bubbleAssistant)}>
              <Text className={styles.messageContent}>{streamingContent}</Text>
              <View className={styles.typingIndicator}>
                <View className={styles.typingDot} />
                <View className={styles.typingDot} />
                <View className={styles.typingDot} />
              </View>
            </View>
          </View>
        )}

        {/* 底部留白 */}
        <View style={{ height: '20rpx' }} />
      </ScrollView>

      {isRecording && (
        <View className={styles.recordOverlay}>
          <Text className={styles.recordIcon}>🎙️</Text>
          <Text className={styles.recordHint}>{recordHint}</Text>
        </View>
      )}

      {showInterviewInput && (
        <ScrollView className={styles.interviewSetupBar} scrollY>
          <Text className={styles.interviewLabel}>目标岗位</Text>
          <Textarea
            className={styles.jdTextarea}
            value={interviewInput}
            onInput={(event) => setInterviewInput(event.detail.value)}
            placeholder="例如：AI 产品经理 / 大模型算法工程师"
            maxlength={80}
            autoHeight
            showConfirmBar={false}
          />
          <Text className={styles.interviewLabel}>面试任务信息（可选）</Text>
          <Textarea className={styles.interviewTextarea} value={interviewCompany} onInput={(e) => setInterviewCompany(e.detail.value)} placeholder="目标公司" maxlength={60} autoHeight showConfirmBar={false} />
          <Textarea className={styles.interviewTextarea} value={interviewRound} onInput={(e) => setInterviewRound(e.detail.value)} placeholder="轮次，例如业务一面 / HR 面" maxlength={40} autoHeight showConfirmBar={false} />
          <Textarea className={styles.interviewTextarea} value={interviewDate} onInput={(e) => setInterviewDate(e.detail.value)} placeholder="日期，例如 8月8日晚上" maxlength={40} autoHeight showConfirmBar={false} />
          <Textarea className={styles.interviewTextarea} value={interviewAnxiety} onInput={(e) => setInterviewAnxiety(e.detail.value)} placeholder="最焦虑或最想补的点" maxlength={100} autoHeight showConfirmBar={false} />
          <Text className={styles.interviewLabel}>今天想怎么练？</Text>
          <View className={styles.durationRow}>
            {([
              ['warmup', '陪我热身'],
              ['real', '真实强度'],
              ['pressure', '压力追问'],
            ] as const).map(([value, label]) => (
              <View
                key={value}
                className={classnames(styles.durationChip, interviewPracticeStyle === value && styles.durationChipActive)}
                onClick={() => setInterviewPracticeStyle(value)}
              >
                <Text>{label}</Text>
              </View>
            ))}
          </View>
          <Text className={styles.interviewLabel}>面试前还有多久？</Text>
          <View className={styles.durationRow}>
            {([5, 10, 20, 30] as const).map((duration) => (
              <View
                key={duration}
                className={classnames(styles.durationChip, interviewDuration === duration && styles.durationChipActive)}
                onClick={() => setInterviewDuration(duration)}
              >
                <Text>{duration} 分钟</Text>
              </View>
            ))}
          </View>
          <Text className={styles.durationHint}>5分钟快速诊断 / 10分钟弱项复练 / 20分钟项目深挖 / 30分钟全真模拟；最后生成六维报告。</Text>
          <View className={styles.interviewButtons}>
            <View className={styles.interviewCancel} onClick={() => setShowInterviewInput(false)}><Text>取消</Text></View>
            <View className={styles.interviewConfirm} onClick={handleStartInterview}><Text>开始练习</Text></View>
          </View>
        </ScrollView>
      )}

      {showJDInput && (
        <View className={styles.jdInputBar}>
          <Text className={styles.interviewLabel}>粘贴岗位描述：</Text>
          <Textarea
            className={styles.jdTextarea}
            value={jdInputText}
            onInput={(e) => setJdInputText(e.detail.value)}
            placeholder="把 JD 内容贴到这里..."
            maxlength={2000}
            autoHeight
            showConfirmBar={false}
          />
          <View className={styles.interviewButtons}>
            <View className={styles.interviewCancel} onClick={() => setShowJDInput(false)}>
              <Text>取消</Text>
            </View>
            <View className={styles.interviewConfirm} onClick={handleJDSubmit}>
              <Text>开始解读</Text>
            </View>
          </View>
        </View>
      )}

      {/* 历史对话弹层 */}
      {showHistory && (
        <View className={styles.historyOverlay} onClick={() => setShowHistory(false)}>
          <View className={styles.historyPanel} onClick={(e) => e.stopPropagation()}>
            <View className={styles.historyHeader}>
              <Text className={styles.historyTitle}>历史对话</Text>
              <View className={styles.historyClose} onClick={() => setShowHistory(false)}>
                <Text>✕</Text>
              </View>
            </View>
            {conversationHistory.length === 0 ? (
              <View className={styles.historyEmpty}>
                <Text>还没有历史对话</Text>
              </View>
            ) : (
              <View className={styles.historyList}>
                {conversationHistory.map((session) => (
                  <View key={session.id} className={styles.historyItem}>
                    <View
                      className={styles.historyItemMain}
                      onClick={() => {
                        switchToConversation(session.id)
                        setShowHistory(false)
                      }}
                    >
                      <Text className={styles.historyItemTitle}>{session.title}</Text>
                      <Text className={styles.historyItemMeta}>
                        {session.messages.length} 条消息 · {new Date(session.updatedAt).toLocaleDateString('zh-CN')}
                      </Text>
                    </View>
                    <View
                      className={styles.historyItemDelete}
                      onClick={() => deleteConversation(session.id)}
                    >
                      <Text>🗑</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>
      )}

      {showActionMenu && (
        <View className={styles.actionMenuOverlay} onClick={() => setShowActionMenu(false)}>
          <View className={styles.actionMenu}>
            <View className={styles.actionMenuItem} onClick={handleImageSend}>
              <Text className={styles.actionMenuIcon}>🖼</Text>
              <Text className={styles.actionMenuText}>发送图片</Text>
            </View>
            <View className={styles.actionMenuDivider} />
            <View className={styles.actionMenuItem} onClick={handleResumeUpload}>
              <Text className={styles.actionMenuIcon}>📄</Text>
              <Text className={styles.actionMenuText}>上传简历（PDF / DOCX）</Text>
            </View>
            <View className={styles.actionMenuDivider} />
            <View className={styles.actionMenuItem} onClick={() => { setShowActionMenu(false); setShowJDInput(true); }}>
              <Text className={styles.actionMenuIcon}>📝</Text>
              <Text className={styles.actionMenuText}>粘贴 JD</Text>
            </View>
          </View>
        </View>
      )}

      {/* 分享菜单 */}
      {showShareMenu && shareTargetMessage && (
        <View className={styles.actionMenuOverlay} onClick={() => setShowShareMenu(false)}>
          <View className={styles.actionMenu}>
            <View className={styles.actionMenuItem} onClick={() => handleShareOption('link')}>
              <Text className={styles.actionMenuIcon}>🔗</Text>
              <Text className={styles.actionMenuText}>复制内容</Text>
            </View>
            <View className={styles.actionMenuDivider} />
            <View className={styles.actionMenuItem} onClick={() => handleShareOption('wechat')}>
              <Text className={styles.actionMenuIcon}>💬</Text>
              <Text className={styles.actionMenuText}>转发给好友</Text>
            </View>
          </View>
        </View>
      )}

      {messageActionTarget && (
        <View className={styles.actionMenuOverlay} onClick={() => setMessageActionTarget(null)}>
          <View className={styles.messageActionSheet} onClick={(event) => event.stopPropagation()}>
            <Text className={styles.messageActionTitle}>回答操作</Text>
            <View className={styles.messageActionGrid}>
              <View className={styles.messageActionItem} onClick={() => { handleCopyMessage(messageActionTarget.content); setMessageActionTarget(null) }}>
                <Text className={styles.messageActionIcon}>⧉</Text><Text>复制</Text>
              </View>
              <View className={styles.messageActionItem} onClick={() => handleOpenTextSelection(messageActionTarget)}>
                <Text className={styles.messageActionIcon}>T</Text><Text>选择文本</Text>
              </View>
              <View className={styles.messageActionItem} onClick={() => handleRegenerate(messageActionTarget)}>
                <Text className={styles.messageActionIcon}>↻</Text><Text>重新生成</Text>
              </View>
              <View className={styles.messageActionItem} onClick={() => { handleFeedback(messageActionTarget.id, 'like'); setMessageActionTarget(null) }}>
                <Text className={styles.messageActionIcon}>♡</Text><Text>有用</Text>
              </View>
              <View className={styles.messageActionItem} onClick={() => { handleFeedback(messageActionTarget.id, 'dislike'); setMessageActionTarget(null) }}>
                <Text className={styles.messageActionIcon}>△</Text><Text>无用</Text>
              </View>
              <View className={styles.messageActionItem} onClick={() => { handleShare(messageActionTarget); setMessageActionTarget(null) }}>
                <Text className={styles.messageActionIcon}>↗</Text><Text>分享</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {selectionMessage && (
        <View className={styles.textSelectionOverlay} onClick={() => setSelectionMessage(null)}>
          <View className={styles.textSelectionPanel} onClick={(event) => event.stopPropagation()}>
            <Text className={styles.textSelectionTitle}>选择要复制的文字</Text>
            <Text className={styles.textSelectionHint}>已默认全选，也可以拖动系统选区手柄调整范围。</Text>
            <Textarea
              className={styles.textSelectionArea}
              value={selectionMessage.content}
              focus
              fixed
              maxlength={-1}
              selectionStart={selectionRange.start}
              selectionEnd={selectionRange.end}
              onSelectionChange={(event: any) => setSelectionRange({
                start: event.detail.selectionStart,
                end: event.detail.selectionEnd,
              })}
              showConfirmBar={false}
            />
            <View className={styles.textSelectionButtons}>
              <View className={styles.textSelectionCancel} onClick={() => setSelectionMessage(null)}><Text>取消</Text></View>
              <View className={styles.textSelectionCopy} onClick={handleCopySelection}><Text>复制所选</Text></View>
            </View>
          </View>
        </View>
      )}

      {privacyPromptVisible && (
        <View className={styles.privacyOverlay}>
          <View className={styles.privacyCard}>
            <Text className={styles.privacyTitle}>隐私提示</Text>
            <Text className={styles.privacyDescription}>
              {privacyDescription}
            </Text>
            <View className={styles.privacyActions}>
              <Button className={styles.privacyDecline} onClick={declinePrivacyAuthorization}>拒绝</Button>
              <Button
                id={PRIVACY_AGREE_BUTTON_ID}
                className={styles.privacyAgree}
                openType='agreePrivacyAuthorization'
                onAgreePrivacyAuthorization={agreePrivacyAuthorization}
              >
                同意继续
              </Button>
            </View>
          </View>
        </View>
      )}

      <View className={styles.footer}>
        {draft.length > 0 && (
          <View className={styles.draftTools}>
            <View className={styles.selectAllButton} onClick={handleSelectAllDraft}><Text>全选输入内容</Text></View>
            <Text className={styles.draftCount}>{draft.length}/500</Text>
          </View>
        )}
        <View className={styles.inputWrap}>
          <View className={styles.attachButton} onClick={() => setShowActionMenu(true)}>
            <Text>+</Text>
          </View>
          <Textarea
            className={styles.textarea}
            value={draft}
            focus={draftFocused}
            selectionStart={draftSelection.start}
            selectionEnd={draftSelection.end}
            onFocus={() => setDraftFocused(true)}
            onBlur={() => setDraftFocused(false)}
            onInput={(event) => {
              setDraft(event.detail.value)
              setDraftSelection({ start: -1, end: -1 })
            }}
            onConfirm={() => handleSend()}
            confirmType="send"
            maxlength={500}
            placeholder='把你现在最卡的一件事发给学姐'
            autoHeight
            showConfirmBar={false}
          />
          <Button
            className={classnames(styles.voiceButton, isRecording && styles.voiceButtonActive)}
            ariaRole='button'
            ariaLabel={isRecording ? '正在录音，再点一次发送' : '录音'}
            onClick={handleVoiceClick}
          >
            <Text className={styles.voiceAccessibleLabel}>
              {isRecording ? '正在录音，再点一次发送' : '录音'}
            </Text>
            {isRecording ? (
              <View className={styles.recordingIndicator}>
                <View className={styles.recordingWave} />
                <View className={styles.recordingWave} style={{ animationDelay: '0.1s' }} />
                <View className={styles.recordingWave} style={{ animationDelay: '0.2s' }} />
              </View>
            ) : (
              <View className={styles.micIcon}>
                <View className={styles.micBody} />
                <View className={styles.micStem} />
                <View className={styles.micBase} />
              </View>
            )}
          </Button>
        </View>
      </View>
    </View>
  )
}

export default ConversationPage
