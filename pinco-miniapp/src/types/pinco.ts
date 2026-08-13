export type ConversationScenario = 'general' | 'resume' | 'interview' | 'emotion' | 'expert' | 'garden' | 'jd'

export type MessageType = 'text' | 'analysis' | 'interview' | 'jd' | 'resume' | 'image' | 'voice'

export interface MessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  type?: MessageType
  mediaUrl?: string
  fileName?: string
  duration?: number
  createdAt: number
  feedback?: 'like' | 'dislike' | null
}

export interface InterviewState {
  active: boolean
  round: number
  position: string
  sessionId?: string
  durationMinutes?: 5 | 10 | 20 | 30
  totalQuestions?: number
  jobId?: string
  sourcePostId?: string
}

export type JobStatus = 'saved' | 'applied' | 'written' | 'interview1' | 'interview2' | 'hr' | 'offer' | 'rejected'

export interface JobMaterials {
  resumeBound?: boolean
  jdBound?: boolean
  reviewBound?: boolean
  resumeNote?: string
  jdNote?: string
  reviewNote?: string
}

export interface JobProgressItem {
  id: string
  company: string
  position: string
  status: JobStatus
  statusLabel: string
  date: string
  nextAction: string
  source: 'ai' | 'manual'
  materials: JobMaterials
  updatedAt: number
}

export interface PendingJobEvent {
  id: string
  company: string
  position: string
  status: JobStatus
  statusLabel: string
  date: string
  confidence: number
  rawText: string
}

export type TriageStage = 'starting' | 'no_reply' | 'interview' | 'offer'

export type TodayTaskSource = 'triage' | 'job_progress' | 'resume' | 'jd' | 'interview'

export type TodayTaskAction = 'open_jd' | 'open_resume' | 'open_interview' | 'send_chat' | 'open_triage' | 'view_progress' | 'chat' | 'booking' | 'circle'

export interface TodayTask {
  id: string
  title: string
  desc: string
  done: boolean
  source: TodayTaskSource
  relatedJobId?: string
  action?: TodayTaskAction
  scenario?: ConversationScenario
  emoji?: string
  prompt?: string
  createdAt: number
}

export interface ServiceTimelineItem {
  id: string
  title: string
  desc: string
  status: 'active' | 'done' | 'pending'
}

export interface HomeActionItem {
  id: string
  title: string
  subtitle: string
  scenario: ConversationScenario
  prompt: string
  tone: 'purple' | 'pink' | 'orange' | 'emerald'
}

export interface GardenArticle {
  id: string
  category: string
  title: string
  subtitle: string
  content: string[]
  reads: string
  highlight: string
}

export interface CommunityComment {
  id: string
  author: string
  text: string
  isAi: boolean
}

export type PostType = 'treehole' | 'help' | 'share' | 'success'

export interface CommunityPost {
  id: string
  author: string
  roleTag: string
  time: string
  title: string
  content: string
  likes: number
  isLiked: boolean
  aiCommentLoading: boolean
  hasAiComment: boolean
  comments: CommunityComment[]
  postType: PostType
  hugs?: number
  isHugged?: boolean
  isExample?: boolean
  boundJobId?: string
  boundJobLabel?: string
  experienceRound?: string
  experienceDate?: string
  isFeatured?: boolean
  actionStarts?: number
}

export interface ExpertProfile {
  id: string
  name: string
  title: string
  intro: string
  tags: string[]
  price: number
  nextSlot: string
  rating: number
  servedCount: number
  slots: string[]
  verificationStatus: string
  isDemo?: boolean
  serviceName: string
  deliverables: string[]
  durationMinutes: number
  reviews?: Array<{ id: string; score: number; comment: string; created_at: string }>
}

export interface BookingItem {
  id: string
  expertId: string
  expertName: string
  topic: string
  slot: string
  desc: string
  status: '平台匹配中' | '待专家确认' | '待付款' | '待服务' | '退款处理中' | '已取消并退款' | '专家未接单' | '待评价' | '已完成' | '已取消' | '待连线' | '已预约'
  status_code?: 'intent_submitted' | 'confirmed' | 'rejected' | 'completed' | 'cancelled'
  delivery_summary?: string
  next_actions?: string[]
  expert_briefing?: {
    consented_at: string
    job: { label: string; jd_excerpt: string; fit_decision?: string; fit_reasons?: string[]; gaps?: string[] }
    evidence: Array<{ title: string; action: string; result: string; metrics?: string }>
    latest_practice?: { position: string; overall_score?: number; priority_improvements?: string[] } | null
    key_questions: string[]
    privacy_note: string
  } | null
  review_id?: string
  payment_status?: 'not_charged_beta' | 'awaiting_expert_confirmation' | 'payment_required' | 'unpaid' | 'paid' | 'refund_processing' | 'refunded'
  payment_order_id?: string
  reference_price?: number
  refund_status?: 'not_applicable_not_charged' | 'processing' | 'success' | 'failed'
  job_id?: string
  job_label?: string
}

export interface ExpertApplication {
  id: string
  user_id: string
  real_name: string
  title: string
  intro: string
  tags: string[]
  reference_price: number
  slots: string[]
  status: 'pending' | 'approved' | 'rejected' | 'changes_requested'
  review_note: string
  service_name?: string
  service_deliverables?: string[]
  created_at: string
  updated_at: string
}

export interface ServiceHealth {
  online: boolean
  model: string
  provider: string
  mockMode: boolean
  summary: string
}

export interface UserProfile {
  user_id: string
  nickname: string
  platform: string
  wechat_bound: boolean
  wechat_openid_hint?: string
  created_at?: string
  last_seen_at?: string
}

export interface MiniappReadinessItem {
  key: string
  label: string
  ready: boolean
  detail: string
}

export interface MiniappReadiness {
  ready: boolean
  ready_count: number
  total_count: number
  summary: string
  items: MiniappReadinessItem[]
  next_steps: string[]
}

export interface MiniappRuntimeInfo {
  platform: string
  apiBaseUrl: string
  appId: string
  envVersion: string
  isTouristAppId: boolean
  loginCodeReady: boolean
}

export type JobPlatform = 'maimai' | 'liepin' | 'jike' | 'official' | 'all'

export interface JobSearchResult {
  title: string
  company: string
  location: string
  salary?: string
  summary: string
  url?: string
  source: string
  platform?: string
  posted_at?: string
  verified_source?: boolean
  retrieved_at?: string
  source_status?: 'provider_listing' | 'listing_signals_verified' | 'source_link_only' | 'expired' | 'unreachable'
  verification_note?: string
}

export interface JobSearchResponse {
  query: string
  total: number
  jobs: JobSearchResult[]
  query_analysis?: {
    status?: string
    message?: string
    providers?: Array<{ provider: string; count: number; ok: boolean }>
  }
}

export interface ConversationSession {
  id: string
  title: string
  scenario: ConversationScenario
  messages: MessageItem[]
  createdAt: number
  updatedAt: number
}

export interface MiniappBootstrapResponse {
  session_token: string
  user: UserProfile
  messages: MessageItem[]
  bookings: BookingItem[]
  service_timeline: ServiceTimelineItem[]
  service_health: ServiceHealth
  wechat_ready: boolean
  miniapp_readiness: MiniappReadiness
  community_posts: CommunityPost[]
  membership?: UserMembership
  workspace?: CareerWorkspace
  support_due?: SupportFollowUp[]
}

export interface SupportFollowUp {
  check_in_id: string
  event_type: string
  previous_intensity: number
  due_at: string
  message: string
}

export interface CareerProfile {
  target_roles: string[]
  years_experience: number
  cities: string[]
  strengths: string[]
  job_search_deadline?: string
  updated_at?: string
}

export interface CareerEvidence {
  id: string
  title: string
  situation: string
  action: string
  result: string
  metrics: string
  skills: string[]
  created_at: string
}

export interface WorkspaceJob {
  id: string
  title: string
  company: string
  location: string
  source: string
  source_url?: string
  source_checked_at?: string
  source_status?: 'linked_at_save' | 'user_provided' | 'expired' | 'unreachable'
  jd_text: string
  status: string
  materials?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface CareerWorkspace {
  career_profile: CareerProfile
  career_memory: Record<string, { value: string; confidence: number; source: string; updated_at?: string }>
  evidence: CareerEvidence[]
  jobs: WorkspaceJob[]
  interview_sessions: any[]
  resume_analyses: any[]
  capability_radar?: {
    target_track?: string
    next_gap?: { key: string; label: string; score: number; suggestion?: string }
    dimensions: Array<{ key: string; label: string; score: number; source: string; evidence_ids?: string[] }>
    disclaimer: string
  }
  learning_plan?: {
    id: string
    week_start: string
    target_track?: string
    focus_dimension: { key: string; label: string; score: number }
    target_output: string
    days: Array<{ day: number; title: string; action: string; evidence_output: string; completed: boolean }>
    completed_count: number
    decision_counts: Record<string, number>
    next_batch_strategy: string
    disclaimer: string
  }
}

export interface ContributionStatus {
  balance: number
  level: string
  rules: string[]
  ledger: Array<{ id: string; points: number; reason: string; created_at: string; post_id?: string }>
  disclaimer: string
}

export interface MembershipPlan {
  id: string
  name: string
  price: number
  price_yearly?: number
  features: string[]
  ai_chat_limit: number
  resume_analysis_limit: number
  mock_interview_limit: number
  expert_discount: number
  job_search_platforms: string[]
  purchasable: boolean
  billing_note: string
}

export interface UserMembership {
  plan_id: string
  plan_name: string
  expire_at?: string
  ai_chat_used: number
  ai_chat_limit: number
  resume_used: number
  resume_limit: number
  interview_used: number
  interview_limit: number
  expert_discount: number
  usage_reset_at?: string
}

export interface ExpertPayResponse {
  success: boolean
  order_id: string
  expert_id: string
  expert_name: string
  topic: string
  original_price: number
  discount: number
  actual_price: number
  final_price: number
  payment_method: 'wechat'
  slot: string
  booking_id: string
  payment_params: WechatPaymentParams
}

export interface WechatPaymentParams {
  timeStamp: string
  nonceStr: string
  package: string
  signType: 'RSA'
  paySign: string
}

export interface PaymentCreateResponse {
  success: boolean
  order_id: string
  amount_total: number
  currency: 'CNY'
  payment_params: WechatPaymentParams
  message: string
}

export interface PaymentOrderStatus {
  order_id: string
  status: 'creating' | 'unpaid' | 'paid' | 'failed' | 'closed' | 'refund_processing' | 'refunded' | 'refund_failed'
  product_type: 'membership' | 'expert'
  amount_total: number
  currency: 'CNY'
  fulfilled: boolean
  message: string
}
