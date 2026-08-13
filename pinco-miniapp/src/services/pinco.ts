import { apiRequest } from '@/services/api'
import {
  BookingItem,
  CommunityPost,
  ContributionStatus,
  ConversationScenario,
  ExpertPayResponse,
  ExpertApplication,
  ExpertProfile,
  JobSearchResponse,
  MembershipPlan,
  MessageItem,
  MiniappBootstrapResponse,
  MiniappReadiness,
  PaymentCreateResponse,
  PaymentOrderStatus,
  ServiceHealth,
  ServiceTimelineItem,
  UserMembership,
} from '@/types/pinco'

interface MessageResponse {
  reply: string
  messages: MessageItem[]
}

interface BookingResponse {
  booking: BookingItem
  bookings: BookingItem[]
  service_timeline: ServiceTimelineItem[]
}

interface CommunityPostsResponse {
  posts: CommunityPost[]
}

interface CommunityPostResponse {
  post: CommunityPost
}

export const bootstrapMiniapp = async (payload: {
  device_id: string
  code?: string
  platform: string
  nickname?: string
}) => {
  return apiRequest<MiniappBootstrapResponse>('/api/v1/miniapp/bootstrap', 'POST', payload)
}

export const fetchMiniappReadiness = async () => {
  return apiRequest<MiniappReadiness>('/api/v1/miniapp/readiness')
}

export const sendMiniappMessage = async (payload: {
  user_id: string
  scenario: ConversationScenario
  content: string
}) => {
  return apiRequest<MessageResponse>('/api/v1/miniapp/message', 'POST', payload)
}

export const createBooking = async (payload: {
  user_id: string
  expert_id: string
  expert_name: string
  topic: string
  slot: string
  desc: string
  job_id?: string
  share_context_with_expert?: boolean
}) => {
  return apiRequest<BookingResponse>('/api/v1/bookings', 'POST', payload)
}

export const fetchCommunityPosts = async (userId: string) => {
  return apiRequest<CommunityPostsResponse>(`/api/v1/community/posts?user_id=${encodeURIComponent(userId)}`)
}

export const createCommunityPost = async (payload: {
  user_id: string
  title: string
  content: string
  post_type: CommunityPost['postType']
  job_id?: string
  interview_round?: string
  experience_date?: string
}) => {
  return apiRequest<CommunityPostResponse>('/api/v1/community/posts', 'POST', payload)
}

export const recordCommunityAction = async (postId: string, payload: {
  user_id: string
  action: 'practice' | 'save_job' | 'update_progress'
  job_id?: string
}) => {
  return apiRequest<{ accepted: boolean; first_action: boolean; author_points_awarded: number }>(
    `/api/v1/community/posts/${postId}/action`, 'POST', payload
  )
}

export const fetchContributionStatus = async (userId: string) => {
  return apiRequest<ContributionStatus>(`/api/v1/contributions/status?user_id=${encodeURIComponent(userId)}`)
}

export const toggleCommunityLike = async (postId: string, userId: string) => {
  return apiRequest<CommunityPostResponse>(`/api/v1/community/posts/${postId}/like`, 'POST', { user_id: userId })
}

export const toggleCommunityHug = async (postId: string, userId: string) => {
  return apiRequest<CommunityPostResponse>(`/api/v1/community/posts/${postId}/hug`, 'POST', { user_id: userId })
}

export const createCommunityComment = async (postId: string, userId: string, text: string) => {
  return apiRequest<CommunityPostResponse>(`/api/v1/community/posts/${postId}/comments`, 'POST', {
    user_id: userId,
    text,
  })
}

export const summonCommunityReply = async (postId: string, userId: string) => {
  return apiRequest<CommunityPostResponse>(`/api/v1/community/posts/${postId}/summon`, 'POST', { user_id: userId })
}

export const reportCommunityPost = async (postId: string, userId: string, reason: string) => {
  return apiRequest<{ accepted: boolean; pending_review: boolean }>(`/api/v1/community/posts/${postId}/report`, 'POST', {
    user_id: userId,
    reason,
  })
}

export const fetchServiceHealth = async (): Promise<ServiceHealth> => {
  const result = await bootstrapMiniapp({
    device_id: 'healthcheck',
    platform: 'healthcheck',
  })
  return result.service_health
}

export const searchJobs = async (payload: { query: string; city?: string; limit?: number }) => {
  return apiRequest<JobSearchResponse>('/api/v1/jobs/search', 'POST', payload)
}

export const searchJobsByPlatform = async (payload: { query: string; city?: string; platforms?: string; limit?: number }) => {
  return apiRequest<JobSearchResponse>('/api/v1/jobs/search', 'POST', payload)
}

export const fetchMembershipPlans = async (userId?: string) => {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
  return apiRequest<{ plans: MembershipPlan[] }>(`/api/v1/membership/plans${query}`)
}

export const fetchMembershipStatus = async (userId: string) => {
  return apiRequest<UserMembership>(`/api/v1/membership/status?user_id=${encodeURIComponent(userId)}`)
}

export const subscribeMembership = async (payload: {
  user_id: string
  plan_id: string
  billing_cycle: 'monthly' | 'yearly'
  payment_method?: string
  request_id: string
}) => {
  return apiRequest<PaymentCreateResponse>('/api/v1/membership/subscribe', 'POST', payload)
}

export const registerMembershipInterest = async (payload: { user_id: string; plan_id: string; billing_cycle: 'monthly' | 'yearly' }) => {
  return apiRequest<{ message: string }>('/api/v1/membership/interest', 'POST', payload)
}

export const payExpert = async (payload: {
  user_id: string
  expert_id: string
  booking_id: string
  request_id: string
  coupon_code?: string
}) => {
  return apiRequest<ExpertPayResponse>(`/api/v1/experts/${payload.expert_id}/pay`, 'POST', payload)
}

export const fetchPaymentOrder = async (orderId: string, userId: string, refresh = true) => {
  return apiRequest<PaymentOrderStatus>(
    `/api/v1/payments/orders/${encodeURIComponent(orderId)}?user_id=${encodeURIComponent(userId)}&refresh=${refresh ? 'true' : 'false'}`
  )
}

export const fetchPaymentOrders = async (userId: string, productType?: 'membership' | 'expert') => {
  const suffix = productType ? `&product_type=${productType}` : ''
  return apiRequest<{ orders: PaymentOrderStatus[] }>(
    `/api/v1/payments/orders?user_id=${encodeURIComponent(userId)}${suffix}`
  )
}

export const refundPaymentOrder = async (orderId: string, userId: string, reason: string) => {
  return apiRequest<PaymentOrderStatus>(`/api/v1/payments/orders/${encodeURIComponent(orderId)}/refund`, 'POST', {
    user_id: userId,
    reason,
  })
}

export const closePaymentOrder = async (orderId: string, userId: string) => {
  return apiRequest<PaymentOrderStatus>(`/api/v1/payments/orders/${encodeURIComponent(orderId)}/close`, 'POST', {
    user_id: userId,
  })
}

export const fetchExperts = async () => {
  return apiRequest<{ experts: ExpertProfile[] }>('/api/v1/experts')
}

export const fetchExpertApplicationStatus = async (userId: string) => {
  return apiRequest<{ application: ExpertApplication | null }>(`/api/v1/experts/applications/status?user_id=${encodeURIComponent(userId)}`)
}

export const applyAsExpert = async (payload: {
  user_id: string
  real_name: string
  title: string
  intro: string
  tags: string[]
  experience_summary: string
  proof_urls: string[]
  reference_price: number
  slots: string[]
  service_name: string
  service_deliverables: string[]
}) => {
  return apiRequest<{ application: ExpertApplication }>('/api/v1/experts/applications', 'POST', payload)
}

export const fetchMyExpertWorkspace = async (userId: string) => {
  return apiRequest<{ expert: ExpertProfile | null; bookings: BookingItem[] }>(`/api/v1/experts/me?user_id=${encodeURIComponent(userId)}`)
}

export const updateExpertAvailability = async (expertId: string, userId: string, slots: string[]) => {
  return apiRequest<{ expert: ExpertProfile }>(`/api/v1/experts/${expertId}/availability`, 'POST', {
    user_id: userId,
    slots,
  })
}

export const decideExpertBooking = async (bookingId: string, expertUserId: string, decision: 'confirmed' | 'rejected', note = '') => {
  return apiRequest<{ booking: BookingItem }>(`/api/v1/experts/bookings/${bookingId}/decision`, 'POST', {
    expert_user_id: expertUserId,
    decision,
    note,
  })
}

export const completeExpertBooking = async (bookingId: string, expertUserId: string, deliverySummary: string, nextActions: string[]) => {
  return apiRequest<{ booking: BookingItem }>(`/api/v1/experts/bookings/${bookingId}/complete`, 'POST', {
    expert_user_id: expertUserId,
    delivery_summary: deliverySummary,
    next_actions: nextActions,
  })
}

export const reviewExpertBooking = async (bookingId: string, userId: string, score: number, comment: string) => {
  return apiRequest<{ booking: BookingItem }>(`/api/v1/bookings/${bookingId}/review`, 'POST', {
    user_id: userId,
    score,
    comment,
  })
}
