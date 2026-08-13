import { create } from 'zustand'
import Taro from '@tarojs/taro'
import {
  BookingItem,
  ConversationScenario,
  ConversationSession,
  InterviewState,
  JobProgressItem,
  JobStatus,
  JobSearchResult,
  PendingJobEvent,
  MessageItem,
  MiniappReadiness,
  MiniappRuntimeInfo,
  ServiceHealth,
  ServiceTimelineItem,
  SupportFollowUp,
  TodayTask,
  TriageStage,
  UserMembership,
  UserProfile,
  WorkspaceJob,
} from '@/types/pinco'
import { bootstrapMiniapp, createBooking, searchJobsByPlatform as apiSearchJobs, fetchMembershipStatus as apiFetchMembershipStatus } from '@/services/pinco'
import { buildConversationTitle } from '@/utils/format'
import { getBootstrapPayload } from '@/utils/session'
import { getMiniappRuntimeInfo } from '@/utils/wechat'
import {
  getApiBaseUrl,
  apiRequest,
  apiUploadFile,
  setApiSessionRecoveryHandler,
  setApiSessionToken,
} from '@/services/api'
import { trackProductEvent } from '@/services/analytics'

interface ConversationMeta {
  title: string
  subtitle: string
  scenario: ConversationScenario
}

interface PincoState {
  userProfile: UserProfile | null
  wechatReady: boolean
  launchScene: string
  miniappReadiness: MiniappReadiness | null
  runtimeInfo: MiniappRuntimeInfo
  messages: MessageItem[]
  bookings: BookingItem[]
  serviceTimeline: ServiceTimelineItem[]
  conversationMeta: ConversationMeta
  serviceHealth: ServiceHealth
  isSending: boolean
  isStreaming: boolean
  streamingContent: string
  interviewState: InterviewState | null
  jobProgress: JobProgressItem[]
  pendingJobEvent: PendingJobEvent | null
  todayTasks: TodayTask[]
  jobSearchResults: JobSearchResult[]
  membership: UserMembership | null
  supportDueFollowUps: SupportFollowUp[]
  supportFeedbackCheckInId: string | null
  searchJobs: (query: string, city?: string) => Promise<void>
  checkInEmotion: (intensity: 1 | 2 | 3 | 4 | 5, eventType?: string, note?: string) => Promise<any>
  submitSupportFeedback: (helpful: boolean, understoodScore: 1 | 2 | 3 | 4 | 5) => Promise<void>
  respondSupportFollowUp: (checkInId: string, intensity: 1 | 2 | 3 | 4 | 5, microActionCompleted: boolean) => Promise<void>
  loadMembership: () => Promise<void>
  bootstrap: () => Promise<void>
  refreshServiceHealth: () => Promise<void>
  setLaunchScene: (scene: string) => void
  openConversation: (scenario?: ConversationScenario, subtitle?: string) => void
  sendMessage: (content: string, type?: MessageItem['type'], media?: Pick<MessageItem, 'mediaUrl' | 'fileName' | 'duration'>) => Promise<void>
  regenerateMessage: (messageId: string) => Promise<void>
  seedConversation: (scenario: ConversationScenario, prompt: string, subtitle?: string) => Promise<void>
  startInterview: (
    position: string,
    durationMinutes?: 5 | 10 | 20 | 30,
    setup?: { company?: string; interviewRound?: string; interviewDate?: string; anxietyFocus?: string; practiceStyle?: 'warmup' | 'real' | 'pressure'; jobId?: string; sourcePostId?: string; jdText?: string }
  ) => Promise<void>
  requestInterviewRescue: () => Promise<void>
  endInterview: () => void
  resumeUpload: (filePath: string, fileName: string) => Promise<void>
  jdAnalyze: (jdText: string) => Promise<void>
  confirmPendingJobEvent: () => Promise<void>
  dismissPendingJobEvent: () => void
  bindLatestMaterialToJob: (jobId: string, material: keyof JobProgressItem['materials']) => void
  updateJobStatus: (jobId: string, status: JobStatus) => Promise<void>
  createBookingOrder: (payload: { expert_id: string; expert_name: string; topic: string; slot: string; desc: string; job_id?: string; share_context_with_expert?: boolean }) => Promise<void>
  cancelBookingOrder: (bookingId: string) => Promise<void>
  refreshBookings: () => Promise<void>
  loadMessages: () => void
  saveMessages: () => void
  clearMessages: () => Promise<void>
  loadTodayTasks: () => void
  saveTodayTasks: () => void
  toggleTodayTask: (id: string) => void
  clearDoneTasks: () => void
  generateTasksFromTriage: (stage: TriageStage, role: string, time: string, materials: string[], anxiety: string) => TodayTask[]
  addTodayTasks: (tasks: TodayTask[]) => void
  conversationHistory: ConversationSession[]
  createNewConversation: () => void
  switchToConversation: (sessionId: string) => void
  deleteConversation: (sessionId: string) => void
  loadConversationHistory: () => void
}

const STORAGE_KEY = 'pinco_messages_v2'
const JOB_STORAGE_KEY = 'pinco_job_progress_v1'
const TASKS_STORAGE_KEY = 'pinco_today_tasks_v1'
const HISTORY_STORAGE_KEY = 'pinco_conversation_history_v1'

const mergeMessages = (local: MessageItem[], remote: MessageItem[]): MessageItem[] => {
  const merged = new Map<string, MessageItem>()
  for (const message of [...remote, ...local]) {
    const fallbackKey = `${message.role}:${message.createdAt}:${message.content}`
    merged.set(message.id || fallbackKey, message)
  }
  return [...merged.values()]
    .sort((a, b) => a.createdAt - b.createdAt)
    .slice(-200)
}

const extractApiErrorMessage = (data: any): string => {
  const detail = data?.detail
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  return detail.message || detail.code || JSON.stringify(detail)
}

const statusLabels: Record<JobStatus, string> = {
  saved: '已收藏',
  applied: '已投递',
  written: '笔试中',
  interview1: '一面',
  interview2: '二面',
  hr: 'HR 面',
  offer: 'Offer',
  rejected: '已挂'
}

const statusNextActions: Record<JobStatus, string> = {
  saved: '补全 JD 和真实证据，再决定是否投递',
  applied: '3-5 天未回复可准备跟进话术',
  written: '先整理题型和截止时间',
  interview1: '建议做一轮岗位模拟面试',
  interview2: '复盘一面问题，补齐岗位案例',
  hr: '准备薪资锚点和到岗时间',
  offer: '对比薪资、成长和团队风险',
  rejected: '沉淀复盘，提炼下一轮改法'
}

const saveJobProgress = (items: JobProgressItem[]) => {
  try {
    Taro.setStorageSync(JOB_STORAGE_KEY, JSON.stringify(items))
  } catch (e) {
    console.error('[Store] save job progress failed', e)
  }
}

const loadJobProgressFromStorage = (): JobProgressItem[] => {
  try {
    const raw = Taro.getStorageSync(JOB_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as JobProgressItem[]
  } catch (e) {
    console.error('[Store] load job progress failed', e)
  }
  return []
}

const workspaceJobsToProgress = (jobs: WorkspaceJob[] = []): JobProgressItem[] => jobs.map((job) => {
  const status = (job.status in statusLabels ? job.status : 'saved') as JobStatus
  return {
    id: job.id,
    company: job.company,
    position: job.title,
    status,
    statusLabel: statusLabels[status],
    date: (job.updated_at || job.created_at || '').slice(5, 10) || '云端',
    nextAction: statusNextActions[status],
    source: job.source === 'manual' ? 'manual' : 'ai',
    materials: {
      resumeBound: Boolean(job.materials?.resume_bullets?.length),
      jdBound: Boolean(job.jd_text),
      reviewBound: Boolean(job.materials?.interview_stories?.length),
    },
    updatedAt: Date.parse(job.updated_at || job.created_at) || Date.now(),
  }
})

const defaultRuntimeInfo: MiniappRuntimeInfo = getMiniappRuntimeInfo(false)

const defaultHealth: ServiceHealth = {
  online: false,
  model: 'claude-sonnet-4-20250514',
  provider: 'backend',
  mockMode: false,
  summary: '正在检查服务状态...'
}

const welcomeMessage: MessageItem = {
  id: 'welcome',
  role: 'assistant',
  content: '嗨！我是 Pinco，你的温柔学姐。👋\n\n职场前五年是生存到突破的关键期。今天遇到了什么难题？\n\n你可以直接打字问我，或者点击下方卡片快速开始 👇',
  type: 'text',
  createdAt: Date.now(),
}

export const usePincoStore = create<PincoState>((set, get) => ({
  userProfile: null,
  wechatReady: false,
  launchScene: '',
  miniappReadiness: null,
  runtimeInfo: defaultRuntimeInfo,
  messages: [welcomeMessage],
  bookings: [],
  serviceTimeline: [],
  conversationMeta: {
    title: '专属会话',
    subtitle: '把问题交给学姐一起拆',
    scenario: 'general'
  },
  serviceHealth: defaultHealth,
  isSending: false,
  isStreaming: false,
  streamingContent: '',
  interviewState: null,
  jobProgress: [],
  pendingJobEvent: null,
  todayTasks: [],
  jobSearchResults: [],
  membership: null,
  supportDueFollowUps: [],
  supportFeedbackCheckInId: null,
  conversationHistory: [],

  loadMessages: () => {
    try {
      const raw = Taro.getStorageSync(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as MessageItem[]
        if (parsed.length > 0) {
          set({ messages: parsed })
          return
        }
      }
    } catch (e) {
      console.error('[Store] load messages failed', e)
    }
    set({ messages: [welcomeMessage] })
  },

  saveMessages: () => {
    try {
      Taro.setStorageSync(STORAGE_KEY, JSON.stringify(get().messages))
    } catch (e) {
      console.error('[Store] save messages failed', e)
    }
  },

  clearMessages: async () => {
    const userId = get().userProfile?.user_id
    if (!userId) throw new Error('用户身份尚未准备好')
    const result = await apiRequest<{ messages: MessageItem[] }>('/api/v1/account/messages/clear', 'POST', { user_id: userId })
    set({ messages: result.messages, interviewState: null, pendingJobEvent: null })
    try {
      Taro.removeStorageSync(STORAGE_KEY)
    } catch (e) {
      console.error('[Store] clear messages failed', e)
    }
  },

  loadTodayTasks: () => {
    try {
      const raw = Taro.getStorageSync(TASKS_STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as TodayTask[]
        if (parsed.length > 0) {
          set({ todayTasks: parsed.filter((t) => t.title && t.desc && !['seed-1', 'seed-2', 'seed-3'].includes(t.id)) })
          return
        }
      }
    } catch (e) {
      console.error('[Store] load today tasks failed', e)
    }
    set({ todayTasks: [] })
  },

  saveTodayTasks: () => {
    try {
      Taro.setStorageSync(TASKS_STORAGE_KEY, JSON.stringify(get().todayTasks))
    } catch (e) {
      console.error('[Store] save today tasks failed', e)
    }
  },

  toggleTodayTask: (id) => {
    const next = get().todayTasks.map((item) => item.id === id ? { ...item, done: !item.done } : item)
    set({ todayTasks: next })
    try {
      Taro.setStorageSync(TASKS_STORAGE_KEY, JSON.stringify(next))
    } catch (e) {
      console.error('[Store] save today tasks failed', e)
    }
  },

  clearDoneTasks: () => {
    const next = get().todayTasks.filter((item) => !item.done)
    set({ todayTasks: next })
    try {
      Taro.setStorageSync(TASKS_STORAGE_KEY, JSON.stringify(next))
    } catch (e) {
      console.error('[Store] save today tasks failed', e)
    }
  },

  addTodayTasks: (tasks) => {
    const next = [...tasks, ...get().todayTasks].slice(0, 12)
    set({ todayTasks: next })
    try {
      Taro.setStorageSync(TASKS_STORAGE_KEY, JSON.stringify(next))
    } catch (e) {
      console.error('[Store] save today tasks failed', e)
    }
  },

  generateTasksFromTriage: (stage, role, time, materials, anxiety) => {
    const target = role.trim() || '目标岗位'
    const hasJD = materials.includes('JD')
    const hasResume = materials.includes('简历')
    const now = Date.now()
    const createTask = (
      title: string,
      desc: string,
      source: TodayTask['source'],
      action?: TodayTask['action'],
      prompt?: string
    ): TodayTask => ({
      id: `task-${now}-${Math.random().toString(36).slice(2, 8)}`,
      title,
      desc,
      done: false,
      source,
      action,
      prompt,
      createdAt: now,
    })

    if (stage === 'interview') {
      return [
        createTask('复盘最近一次被追问的问题', `用5句话写下问题、你的回答、卡住点。可用时间：${time}`, 'interview', 'send_chat', '我刚面完/最近一次面试被追问了几个问题，帮我做一次结构化复盘。'),
        createTask(`准备1个${target}项目深挖故事`, '按STAR写出背景、目标、动作、结果，各不超过2行。', 'interview', 'send_chat', `帮我为${target}准备一个可被深挖15分钟的STAR项目故事。`),
        createTask('做10分钟模拟面试', '让Pinco只追问一个项目，结束后把复盘归档。', 'interview', 'open_interview'),
      ]
    }
    if (stage === 'offer') {
      return [
        createTask('列Offer决策三栏', '薪资福利/成长空间/风险红线，每栏至少3条。', 'job_progress', 'send_chat', '帮我做一个Offer决策三栏表：薪资福利、成长空间、风险红线。'),
        createTask('生成谈薪话术', `围绕${target}的市场价和个人筹码，准备2套说法。`, 'job_progress', 'send_chat', `帮我围绕${target}准备2套谈薪话术。`),
        createTask('确认最晚回复时间', '把HR截止日期记到进度里，避免被动。', 'job_progress', 'view_progress'),
      ]
    }
    if (stage === 'starting') {
      return [
        createTask(`确定${target}的10个目标公司`, '先按行业/城市/岗位匹配度筛，不要一上来海投。', 'triage', 'send_chat', `帮我按行业、城市、岗位匹配度筛出${target}的10个目标公司。`),
        createTask(hasResume ? '把简历改成目标岗位版本' : '先补一版基础简历', '只改标题、项目亮点和关键词三处，今天先能投出去。', 'resume', 'open_resume'),
        createTask(hasJD ? '从JD提取8个关键词' : '找3条真实JD粘给Pinco', `焦虑点：${anxiety}。先用证据决定投什么。`, 'jd', 'open_jd'),
      ]
    }
    return [
      createTask(hasJD ? '拆1份最高匹配JD' : '粘贴1份最想投的JD', `目标是找出${target}的5个高频关键词。`, 'jd', 'open_jd'),
      createTask(hasResume ? '用JD对齐简历首屏' : '上传简历做一次诊断', '只优化最影响回复率的摘要、项目标题、成果数字。', 'resume', 'open_resume'),
      createTask('精准补投5个岗位', `不要补投50个。今天${time}只追求5个高匹配。`, 'triage', 'send_chat', `基于我的目标岗位${target}，帮我制定今天精准补投5个岗位的筛选标准。`),
    ]
  },

  bootstrap: async () => {
    let runtimeInfo = defaultRuntimeInfo
    try {
      const payload = await getBootstrapPayload()
      runtimeInfo = getMiniappRuntimeInfo(Boolean(payload.code))
      const data = await bootstrapMiniapp(payload)
      setApiSessionToken(data.session_token)

      // Load local messages first; only use server messages if local is empty
      let localMessages: MessageItem[] = []
      try {
        const raw = Taro.getStorageSync(STORAGE_KEY)
        if (raw) {
          const parsed = JSON.parse(raw) as MessageItem[]
          if (parsed.length > 0) localMessages = parsed
        }
      } catch {}

      set({
        userProfile: data.user,
        wechatReady: data.wechat_ready,
        miniappReadiness: data.miniapp_readiness,
        runtimeInfo,
        messages: mergeMessages(localMessages, data.messages?.length > 0 ? data.messages : [welcomeMessage]),
        bookings: data.bookings,
        serviceTimeline: data.service_timeline,
        serviceHealth: data.service_health,
        membership: data.membership || null,
        supportDueFollowUps: data.support_due || [],
        jobProgress: data.workspace?.jobs?.length ? workspaceJobsToProgress(data.workspace.jobs) : loadJobProgressFromStorage(),
        todayTasks: (() => {
          try {
            const raw = Taro.getStorageSync(TASKS_STORAGE_KEY)
            if (raw) {
              const parsed = JSON.parse(raw) as TodayTask[]
              return parsed.filter((t) => t.title && t.desc)
            }
          } catch {}
          return []
        })()
      })
      trackProductEvent('app.bootstrap.succeeded', data.user.user_id, {
        wechat_bound: data.user.wechat_bound,
        durable_ready: data.miniapp_readiness?.items?.find((item) => item.key === 'durable_state')?.ready || false,
      })
    } catch (error) {
      console.error('[Store] bootstrap failed', error)
      set({
        serviceHealth: {
          online: false,
          model: '未知',
          provider: 'backend',
          mockMode: false,
          summary: '模型服务未连接：本地记录可用，但不会用固定模板冒充 AI'
        },
        runtimeInfo,
        messages: (() => {
          try {
            const raw = Taro.getStorageSync(STORAGE_KEY)
            if (raw) {
              const parsed = JSON.parse(raw) as MessageItem[]
              if (parsed.length > 0) return parsed
            }
          } catch {}
          return get().messages.length > 0 ? get().messages : [welcomeMessage]
        })(),
        jobProgress: loadJobProgressFromStorage(),
        todayTasks: (() => {
          try {
            const raw = Taro.getStorageSync(TASKS_STORAGE_KEY)
            if (raw) {
              const parsed = JSON.parse(raw) as TodayTask[]
              return parsed.filter((t) => t.title && t.desc)
            }
          } catch {}
          return []
        })()
      })
      trackProductEvent('app.bootstrap.failed', undefined, { stage: 'bootstrap' })
    }
  },

  refreshServiceHealth: async () => {
    await get().bootstrap()
  },

  setLaunchScene: (scene) => set({ launchScene: scene }),

  openConversation: (scenario = 'general', subtitle) => {
    set({
      conversationMeta: {
        title: buildConversationTitle(scenario),
        subtitle: subtitle || '把问题交给学姐一起拆',
        scenario
      }
    })
  },

  sendMessage: async (content, type = 'text', media) => {
    const trimmed = content.trim()
    if (!trimmed || get().isSending) return

    const now = Date.now()
    const userMessage: MessageItem = {
      id: `user-${now}`,
      role: 'user',
      content: trimmed,
      type,
      ...media,
      createdAt: now,
    }

    set({
      messages: [...get().messages, userMessage],
      isSending: true,
      isStreaming: true,
      streamingContent: '',
      jobSearchResults: [],
    })
    trackProductEvent('chat.send.started', get().userProfile?.user_id, {
      scenario: get().conversationMeta.scenario,
      input_type: type,
    })

    const interview = get().interviewState
    if (interview?.active && interview.sessionId) {
      try {
        const result = await apiRequest<any>(`/api/v1/interview/practice/${interview.sessionId}/answer`, 'POST', {
          user_id: get().userProfile?.user_id,
          answer: trimmed,
        })
        const scores = result.scores || {}
        const scoreLine = `内容 ${scores.content ?? '-'} · 结构 ${scores.structure ?? '-'} · 证据 ${scores.evidence ?? '-'} · 匹配 ${scores.role_fit ?? '-'} · 清晰 ${scores.clarity ?? '-'} · 应变 ${scores.adaptability ?? '-'}`
        const report = result.report
        const comparison = result.comparison
        const comparisonLine = comparison
          ? `\n\n**和上一次回答相比**：平均分 ${comparison.average_delta >= 0 ? '+' : ''}${comparison.average_delta}（${comparison.previous_average} → ${comparison.current_average}）\n评分只用于本轮纵向比较。`
          : ''
        const dimensions = report?.dimension_scores || {}
        const dimensionLine = `内容 ${dimensions.content ?? '-'} · 结构 ${dimensions.structure ?? '-'} · 证据 ${dimensions.evidence ?? '-'} · 匹配 ${dimensions.role_fit ?? '-'} · 清晰 ${dimensions.clarity ?? '-'} · 应变 ${dimensions.adaptability ?? '-'}`
        const content = result.completed
          ? `✅ **本轮练习完成**\n\n**本题反馈**：${result.feedback}\n\n**回答改进框架**：${result.better_answer}\n\n**本题评分**：${scoreLine}${comparisonLine}\n\n**整轮得分**：${report?.overall_score ?? '-'}\n\n**六维汇总**：${dimensionLine}\n\n**做得好的**\n${(report?.strengths || []).map((item: string) => `- ${item}`).join('\n')}\n\n**优先改进**\n${(report?.improvements || []).map((item: string) => `- ${item}`).join('\n')}\n\n**下一次练习**：${report?.next_drill || '从本轮最低分维度开始'} `
          : `**即时反馈**：${result.feedback}\n\n**回答改进框架**：${result.better_answer}\n\n**本题评分**：${scoreLine}${comparisonLine}\n\n---\n**第 ${interview.round + 1}/${interview.totalQuestions} 题**\n${result.next_question}`
        set({
          messages: [...get().messages, {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content,
            type: 'interview',
            createdAt: Date.now(),
          }],
          interviewState: result.completed ? null : { ...interview, round: interview.round + 1 },
          isStreaming: false,
          streamingContent: '',
        })
        get().saveMessages()
        trackProductEvent(result.completed ? 'interview.practice.completed' : 'interview.practice.answer_succeeded', get().userProfile?.user_id, {
          duration_minutes: interview.durationMinutes || 10,
          question_index: interview.round,
        })
      } catch (error) {
        console.error('[Store] interview practice answer failed', error)
        set({
          messages: [...get().messages, {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: '这次回答没有完成评分，我已经保留你的原回答，也没有生成固定点评。请稍后点“重试本题”。',
            type: 'interview',
            createdAt: Date.now(),
          }],
          isStreaming: false,
          streamingContent: '',
        })
        get().saveMessages()
        trackProductEvent('interview.practice.answer_failed', get().userProfile?.user_id, {
          duration_minutes: interview.durationMinutes || 10,
          question_index: interview.round,
        })
      } finally {
        set({ isSending: false, isStreaming: false })
      }
      return
    }
    if (interview?.active && interview.round < 5) {
      set({ interviewState: { ...interview, round: interview.round + 1 } })
    }

    const payload: any = {
      user_id: get().userProfile?.user_id,
      scenario: get().conversationMeta.scenario,
      messages: get().messages.filter((m) => m.role === 'user' || m.role === 'assistant').map((m) => ({
        role: m.role,
        content: m.content,
      })),
    }
    if (interview?.active) {
      payload.interview_mode = true
      payload.interview_round = interview.round
      payload.interview_position = interview.position
    }

    let fullContent = ''
    let useFallback = false
    let requestErrorText = ''
    let progressSuggestion: any = null

    try {
      const baseUrl = getApiBaseUrl()
      console.info('[Chat] baseUrl=', baseUrl, 'env=', process.env.TARO_ENV)

      // callContainer 不支持 SSE 流式响应，小程序环境直接走非流式
      const isWeapp = process.env.TARO_ENV === 'weapp'
      const isTunnelUrl = baseUrl.includes('trycloudflare.com')
      if (isWeapp || isTunnelUrl) {
        console.info('[Chat] weapp or tunnel detected, skip streaming')
        useFallback = true
      }

      if (!useFallback) {
      const task = Taro.request({
        url: `${baseUrl}/api/v1/chat/stream`,
        method: 'POST',
        data: payload,
        header: { 'Content-Type': 'application/json' },
        timeout: 60000,
        enableChunked: true,
      })

      const hasChunkHandler = typeof (task as any).onChunkReceived === 'function'
      console.info('[Chat] has onChunkReceived=', hasChunkHandler)

      if (hasChunkHandler) {
        (task as any).onChunkReceived((res: any) => {
          try {
            const chunk = new Uint8Array(res.data)
            const text = new TextDecoder('utf-8').decode(chunk)
            const lines = text.split('\n')
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6))
                  if (data.error) {
                    requestErrorText = data.error.message || data.error.code || JSON.stringify(data.error)
                  }
                  if (data.chunk) {
                    fullContent += data.chunk
                    set({ streamingContent: fullContent })
                  }
                  if (data.search_results && Array.isArray(data.search_results) && data.search_results.length > 0) {
                    set({ jobSearchResults: data.search_results })
                    console.info('[Chat] stream search results received:', data.search_results.length)
                  }
                } catch {}
              }
            }
          } catch (e) {
            console.warn('[Chat] chunk decode failed', e)
          }
        })
      } else {
        useFallback = true
        console.warn('[Chat] onChunkReceived not available, will fallback')
      }

      const response = await task
      console.info('[Chat] stream request done, status=', response.statusCode, 'contentLen=', fullContent.length)

      if (response.statusCode >= 400) {
        requestErrorText = extractApiErrorMessage(response.data) || `HTTP ${response.statusCode}`
        throw new Error(requestErrorText)
      }

      if (requestErrorText) {
        throw new Error(requestErrorText)
      }

      if (!fullContent || useFallback) {
        throw new Error('EMPTY_LLM_RESPONSE')
      }

      const assistantMessage: MessageItem = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: fullContent,
        type: type === 'interview' ? 'interview' : 'text',
        createdAt: Date.now(),
      }

      set({
        messages: [...get().messages, assistantMessage],
        serviceHealth: {
          ...get().serviceHealth,
          online: true,
          mockMode: false,
          summary: get().serviceHealth.summary.includes('模型服务未连接') ? '模型服务已恢复' : get().serviceHealth.summary
        },
        isStreaming: false,
        streamingContent: '',
      })

      if (interview?.active && interview.round >= 5) {
        set({ interviewState: null })
      }

      get().saveMessages()
      trackProductEvent('chat.send.succeeded', get().userProfile?.user_id, {
        scenario: get().conversationMeta.scenario,
        mode: 'stream',
      })
      }

      if (useFallback) {
        throw new Error('TUNNEL_SKIP_STREAMING')
      }
    } catch (error: any) {
      const streamErrorText = String(error?.message || error?.errMsg || error || '')
      if (streamErrorText.includes('TUNNEL_SKIP_STREAMING')) {
        console.info('[Chat] streaming intentionally skipped; using non-streaming request')
      } else {
        console.warn('[Store] stream failed, trying fallback', error)
        requestErrorText = [requestErrorText, streamErrorText].filter(Boolean).join(' ')
      }

      // Try non-streaming fallback
      if (!fullContent && !/429|rate limit|usage limit|quota/i.test(requestErrorText)) {
        try {
          // 小程序环境通过 apiRequest 走 callContainer，H5 走普通 HTTP
          const fallbackRes = await apiRequest<any>('/api/v1/chat', 'POST', payload)
          if (fallbackRes?.response) {
            fullContent = fallbackRes.response
            progressSuggestion = fallbackRes.progress_suggestion || null
            console.info('[Chat] fallback success, content length=', fullContent.length)
            const searchResults = fallbackRes?.search_results
            if (searchResults && Array.isArray(searchResults) && searchResults.length > 0) {
              set({ jobSearchResults: searchResults })
              console.info('[Chat] search results received:', searchResults.length)
            }
          }
        } catch (fallbackErr: any) {
          console.error('[Store] fallback also failed', fallbackErr)
          requestErrorText = [
            requestErrorText,
            String(fallbackErr?.message || fallbackErr?.errMsg || fallbackErr || ''),
          ].filter(Boolean).join(' ')
        }
      }

      if (fullContent) {
        // Fallback succeeded
        const assistantMessage: MessageItem = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: fullContent,
          type: type === 'interview' ? 'interview' : 'text',
          createdAt: Date.now(),
        }
        set({
          messages: [...get().messages, assistantMessage],
          serviceHealth: {
            ...get().serviceHealth,
            online: true,
            mockMode: false,
            summary: '模型服务正常（非流式模式）'
          },
          isStreaming: false,
          streamingContent: '',
        })
        if (
          progressSuggestion?.company
          && progressSuggestion?.position
          && progressSuggestion?.status in statusLabels
        ) {
          const status = progressSuggestion.status as JobStatus
          set({
            pendingJobEvent: {
              id: `agent-progress-${Date.now()}`,
              company: progressSuggestion.company,
              position: progressSuggestion.position,
              status,
              statusLabel: statusLabels[status],
              date: new Date().toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }),
              confidence: 1,
              rawText: progressSuggestion.prompt || trimmed,
            },
          })
        }
        if (interview?.active && interview.round >= 5) {
          set({ interviewState: null })
        }
        get().saveMessages()
        trackProductEvent('chat.send.succeeded', get().userProfile?.user_id, {
          scenario: get().conversationMeta.scenario,
          mode: 'non_stream',
        })
      } else {
        // Both failed
        const isRateLimited = /429|Too Many Requests|rate limit|usage limit|quota|额度|限流|exceeded retry/i.test(requestErrorText)
        const assistantContent = isRateLimited
          ? `模型服务额度已用完或被限流了，这不是你的输入问题，也不是 WebSocket 问题。\n\n我已经把你刚才的问题保留下来了。等额度恢复或更换可用 API Key 后，直接发「继续回答刚才的问题」，Pinco 会重新用真实模型回答。`
          : `我现在没有连上真实模型服务，所以不会再用固定模板假装回答你。\n\n请先检查：\n1. 后端是否已启动：${getApiBaseUrl()}/health\n2. 小程序开发工具是否开启「不校验合法域名」或已配置合法 request 域名\n3. 后端 .env 里的 LLM_PROVIDER / API Key / DEFAULT_MODEL 是否可用\n\n你刚才的问题已经保留在会话里。服务恢复后，直接再发一句「继续回答刚才的问题」就能接着聊。`

        set({
          messages: [
            ...get().messages,
            {
              id: `assistant-${Date.now()}`,
              role: 'assistant',
              content: assistantContent,
              type: type === 'interview' ? 'interview' : 'text',
              createdAt: Date.now(),
            }
          ],
          serviceHealth: {
            online: false,
            model: get().serviceHealth.model,
            provider: get().serviceHealth.provider,
            mockMode: false,
            summary: isRateLimited ? '模型服务限流：请稍后重试' : '模型服务未连接：已停止本地模板兜底'
          },
          isStreaming: false,
          streamingContent: '',
        })
        get().saveMessages()
        trackProductEvent('chat.send.failed', get().userProfile?.user_id, {
          scenario: get().conversationMeta.scenario,
          rate_limited: isRateLimited,
        })
      }
    } finally {
      set({ isSending: false, isStreaming: false })
    }
  },

  regenerateMessage: async (messageId) => {
    if (get().isSending) throw new Error('正在生成上一条回答，请稍候')
    const currentMessages = get().messages
    const targetIndex = currentMessages.findIndex((message) => message.id === messageId && message.role === 'assistant')
    if (targetIndex < 0) throw new Error('没有找到这条回答')
    const target = currentMessages[targetIndex]
    if (target.type === 'interview') {
      throw new Error('模拟面试反馈会影响练习进度，暂不支持重新生成')
    }
    const previousUserIndex = currentMessages
      .slice(0, targetIndex)
      .map((message, index) => ({ message, index }))
      .reverse()
      .find((item) => item.message.role === 'user')?.index
    if (previousUserIndex === undefined) throw new Error('没有找到对应的问题')

    const contextMessages = currentMessages
      .slice(0, targetIndex)
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => ({ role: message.role, content: message.content }))

    set({ isSending: true, isStreaming: true, streamingContent: '' })
    trackProductEvent('chat.regenerate.started', get().userProfile?.user_id, {
      scenario: get().conversationMeta.scenario,
      message_id: messageId,
    })
    try {
      const result = await apiRequest<any>('/api/v1/chat', 'POST', {
        user_id: get().userProfile?.user_id,
        scenario: get().conversationMeta.scenario,
        messages: contextMessages,
      })
      const content = String(result?.response || '').trim()
      if (!content) throw new Error('模型没有返回有效内容')
      const nextMessages = currentMessages.map((message) => message.id === messageId
        ? { ...message, content, createdAt: Date.now() }
        : message)
      set({
        messages: nextMessages,
        serviceHealth: {
          ...get().serviceHealth,
          online: true,
          mockMode: false,
          summary: '模型服务正常（重新生成）',
        },
      })
      get().saveMessages()
      trackProductEvent('chat.regenerate.succeeded', get().userProfile?.user_id, {
        scenario: get().conversationMeta.scenario,
        message_id: messageId,
      })
    } catch (error) {
      console.error('[Store] regenerate failed', error)
      trackProductEvent('chat.regenerate.failed', get().userProfile?.user_id, {
        scenario: get().conversationMeta.scenario,
        message_id: messageId,
      })
      throw error
    } finally {
      set({ isSending: false, isStreaming: false, streamingContent: '' })
    }
  },

  seedConversation: async (scenario, prompt, subtitle) => {
    get().openConversation(scenario, subtitle)
    await get().sendMessage(prompt, scenario === 'interview' ? 'interview' : 'text')
  },

  startInterview: async (position, durationMinutes = 10, setup = {}) => {
    if (!position.trim()) return
    set({
      interviewState: { active: true, round: 0, position },
      isSending: true,
    })
    const now = Date.now()
    const userMessage: MessageItem = {
      id: `user-${now}`,
      role: 'user',
      content: `🎤 我想模拟面试：${position}`,
      type: 'interview',
      createdAt: now,
    }
    set({ messages: [...get().messages, userMessage] })
    trackProductEvent('interview.start.started', get().userProfile?.user_id, { position })

    try {
      const data = await apiRequest<any>('/api/v1/interview/practice/start', 'POST', {
        user_id: get().userProfile?.user_id,
        position,
        duration_minutes: durationMinutes,
        company: setup.company || '',
        interview_round: setup.interviewRound || '',
        interview_date: setup.interviewDate || '',
        anxiety_focus: setup.anxietyFocus || '',
        practice_style: setup.practiceStyle || 'real',
        job_id: setup.jobId || undefined,
        source_post_id: setup.sourcePostId || undefined,
        jd_text: setup.jdText || undefined,
        focus_areas: setup.anxietyFocus ? [setup.anxietyFocus] : [],
      })

      const content = `🎤 **${durationMinutes} 分钟${data.mode || '面试前练习'}开始**\n\n**本轮重点**：${data.plan_summary}\n\n**第 1/${data.total_questions} 题**\n${data.question}\n\n**评分维度**\n${(data.focus || []).map((f: string) => `- ${f}`).join('\n')}\n\n---\n请直接打字或按住麦克风回答；每题都会给即时反馈，最后生成六维报告。`

      set({
        messages: [
          ...get().messages,
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content,
            type: 'interview',
            createdAt: Date.now(),
          }
        ],
        interviewState: {
          active: true,
          round: 1,
          position,
          sessionId: data.session_id,
          durationMinutes,
          totalQuestions: data.total_questions,
          jobId: data.job_id,
          sourcePostId: data.source_post_id,
        },
      })
      get().saveMessages()
      trackProductEvent('interview.start.succeeded', get().userProfile?.user_id, { position, duration_minutes: durationMinutes })
    } catch (error) {
      console.error('[Store] start interview failed', error)
      set({
        interviewState: null,
        messages: [
          ...get().messages,
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: `模拟面试没有启动成功，我没有生成本地固定题冒充真实面试。\n\n你的目标岗位「${position}」已保留，请检查模型服务后点击重试。`,
            type: 'interview',
            createdAt: Date.now(),
          }
        ],
      })
      get().saveMessages()
      trackProductEvent('interview.start.failed', get().userProfile?.user_id, { position })
    } finally {
      set({ isSending: false })
    }
  },

  requestInterviewRescue: async () => {
    const interview = get().interviewState
    const userId = get().userProfile?.user_id
    if (!interview?.active || !interview.sessionId || !userId || get().isSending) return
    set({ isSending: true })
    try {
      const result = await apiRequest<any>(`/api/v1/interview/practice/${interview.sessionId}/rescue`, 'POST', {
        user_id: userId,
      })
      set({
        messages: [...get().messages, {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: `先不推进下一题，也不替你编答案。\n\n**三步救场框架**：${result.framework}\n\n**先想一个真实细节**：${result.first_prompt}`,
          type: 'interview',
          createdAt: Date.now(),
        }],
      })
      get().saveMessages()
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '救场框架暂时不可用', icon: 'none' })
    } finally {
      set({ isSending: false })
    }
  },

  endInterview: () => {
    get().sendMessage('【结束面试】请给出本次模拟面试的综合评分和详细反馈，并总结 3 条下次可直接复用的改进话术。', 'interview')
    set({ interviewState: null })
  },

  resumeUpload: async (filePath: string, fileName: string) => {
    const now = Date.now()
    set({
      isSending: true,
      messages: [...get().messages, {
        id: `user-${now}`,
        role: 'user',
        content: `📄 上传了简历: ${fileName}`,
        type: 'resume',
        createdAt: now,
      }]
    })
    trackProductEvent('resume.analyze.started', get().userProfile?.user_id, {
      extension: fileName.split('.').pop() || '',
    })

    try {
      const analysis = await apiUploadFile<any>('/api/v1/resume/upload', filePath, fileName, {
        user_id: get().userProfile?.user_id || '',
      })

      const content = `✅ **简历诊断完成！**\n\n📄 **文件**: ${analysis.filename || fileName}\n📊 **初步评分**: ${analysis.score}/100\n\n**一句话总结**: ${analysis.summary}`

      set({
        messages: [...get().messages, {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content,
          type: 'analysis',
          createdAt: Date.now(),
        }],
      })
      get().saveMessages()
      trackProductEvent('resume.analyze.succeeded', get().userProfile?.user_id, { score: analysis.score || 0 })
    } catch (error) {
      console.error('[Store] resume upload failed', error)
      set({
        messages: [...get().messages, {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: `📄 **我暂时没法直接解析这个文件，但会话不中断。**\n\n你可以把简历里的「个人摘要 / 项目经历 / 实习经历」直接粘贴过来，我会继续按这个格式帮你改：\n\n- 原文问题\n- 优化版\n- 为什么这样改\n- 还能补哪些量化数据\n\n先粘一段最想改的项目经历就行。`,
          type: 'resume',
          createdAt: Date.now(),
        }],
      })
      get().saveMessages()
      trackProductEvent('resume.analyze.failed', get().userProfile?.user_id)
    } finally {
      set({ isSending: false })
    }
  },

  jdAnalyze: async (jdText: string) => {
    if (!jdText.trim()) return
    const now = Date.now()

    // 先设置 conversationMeta，确保页面标题和推荐内容正确
    get().openConversation('jd', '解读岗位描述')

    // 截断过长的 JD 文本用于显示
    const displayText = jdText.length > 200 ? jdText.slice(0, 200) + '...' : jdText

    set({
      isSending: true,
      messages: [...get().messages, {
        id: `user-${now}`,
        role: 'user',
        content: `📝 请帮我分析这份 JD：\n${displayText}`,
        type: 'jd',
        createdAt: now,
      }]
    })
    trackProductEvent('jd.analyze.started', get().userProfile?.user_id, {
      length_bucket: jdText.length > 2000 ? 'long' : jdText.length > 800 ? 'medium' : 'short',
    })

    try {
      const data = await apiRequest<any>('/api/v1/jd/analyze', 'POST', { jd_text: jdText })

      const content = `🎯 **JD 解读报告**\n\n**岗位画像**: ${data.summary}\n\n✅ **核心要求**:\n${(data.core_requirements || []).map((r: string) => `- ${r}`).join('\n')}\n\n🔍 **隐性要求**:\n${(data.hidden_requirements || []).map((r: string) => `- ${r}`).join('\n')}\n\n🎤 **面试重点**:\n${(data.interview_focus || []).map((f: string) => `- ${f}`).join('\n')}\n\n💰 **谈薪建议**:\n${(data.salary_negotiation_tips || []).map((t: string) => `- ${t}`).join('\n')}`

      set({
        messages: [...get().messages, {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content,
          type: 'jd',
          createdAt: Date.now(),
        }],
      })
      get().saveMessages()
      trackProductEvent('jd.analyze.succeeded', get().userProfile?.user_id)
    } catch (error) {
      console.error('[Store] JD analyze failed', error)
      set({
        messages: [...get().messages, {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: 'JD 解读没有完成，我没有用通用模板冒充针对这份岗位的分析。\n\n完整 JD 已保留在会话中；模型服务恢复后，请点击“重新分析 JD”。',
          type: 'jd',
          createdAt: Date.now(),
        }],
      })
      get().saveMessages()
      trackProductEvent('jd.analyze.failed', get().userProfile?.user_id)
    } finally {
      set({ isSending: false })
    }
  },


  confirmPendingJobEvent: async () => {
    const pending = get().pendingJobEvent
    if (!pending) return
    const userId = get().userProfile?.user_id
    if (!userId) return
    let nextItem: JobProgressItem
    try {
      const response = await apiRequest<any>('/api/v1/workspace/jobs', 'POST', {
        user_id: userId,
        company: pending.company,
        title: pending.position,
        source: 'manual',
        status: pending.status,
        jd_text: '',
      })
      nextItem = workspaceJobsToProgress([response.job])[0]
    } catch (error) {
      console.error('[Store] cloud job confirmation failed', error)
      Taro.showToast({ title: '云端记录失败，内容仍待确认', icon: 'none' })
      return
    }
    const next = [nextItem, ...get().jobProgress.filter((item) => item.id !== nextItem.id && !(item.company === nextItem.company && item.position === nextItem.position))]
    let nextTasks = get().todayTasks
    if (pending.status === 'rejected') {
      const supportTask: TodayTask = {
        id: `support-${Date.now()}`,
        title: '先照顾状态，再做复盘',
        desc: `${pending.company} 的结果不等于你的价值。先选希望学姐怎么陪你，再只复盘一个最关键卡点。`,
        done: false,
        source: 'job_progress',
        relatedJobId: nextItem.id,
        action: 'send_chat',
        scenario: 'emotion',
        prompt: `我刚收到 ${pending.company} ${pending.position} 的拒绝结果。请先按我的陪伴偏好接住情绪，再问我是否现在适合复盘；如果我说不适合，就只陪我把状态稳住。`,
        createdAt: Date.now(),
      }
      nextTasks = [supportTask, ...nextTasks.filter((task) => task.relatedJobId !== nextItem.id || task.scenario !== 'emotion')].slice(0, 12)
      try { Taro.setStorageSync(TASKS_STORAGE_KEY, JSON.stringify(nextTasks)) } catch {}
    }
    set({ jobProgress: next, pendingJobEvent: null, todayTasks: nextTasks })
    saveJobProgress(next)
    Taro.showToast({ title: '已记录到求职进度', icon: 'none' })
  },

  dismissPendingJobEvent: () => {
    set({ pendingJobEvent: null })
  },

  bindLatestMaterialToJob: (jobId, material) => {
    const next = get().jobProgress.map((item) => {
      if (item.id !== jobId) return item
      return {
        ...item,
        materials: {
          ...item.materials,
          [material]: true
        },
        updatedAt: Date.now()
      }
    })
    set({ jobProgress: next })
    saveJobProgress(next)
    Taro.showToast({ title: '已绑定到此岗位', icon: 'none' })
  },

  updateJobStatus: async (jobId, status) => {
    const userId = get().userProfile?.user_id
    if (!userId) return
    try {
      const response = await apiRequest<any>(`/api/v1/workspace/jobs/${jobId}/status`, 'POST', {
        user_id: userId,
        status,
      })
      const cloudItem = workspaceJobsToProgress([response.job])[0]
      const next = get().jobProgress.map((item) => item.id === jobId ? cloudItem : item)
      set({ jobProgress: next })
      saveJobProgress(next)
      if (response.support_action) {
        const action = response.support_action
        const result = await Taro.showModal({
          title: action.title,
          content: action.message,
          confirmText: action.action_label,
          cancelText: '先不用',
        })
        if (result.confirm) {
          Taro.navigateTo({ url: `/pages/conversation/index?scenario=emotion&prompt=${encodeURIComponent(action.prompt)}` })
        }
      } else {
        Taro.showToast({ title: '进度已同步云端', icon: 'none' })
      }
    } catch (error) {
      console.error('[Store] cloud status update failed', error)
      Taro.showToast({ title: '进度更新失败，请重试', icon: 'none' })
    }
  },

  createBookingOrder: async ({ expert_id, expert_name, topic, slot, desc, job_id, share_context_with_expert }) => {
    const userProfile = get().userProfile
    if (!userProfile) {
      Taro.showToast({ title: '请先重新进入小程序', icon: 'none' })
      return
    }
    const result = await createBooking({
      user_id: userProfile.user_id,
      expert_id,
      expert_name,
      topic,
      slot,
      desc,
      job_id,
      share_context_with_expert,
    })
    set({ bookings: result.bookings, serviceTimeline: result.service_timeline })
  },

  cancelBookingOrder: async (bookingId) => {
    const userId = get().userProfile?.user_id
    if (!userId) return
    const result = await apiRequest<any>(`/api/v1/bookings/${bookingId}/cancel`, 'POST', {
      user_id: userId,
      reason: '用户主动取消',
    })
    set({ bookings: get().bookings.map((item) => item.id === bookingId ? result.booking : item) })
  },

  refreshBookings: async () => {
    const userId = get().userProfile?.user_id
    if (!userId) return
    const result = await apiRequest<{ bookings: BookingItem[] }>(`/api/v1/bookings?user_id=${encodeURIComponent(userId)}`)
    set({ bookings: result.bookings || [] })
  },

  checkInEmotion: async (intensity, eventType = 'daily', note) => {
    const userId = get().userProfile?.user_id
    if (!userId) {
      Taro.showToast({ title: '正在建立你的用户状态，请稍后重试', icon: 'none' })
      return
    }
    const labels: Record<number, string> = { 1: '快撑不住了', 2: '很累', 3: '有点绷', 4: '还可以', 5: '有力量' }
    trackProductEvent('emotion.checkin.started', userId, { intensity, event_type: eventType })
    try {
      const data = await apiRequest<any>('/api/v1/support/check-ins', 'POST', {
        user_id: userId,
        intensity,
        event_type: eventType,
        note,
      })
      const timestamp = Date.now()
      set({
        conversationMeta: {
          title: '情感树洞',
          subtitle: '先把状态扶稳，再决定下一步',
          scenario: 'emotion',
        },
        messages: [...get().messages,
          {
            id: `user-${timestamp}`,
            role: 'user',
            content: `今日状态打卡：${labels[intensity]}（${intensity}/5）${note ? `\n${note}` : ''}`,
            type: 'text',
            createdAt: timestamp,
          },
          {
            id: `assistant-${timestamp + 1}`,
            role: 'assistant',
            content: data.response,
            type: 'text',
            createdAt: timestamp + 1,
          },
        ],
      })
      get().saveMessages()
      trackProductEvent('emotion.checkin.succeeded', userId, {
        intensity,
        crisis: Boolean(data.check_in?.crisis),
        follow_up_scheduled: Boolean(data.check_in?.follow_up_due_at),
      })
      set({ supportFeedbackCheckInId: data.check_in?.id || null })
      return data
    } catch (error) {
      console.error('[Store] emotion check-in failed', error)
      trackProductEvent('emotion.checkin.failed', userId, { intensity })
      throw error
    }
  },

  submitSupportFeedback: async (helpful, understoodScore) => {
    const userId = get().userProfile?.user_id
    const checkInId = get().supportFeedbackCheckInId
    if (!userId || !checkInId) return
    try {
      await apiRequest(`/api/v1/support/check-ins/${checkInId}/feedback`, 'POST', {
        user_id: userId,
        helpful,
        understood_score: understoodScore,
      })
      set({ supportFeedbackCheckInId: null })
      Taro.showToast({ title: helpful ? '谢谢你告诉我' : '收到，我会少些套路', icon: 'none' })
    } catch (error) {
      console.error('[Store] support feedback failed', error)
      Taro.showToast({ title: '反馈暂未保存，请重试', icon: 'none' })
    }
  },

  respondSupportFollowUp: async (checkInId, intensity, microActionCompleted) => {
    const userId = get().userProfile?.user_id
    if (!userId) return
    await get().checkInEmotion(intensity, 'follow_up')
    await apiRequest(`/api/v1/support/follow-ups/${checkInId}/respond`, 'POST', {
      user_id: userId,
      current_intensity: intensity,
      micro_action_completed: microActionCompleted,
    })
    set({ supportDueFollowUps: get().supportDueFollowUps.filter((item) => item.check_in_id !== checkInId) })
  },

  searchJobs: async (query, city) => {
    try {
      Taro.showLoading({ title: '正在搜索...' })
      const result = await apiSearchJobs({ query, city, limit: 8 })
      set({ jobSearchResults: result.jobs })
      Taro.hideLoading()
    } catch (error) {
      console.error('[Store] search jobs failed', error)
      Taro.hideLoading()
      Taro.showToast({ title: '搜索失败，请稍后重试', icon: 'none' })
    }
  },

  loadMembership: async () => {
    const userId = get().userProfile?.user_id
    if (!userId) return
    try {
      const status = await apiFetchMembershipStatus(userId)
      set({ membership: status })
    } catch (e) {
      console.error('[Store] load membership failed', e)
    }
  },

  loadConversationHistory: () => {
    try {
      const raw = Taro.getStorageSync(HISTORY_STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as ConversationSession[]
        set({ conversationHistory: parsed.filter((s) => s.id && s.messages?.length > 0) })
        return
      }
    } catch (e) {
      console.error('[Store] load conversation history failed', e)
    }
    set({ conversationHistory: [] })
  },

  createNewConversation: () => {
    const currentMessages = get().messages
    const currentMeta = get().conversationMeta
    // Only save if there's actual conversation beyond welcome
    if (currentMessages.length > 1) {
      const firstUserMsg = currentMessages.find((m) => m.role === 'user')
      const title = firstUserMsg
        ? firstUserMsg.content.slice(0, 20) + (firstUserMsg.content.length > 20 ? '...' : '')
        : currentMeta.title
      const session: ConversationSession = {
        id: `session-${Date.now()}`,
        title,
        scenario: currentMeta.scenario,
        messages: [...currentMessages],
        createdAt: currentMessages[0]?.createdAt || Date.now(),
        updatedAt: Date.now(),
      }
      const nextHistory = [session, ...get().conversationHistory].slice(0, 50)
      set({ conversationHistory: nextHistory })
      try {
        Taro.setStorageSync(HISTORY_STORAGE_KEY, JSON.stringify(nextHistory))
      } catch (e) {
        console.error('[Store] save conversation history failed', e)
      }
    }
    // Reset current conversation
    set({
      messages: [welcomeMessage],
      conversationMeta: {
        title: '专属会话',
        subtitle: '把问题交给学姐一起拆',
        scenario: 'general'
      },
      interviewState: null,
      pendingJobEvent: null,
      streamingContent: '',
      isStreaming: false,
      isSending: false,
    })
    try {
      Taro.setStorageSync(STORAGE_KEY, JSON.stringify([welcomeMessage]))
    } catch (e) {
      console.error('[Store] reset messages failed', e)
    }
    Taro.showToast({ title: '已新建对话', icon: 'success' })
  },

  switchToConversation: (sessionId) => {
    const session = get().conversationHistory.find((s) => s.id === sessionId)
    if (!session) {
      Taro.showToast({ title: '会话不存在', icon: 'none' })
      return
    }
    // Save current conversation to history first
    get().createNewConversation()
    // Load the selected session
    set({
      messages: session.messages,
      conversationMeta: {
        title: session.title,
        subtitle: '继续和学姐往下聊',
        scenario: session.scenario,
      },
    })
    try {
      Taro.setStorageSync(STORAGE_KEY, JSON.stringify(session.messages))
    } catch (e) {
      console.error('[Store] switch conversation failed', e)
    }
    Taro.showToast({ title: '已切换对话', icon: 'success' })
  },

  deleteConversation: (sessionId) => {
    const next = get().conversationHistory.filter((s) => s.id !== sessionId)
    set({ conversationHistory: next })
    try {
      Taro.setStorageSync(HISTORY_STORAGE_KEY, JSON.stringify(next))
    } catch (e) {
      console.error('[Store] delete conversation failed', e)
    }
  }
}))

// 云托管容器重启或会话过期时，当前页面不能要求用户手动清缓存。
// API 层会等待这次恢复完成，并用新身份把原请求安全地重试一次。
setApiSessionRecoveryHandler(async () => {
  const previousUserId = usePincoStore.getState().userProfile?.user_id
  const payload = await getBootstrapPayload()
  const data = await bootstrapMiniapp(payload)
  setApiSessionToken(data.session_token)
  usePincoStore.setState({
    userProfile: data.user,
    wechatReady: data.wechat_ready,
    miniappReadiness: data.miniapp_readiness,
    runtimeInfo: getMiniappRuntimeInfo(Boolean(payload.code)),
    serviceHealth: data.service_health,
    membership: data.membership || null,
    supportDueFollowUps: data.support_due || [],
  })
  console.info('[Session] recovered automatically', previousUserId === data.user.user_id ? 'same-user' : 'new-user')
  Taro.showToast({ title: '登录状态已恢复', icon: 'none' })
  return { previousUserId, userId: data.user.user_id }
})
