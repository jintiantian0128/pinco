import React, { useEffect, useState } from 'react'
import { Text, Textarea, View, Switch } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useShareAppMessage } from '@tarojs/taro'
import classnames from 'classnames'
import styles from './index.module.scss'
import { usePincoStore } from '@/store/usePincoStore'
import { buildWechatSetupChecklist } from '@/utils/wechat'
import { BookingItem, ContributionStatus, TriageStage } from '@/types/pinco'
import { apiRequest } from '@/services/api'
import {
  closePaymentOrder,
  fetchContributionStatus,
  fetchPaymentOrder,
  payExpert,
  refundPaymentOrder,
  reviewExpertBooking,
} from '@/services/pinco'

const STAGES: Array<{ id: TriageStage; label: string }> = [
  { id: 'starting', label: '刚开始找' },
  { id: 'no_reply', label: '投了没回音' },
  { id: 'interview', label: '卡在面试' },
  { id: 'offer', label: 'Offer纠结' },
]

const TIME_OPTIONS = ['30分钟', '1小时', '2小时', '半天']
const MATERIAL_OPTIONS = ['简历', 'JD', '面试邀约', 'Offer', '都没有']
const ANXIETY_OPTIONS = ['不知道投什么', '简历没回音', '面试答不好', '不知道怎么选offer']
const PILOT_SCORE_OPTIONS = [1, 2, 3, 4, 5]

type PilotFeedback = {
  professional_value_score: number
  emotional_value_score: number
  return_intent: 'yes' | 'unsure' | 'no'
  most_helpful: string
  biggest_blocker: string
  updated_at?: string
}

const MinePage: React.FC = () => {
  const serviceHealth = usePincoStore((state) => state.serviceHealth)
  const bookings = usePincoStore((state) => state.bookings)
  const refreshServiceHealth = usePincoStore((state) => state.refreshServiceHealth)
  const userProfile = usePincoStore((state) => state.userProfile)
  const wechatReady = usePincoStore((state) => state.wechatReady)
  const miniappReadiness = usePincoStore((state) => state.miniappReadiness)
  const runtimeInfo = usePincoStore((state) => state.runtimeInfo)
  const jobProgress = usePincoStore((state) => state.jobProgress)
  const todayTasks = usePincoStore((state) => state.todayTasks)
  const toggleTodayTask = usePincoStore((state) => state.toggleTodayTask)
  const clearDoneTasks = usePincoStore((state) => state.clearDoneTasks)
  const addTodayTasks = usePincoStore((state) => state.addTodayTasks)
  const generateTasksFromTriage = usePincoStore((state) => state.generateTasksFromTriage)
  const clearMessages = usePincoStore((state) => state.clearMessages)
  const membership = usePincoStore((state) => state.membership)
  const cancelBookingOrder = usePincoStore((state) => state.cancelBookingOrder)
  const refreshBookings = usePincoStore((state) => state.refreshBookings)
  const latestBooking = bookings[0]
  const interviewJobs = jobProgress.filter((item) => ['interview1', 'interview2', 'hr'].includes(item.status))
  const appliedJobs = jobProgress.filter((item) => item.status === 'applied')
  const offerJobs = jobProgress.filter((item) => item.status === 'offer')

  const [showTriage, setShowTriage] = useState(false)
  const [triageStage, setTriageStage] = useState<TriageStage>('no_reply')
  const [triageRole, setTriageRole] = useState('')
  const [triageTime, setTriageTime] = useState('2小时')
  const [triageMaterials, setTriageMaterials] = useState<string[]>(['简历'])
  const [triageAnxiety, setTriageAnxiety] = useState('简历没回音')
  const [showDebugInfo, setShowDebugInfo] = useState(false)
  const [supportMode, setSupportMode] = useState('listen_then_action')
  const [supportFollowUp, setSupportFollowUp] = useState(true)
  const [supportMemory, setSupportMemory] = useState(false)
  const [reviewBookingId, setReviewBookingId] = useState('')
  const [reviewScore, setReviewScore] = useState(5)
  const [reviewComment, setReviewComment] = useState('')
  const [paymentBookingId, setPaymentBookingId] = useState('')
  const [contribution, setContribution] = useState<ContributionStatus | null>(null)
  const [professionalValueScore, setProfessionalValueScore] = useState(0)
  const [emotionalValueScore, setEmotionalValueScore] = useState(0)
  const [pilotReturnIntent, setPilotReturnIntent] = useState<'yes' | 'unsure' | 'no' | ''>('')
  const [pilotMostHelpful, setPilotMostHelpful] = useState('')
  const [pilotBiggestBlocker, setPilotBiggestBlocker] = useState('')
  const [pilotFeedbackSaved, setPilotFeedbackSaved] = useState(false)
  const [pilotFeedbackSaving, setPilotFeedbackSaving] = useState(false)

  const loadContribution = async () => {
    if (!userProfile?.user_id) return
    try {
      setContribution(await fetchContributionStatus(userProfile.user_id))
    } catch (error) {
      console.warn('[Mine] contribution status failed', error)
    }
  }

  const submitExpertReview = async (bookingId: string) => {
    if (!userProfile?.user_id || reviewComment.trim().length < 2) {
      Taro.showToast({ title: '请写下真实服务感受', icon: 'none' })
      return
    }
    try {
      await reviewExpertBooking(bookingId, userProfile.user_id, reviewScore, reviewComment.trim())
      setReviewBookingId('')
      setReviewComment('')
      await refreshServiceHealth()
      Taro.showToast({ title: '真实评价已发布', icon: 'success' })
    } catch (error) {
      console.error('[Mine] expert review failed', error)
      Taro.showToast({ title: '评价失败，请刷新后重试', icon: 'none' })
    }
  }

  const cancelBooking = async (booking: BookingItem) => {
    if (!userProfile?.user_id) return
    if (booking.payment_status === 'paid' && booking.payment_order_id) {
      const confirmed = await Taro.showModal({
        title: '取消并申请全额退款',
        content: '服务尚未完成，可申请原路全额退款。退款只以微信支付服务端确认结果为准。',
        confirmText: '申请退款',
      })
      if (!confirmed.confirm) return
      try {
        const result = await refundPaymentOrder(booking.payment_order_id, userProfile.user_id, '用户取消未开始的专家预约')
        await refreshBookings()
        Taro.showModal({ title: '退款已受理', content: result.message, showCancel: false })
      } catch (error: any) {
        console.error('[Mine] refund booking failed', error)
        Taro.showModal({ title: '退款未完成', content: error?.message || '预约仍保留，请勿重复申请并联系平台核对。', showCancel: false })
      }
      return
    }
    if (booking.payment_status === 'unpaid' && booking.payment_order_id) {
      try {
        const closed = await closePaymentOrder(booking.payment_order_id, userProfile.user_id)
        if (closed.status === 'paid') {
          await refreshBookings()
          Taro.showModal({ title: '支付已确认', content: '该订单实际已经支付，若仍要取消请重新点击并申请退款。', showCancel: false })
          return
        }
      } catch (error: any) {
        Taro.showModal({ title: '暂时不能取消', content: error?.message || '支付订单状态尚未核清，请不要重复支付。', showCancel: false })
        return
      }
    }
    const confirmed = await Taro.showModal({
      title: '取消预约意向',
      content: '当前没有扣款。取消后若专家已确认，时段会重新释放。',
      confirmText: '确认取消',
    })
    if (!confirmed.confirm) return
    try {
      await cancelBookingOrder(booking.id)
      Taro.showToast({ title: '已取消，未发生扣款', icon: 'none' })
    } catch (error) {
      console.error('[Mine] cancel booking failed', error)
      Taro.showToast({ title: '取消失败，请刷新重试', icon: 'none' })
    }
  }

  const payForBooking = async (booking: BookingItem) => {
    if (!userProfile?.user_id || paymentBookingId) return
    const confirmed = await Taro.showModal({
      title: '支付专家服务',
      content: `专家已确认接单。微信收银台会展示服务端计算的最终金额，参考价 ¥${booking.reference_price || 0}。`,
      confirmText: '核对并支付',
    })
    if (!confirmed.confirm) return
    setPaymentBookingId(booking.id)
    try {
      const order = await payExpert({
        user_id: userProfile.user_id,
        expert_id: booking.expertId,
        booking_id: booking.id,
        request_id: `expert-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      })
      try {
        await Taro.requestPayment(order.payment_params)
      } catch (paymentError: any) {
        const message = String(paymentError?.errMsg || paymentError?.message || '')
        if (message.includes('cancel')) {
          try {
            const closed = await closePaymentOrder(order.order_id, userProfile.user_id)
            await refreshBookings()
            Taro.showToast({ title: closed.status === 'paid' ? '支付已由服务端确认' : '已取消支付，订单已关闭', icon: 'none' })
          } catch (closeError) {
            console.error('[Mine] close expert order failed', closeError)
            Taro.showModal({ title: '订单状态待核对', content: '请不要重复支付，先查看微信支付记录并稍后刷新。', showCancel: false })
          }
          return
        }
        throw paymentError
      }
      const status = await fetchPaymentOrder(order.order_id, userProfile.user_id, true)
      await refreshBookings()
      Taro.showModal({
        title: status.status === 'paid' && status.fulfilled ? '支付成功' : '支付结果确认中',
        content: status.status === 'paid' && status.fulfilled ? '微信支付服务端已确认，预约进入待服务状态。' : `${status.message}，请勿重复支付。`,
        showCancel: false,
      })
    } catch (error: any) {
      console.error('[Mine] expert payment failed', error)
      Taro.showModal({ title: '支付未完成', content: error?.message || '请先核对微信支付记录，再决定是否重试。', showCancel: false })
    } finally {
      setPaymentBookingId('')
    }
  }

  const reconcileExpertPayment = async (booking: BookingItem) => {
    if (!userProfile?.user_id || !booking.payment_order_id || paymentBookingId) return
    setPaymentBookingId(booking.id)
    try {
      const status = await fetchPaymentOrder(booking.payment_order_id, userProfile.user_id, true)
      if (status.status === 'paid' && status.fulfilled) {
        await refreshBookings()
        Taro.showModal({ title: '支付已确认', content: '微信支付服务端已确认，预约进入待服务状态。', showCancel: false })
        return
      }
      const decision = await Taro.showModal({
        title: '支付尚未确认',
        content: `${status.message}。为避免重复支付，可以先安全关闭原订单，再重新发起。`,
        confirmText: '关闭原订单',
      })
      if (decision.confirm) {
        const closed = await closePaymentOrder(booking.payment_order_id, userProfile.user_id)
        await refreshBookings()
        Taro.showToast({ title: closed.status === 'paid' ? '支付已确认' : '原订单已关闭，可重新支付', icon: 'none' })
      }
    } catch (error: any) {
      Taro.showModal({ title: '订单状态待核对', content: error?.message || '请不要重复支付，稍后再试。', showCancel: false })
    } finally {
      setPaymentBookingId('')
    }
  }

  useEffect(() => {
    if (!userProfile?.user_id) return
    apiRequest<any>(`/api/v1/support/preferences?user_id=${encodeURIComponent(userProfile.user_id)}`)
      .then((preferences) => {
        setSupportMode(preferences.mode || 'listen_then_action')
        setSupportFollowUp(preferences.follow_up_enabled !== false)
        setSupportMemory(Boolean(preferences.memory_consent))
      })
      .catch((error) => console.warn('[Mine] load support preferences failed', error))
    apiRequest<{ feedback: PilotFeedback | null }>(`/api/v1/pilot/feedback?user_id=${encodeURIComponent(userProfile.user_id)}`)
      .then(({ feedback }) => {
        if (!feedback) return
        setProfessionalValueScore(feedback.professional_value_score)
        setEmotionalValueScore(feedback.emotional_value_score)
        setPilotReturnIntent(feedback.return_intent)
        setPilotMostHelpful(feedback.most_helpful || '')
        setPilotBiggestBlocker(feedback.biggest_blocker || '')
        setPilotFeedbackSaved(true)
      })
      .catch((error) => console.warn('[Mine] load pilot feedback failed', error))
  }, [userProfile?.user_id])

  const submitPilotFeedback = async () => {
    if (!userProfile?.user_id || pilotFeedbackSaving) return
    if (!professionalValueScore || !emotionalValueScore || !pilotReturnIntent) {
      Taro.showToast({ title: '请完成三项选择', icon: 'none' })
      return
    }
    setPilotFeedbackSaving(true)
    try {
      await apiRequest('/api/v1/pilot/feedback', 'POST', {
        user_id: userProfile.user_id,
        professional_value_score: professionalValueScore,
        emotional_value_score: emotionalValueScore,
        return_intent: pilotReturnIntent,
        most_helpful: pilotMostHelpful.trim(),
        biggest_blocker: pilotBiggestBlocker.trim(),
      })
      setPilotFeedbackSaved(true)
      Taro.showToast({ title: '已收到，感谢共创', icon: 'success' })
    } catch (error) {
      console.error('[Mine] submit pilot feedback failed', error)
      Taro.showToast({ title: '提交失败，内容仍保留', icon: 'none' })
    } finally {
      setPilotFeedbackSaving(false)
    }
  }

  const saveSupportPreferences = async (next: { mode?: string; followUp?: boolean; memory?: boolean }) => {
    if (!userProfile?.user_id) return
    const mode = next.mode ?? supportMode
    const followUp = next.followUp ?? supportFollowUp
    const memory = next.memory ?? supportMemory
    setSupportMode(mode)
    setSupportFollowUp(followUp)
    setSupportMemory(memory)
    try {
      await apiRequest('/api/v1/support/preferences', 'POST', {
        user_id: userProfile.user_id,
        mode,
        follow_up_enabled: followUp,
        memory_consent: memory,
      })
      Taro.showToast({ title: '陪伴偏好已保存', icon: 'none' })
    } catch (error) {
      console.error('[Mine] save support preferences failed', error)
      Taro.showToast({ title: '保存失败，请稍后重试', icon: 'none' })
    }
  }

  const handleCopyChecklist = async () => {
    try {
      await Taro.setClipboardData({
        data: buildWechatSetupChecklist(runtimeInfo, miniappReadiness)
      })
      Taro.showToast({ title: '接入清单已复制', icon: 'none' })
    } catch (error) {
      console.error('[Mine] copy checklist failed', error)
      Taro.showToast({ title: '复制失败，请稍后再试', icon: 'none' })
    }
  }

  const exportMyData = async () => {
    if (!userProfile?.user_id) return
    try {
      const data = await apiRequest<any>(`/api/v1/account/export?user_id=${encodeURIComponent(userProfile.user_id)}`)
      const text = JSON.stringify(data, null, 2)
      await Taro.setClipboardData({ data: text })
      const verified = await Taro.getClipboardData()
      if (verified.data !== text) throw new Error('CLIPBOARD_VERIFY_FAILED')
      Taro.showToast({ title: '个人数据已复制', icon: 'success' })
    } catch (error) {
      console.error('[Mine] export account failed', error)
      Taro.showToast({ title: '导出失败，请稍后重试', icon: 'none' })
    }
  }

  const deleteMyAccount = async () => {
    if (!userProfile?.user_id) return
    const confirmed = await Taro.showModal({
      title: '永久删除账号数据',
      content: '将删除云端会话、岗位、证据、练习、社区内容和服务记录，且无法恢复。建议先导出。确定继续吗？',
      confirmText: '永久删除',
      confirmColor: '#DC2626',
    })
    if (!confirmed.confirm) return
    try {
      await apiRequest('/api/v1/account', 'DELETE', {
        user_id: userProfile.user_id,
        confirmation: 'DELETE',
      })
      Taro.clearStorageSync()
      await Taro.showModal({ title: '数据已删除', content: '重新进入后会创建一个空白账号。', showCancel: false })
      Taro.reLaunch({ url: '/pages/conversation/index' })
    } catch (error) {
      console.error('[Mine] delete account failed', error)
      Taro.showToast({ title: '删除失败，数据仍保留', icon: 'none' })
    }
  }

  const submitTriage = () => {
    const tasks = generateTasksFromTriage(triageStage, triageRole, triageTime, triageMaterials, triageAnxiety)
    addTodayTasks(tasks)
    setShowTriage(false)
    Taro.showToast({ title: '已生成今日任务', icon: 'success' })
  }

  const handleTaskAction = (task: typeof todayTasks[0]) => {
    if (task.action === 'open_jd') {
      Taro.navigateTo({ url: '/pages/conversation/index?scenario=jd' })
    } else if (task.action === 'open_resume') {
      Taro.navigateTo({ url: '/pages/conversation/index?scenario=resume' })
    } else if (task.action === 'open_interview') {
      Taro.navigateTo({ url: '/pages/conversation/index?scenario=interview' })
    } else if (task.action === 'view_progress') {
      Taro.pageScrollTo({ selector: '.job-section', duration: 300 })
    } else if (task.action === 'send_chat' && task.prompt) {
      Taro.navigateTo({
        url: `/pages/conversation/index?scenario=${task.scenario || 'general'}&prompt=${encodeURIComponent(task.prompt)}`
      })
    }
  }

  usePullDownRefresh(() => {
    Promise.all([refreshServiceHealth(), refreshBookings(), loadContribution()]).finally(() => Taro.stopPullDownRefresh())
  })

  useDidShow(() => {
    if (userProfile?.user_id) {
      refreshBookings().catch((error) => console.warn('[Mine] refresh bookings failed', error))
      loadContribution()
    }
  })

  useShareAppMessage(() => ({
    title: 'Pinco AI职场学姐，正在微信内测中',
    path: '/pages/home/index'
  }))

  const doneCount = todayTasks.filter((t) => t.done).length

  return (
    <View className={styles.page}>
      <View className={styles.profileCard}>
        <View className={styles.avatar}>P</View>
        <View className={styles.profileMain}>
          <View className={styles.profileTop}>
            <Text className={styles.nickname}>{userProfile?.nickname || 'Pinco 新手'}</Text>
            <Text className={styles.planBadge}>{membership?.plan_name || 'Free Plan'}</Text>
            {(!membership || membership.plan_id === 'free') && (
              <View className={styles.upgradeBadge} onClick={() => Taro.navigateTo({ url: '/pages/membership/index' })}>
                <Text>升级会员</Text>
              </View>
            )}
          </View>
          <Text className={styles.desc}>今天也不用一个人硬扛。Pinco 会帮你记录进度、拆 JD、改简历和复盘面试。</Text>
          <Text className={styles.quotaText}>当前方案：{membership?.plan_name || '免费版'} · 用量以服务端实际记录为准</Text>
        </View>
      </View>

      <View className={styles.section}>

        {/* 今日任务 */}
        <View className={styles.card}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>今日任务</Text>
              <Text className={styles.cardDesc}>根据你的阶段和焦虑点，生成今天能完成的动作。</Text>
            </View>
            <View className={styles.progressBadge} onClick={() => setShowTriage(true)}>
              <Text>生成任务</Text>
            </View>
          </View>
          {todayTasks.length > 0 && (
            <View className={styles.taskMeta}>
              <Text className={styles.taskCount}>{doneCount}/{todayTasks.length} 完成</Text>
              {doneCount > 0 && (
                <Text className={styles.taskClear} onClick={clearDoneTasks}>清已完成</Text>
              )}
            </View>
          )}
          {todayTasks.length === 0 ? (
            <View className={styles.emptyProgress} onClick={() => setShowTriage(true)}>
              <Text className={styles.emptyTitle}>还没有今日任务</Text>
              <Text className={styles.emptyDesc}>点「生成任务」，Pinco会根据你当前阶段、可用时间和焦虑点，给你排3个今天能完成的动作。</Text>
            </View>
          ) : (
            <View className={styles.taskList}>
              {todayTasks.map((task) => (
                <View key={task.id} className={styles.taskItem}>
                  <View
                    className={classnames(styles.taskCheck, task.done && styles.taskCheckDone)}
                    onClick={() => toggleTodayTask(task.id)}
                  >
                    <Text>{task.done ? '✓' : ''}</Text>
                  </View>
                  <View className={styles.taskBody} onClick={() => handleTaskAction(task)}>
                    <Text className={classnames(styles.taskTitle, task.done && styles.taskTitleDone)}>{task.title}</Text>
                    <Text className={styles.taskDesc}>{task.desc}</Text>
                    {task.action && (
                      <Text className={styles.taskActionLabel}>
                        {task.action === 'open_jd' ? '去解读JD' :
                         task.action === 'open_resume' ? '去诊断简历' :
                         task.action === 'open_interview' ? '开始面试' :
                         task.action === 'view_progress' ? '看进度' : '找学姐做'} →
                      </Text>
                    )}
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>

        {/* 求职进度 */}
        <View className={styles.card} onClick={() => Taro.navigateTo({ url: '/pages/career/index' })}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>求职证据库</Text>
              <Text className={styles.cardDesc}>沉淀真实项目事实、岗位 JD 和定制材料；AI 只能重组事实，不能替你编经历。</Text>
            </View>
            <View className={styles.progressBadge}><Text>去完善</Text></View>
          </View>
        </View>

        {/* 求职进度 */}
        <View className={styles.card}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>求职进度</Text>
              <Text className={styles.cardDesc}>从对话里自动提取，用户确认后沉淀到这里。不是再造Excel，是让AI顺手帮你记。</Text>
            </View>
            <View className={styles.progressBadge} onClick={() => Taro.navigateTo({ url: '/pages/conversation/index?scenario=general&prompt=' + encodeURIComponent('帮我整理现在所有求职进度，并建议今天最该推进的三个动作。') })}>
              <Text>AI建议</Text>
            </View>
          </View>
          <View className={styles.funnelRow}>
            <View className={styles.funnelItem}>
              <Text className={styles.funnelNum}>{jobProgress.length}</Text>
              <Text className={styles.funnelLabel}>全部</Text>
            </View>
            <View className={styles.funnelItem}>
              <Text className={styles.funnelNum}>{appliedJobs.length}</Text>
              <Text className={styles.funnelLabel}>等回复</Text>
            </View>
            <View className={styles.funnelItem}>
              <Text className={styles.funnelNum}>{interviewJobs.length}</Text>
              <Text className={styles.funnelLabel}>面试中</Text>
            </View>
            <View className={styles.funnelItem}>
              <Text className={styles.funnelNum}>{offerJobs.length}</Text>
              <Text className={styles.funnelLabel}>Offer</Text>
            </View>
          </View>
          {jobProgress.length ? (
            <View className={styles.jobList}>
              {jobProgress.slice(0, 5).map((job) => (
                <View key={job.id} className={styles.jobItem} onClick={() => Taro.navigateTo({ url: '/pages/conversation/index?scenario=general&prompt=' + encodeURIComponent(`基于我的求职记录：${job.company} ${job.position} 当前${job.statusLabel}，帮我判断下一步。`) })}>
                  <View className={styles.jobMain}>
                    <Text className={styles.jobTitle}>{job.company} · {job.position}</Text>
                    <Text className={styles.jobDesc}>{job.nextAction}</Text>
                    <View className={styles.materialRow}>
                      <Text className={job.materials.resumeBound ? styles.materialOn : styles.materialOff}>简历</Text>
                      <Text className={job.materials.jdBound ? styles.materialOn : styles.materialOff}>JD</Text>
                      <Text className={job.materials.reviewBound ? styles.materialOn : styles.materialOff}>复盘</Text>
                    </View>
                  </View>
                  <View className={styles.jobSide}>
                    <Text className={styles.jobStatus}>{job.statusLabel}</Text>
                    <Text className={styles.jobDate}>{job.date}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View className={styles.emptyProgress} onClick={() => Taro.navigateTo({ url: '/pages/conversation/index?scenario=general&prompt=' + encodeURIComponent('我想开始记录求职进度，请问我公司、岗位和当前状态。') })}>
              <Text className={styles.emptyTitle}>还没有进度记录</Text>
              <Text className={styles.emptyDesc}>完成简历、模拟面试、真实面试复盘或 Offer 决策时，Pinco 会结合上下文判断是否该询问你记录进度，不会在普通问答中反复弹出。</Text>
            </View>
          )}
        </View>

        {/* 我的预约 */}
        <View className={styles.card}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>我的预约</Text>
              <Text className={styles.cardDesc}>查看已预约的专家咨询，提前准备问题。</Text>
            </View>
            <View className={styles.progressBadge} onClick={() => Taro.switchTab({ url: '/pages/experts/index' })}>
              <Text>去预约</Text>
            </View>
          </View>
          {bookings.length === 0 ? (
            <View className={styles.emptyProgress} onClick={() => Taro.switchTab({ url: '/pages/experts/index' })}>
              <Text className={styles.emptyTitle}>还没有预约</Text>
              <Text className={styles.emptyDesc}>选择适合你的专家，15分钟针对性辅导比自己想3天更有效。</Text>
            </View>
          ) : (
            <View className={styles.bookingList}>
              {bookings.map((booking) => (
                <View key={booking.id} className={styles.bookingWrap}>
                  <View className={styles.bookingItem}>
                    <View className={styles.bookingMain}>
                      <Text className={styles.bookingExpert}>{booking.expertName}</Text>
                      <Text className={styles.bookingTopic}>{booking.topic}</Text>
                      <Text className={styles.bookingSlot}>⏰ {booking.slot}</Text>
                    </View>
                    <View className={styles.bookingStatus}>
                      <Text className={styles.bookingStatusText}>{booking.status}</Text>
                    </View>
                  </View>
                  {booking.delivery_summary && <Text className={styles.bookingDelivery}>交付摘要：{booking.delivery_summary}</Text>}
                  {(booking.next_actions || []).map((item, index) => <Text key={`next-${index}`} className={styles.bookingDelivery}>下一步 {index + 1}：{item}</Text>)}
                  {booking.status_code === 'confirmed' && booking.payment_status === 'payment_required' && (
                    <View className={styles.reviewTrigger} onClick={() => payForBooking(booking)}><Text>{paymentBookingId === booking.id ? '正在创建安全订单…' : '微信支付专家服务'}</Text></View>
                  )}
                  {booking.status_code === 'confirmed' && booking.payment_status === 'unpaid' && (
                    <View className={styles.reviewTrigger} onClick={() => reconcileExpertPayment(booking)}><Text>{paymentBookingId === booking.id ? '正在核对…' : '核对待支付订单'}</Text></View>
                  )}
                  {['intent_submitted', 'confirmed'].includes(booking.status_code || '') && booking.payment_status !== 'refund_processing' && (
                    <View className={styles.reviewTrigger} onClick={() => cancelBooking(booking)}><Text>{booking.payment_status === 'paid' ? '取消并申请退款' : booking.payment_status === 'unpaid' ? '关闭支付订单并取消' : '取消预约（未扣款）'}</Text></View>
                  )}
                  {booking.status_code === 'completed' && !booking.review_id && reviewBookingId !== booking.id && (
                    <View className={styles.reviewTrigger} onClick={() => setReviewBookingId(booking.id)}><Text>评价这次真实服务</Text></View>
                  )}
                  {booking.status_code === 'completed' && !booking.review_id && reviewBookingId === booking.id && (
                    <View className={styles.reviewBox}>
                      <Text className={styles.reviewLabel}>真实评分</Text>
                      <View className={styles.scoreRow}>
                        {[1, 2, 3, 4, 5].map((score) => (
                          <Text key={score} className={reviewScore >= score ? styles.scoreActive : styles.scoreIdle} onClick={() => setReviewScore(score)}>★</Text>
                        ))}
                      </View>
                      <Textarea className={styles.reviewInput} value={reviewComment} onInput={(event) => setReviewComment(event.detail.value)} placeholder="说说哪些帮助有效、还有什么可以改进" maxlength={500} autoHeight />
                      <View className={styles.reviewSubmit} onClick={() => submitExpertReview(booking.id)}><Text>发布评价</Text></View>
                    </View>
                  )}
                </View>
              ))}
            </View>
          )}
        </View>

        <View className={styles.card}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>学社贡献</Text>
              <Text className={styles.cardDesc}>{contribution?.disclaimer || '只记录真实帮助，不承诺兑换权益。'}</Text>
            </View>
            <Text className={styles.pointsBadge}>{contribution ? `${contribution.balance} · ${contribution.level}` : '同步中'}</Text>
          </View>
          {(contribution?.rules || []).map((rule) => <Text key={rule} className={styles.cardDesc}>• {rule}</Text>)}
          {(contribution?.ledger || []).slice(0, 3).map((entry) => (
            <View key={entry.id} className={styles.rewardItem}>
              <Text className={styles.rewardTitle}>+{entry.points} · {entry.reason}</Text>
              <Text className={styles.rewardDesc}>{entry.created_at}</Text>
            </View>
          ))}
        </View>

        <View className={styles.card}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>会员权益</Text>
              <Text className={styles.cardDesc}>当前会员等级享有的专属权益</Text>
            </View>
            {(!membership || membership.plan_id === 'free') && (
              <View className={styles.progressBadge} onClick={() => Taro.navigateTo({ url: '/pages/membership/index' })}>
                <Text>升级</Text>
              </View>
            )}
          </View>
          <View className={styles.membershipGrid}>
            <View className={styles.membershipItem}>
              <Text className={styles.membershipIcon}>💬</Text>
              <Text className={styles.membershipTitle}>AI 对话</Text>
              <Text className={styles.membershipDesc}>{membership ? `${membership.ai_chat_used}/${membership.ai_chat_limit === -1 ? '∞' : membership.ai_chat_limit}` : '等待同步'}</Text>
            </View>
            <View className={styles.membershipItem}>
              <Text className={styles.membershipIcon}>📄</Text>
              <Text className={styles.membershipTitle}>简历诊断</Text>
              <Text className={styles.membershipDesc}>{membership ? `${membership.resume_used}/${membership.resume_limit === -1 ? '∞' : membership.resume_limit}` : '等待同步'}</Text>
            </View>
            <View className={styles.membershipItem}>
              <Text className={styles.membershipIcon}>🎤</Text>
              <Text className={styles.membershipTitle}>模拟面试</Text>
              <Text className={styles.membershipDesc}>{membership ? `${membership.interview_used}/${membership.interview_limit === -1 ? '∞' : membership.interview_limit}` : '等待同步'}</Text>
            </View>
            <View className={styles.membershipItem}>
              <Text className={styles.membershipIcon}>🎯</Text>
              <Text className={styles.membershipTitle}>专家折扣</Text>
              <Text className={styles.membershipDesc}>{membership && membership.expert_discount < 1 ? `${Math.round(membership.expert_discount * 100)}%` : '无'}</Text>
            </View>
          </View>
        </View>

        <View className={styles.card}>
          <Text className={styles.cardTitle}>学姐怎样陪你</Text>
          <Text className={styles.cardDesc}>同一句“我又挂了”，有人想先被听见，有人想马上复盘。你可以随时改变。</Text>
          <View className={styles.optionRowWrap}>
            {[
              { id: 'listen', label: '先听我说' },
              { id: 'listen_then_action', label: '先接住，再行动' },
              { id: 'action', label: '直接给行动' },
              { id: 'direct', label: '坦率点醒我' },
            ].map((option) => (
              <View
                key={option.id}
                className={classnames(styles.optionChip, supportMode === option.id && styles.optionChipActive)}
                onClick={() => saveSupportPreferences({ mode: option.id })}
              >
                <Text className={styles.optionChipText}>{option.label}</Text>
              </View>
            ))}
          </View>
          <View className={styles.settingRow}>
            <View>
              <Text className={styles.settingLabel}>低落时隔天问候</Text>
              <Text className={styles.cardDesc}>状态打卡 ≤2 分时安排一次跟进</Text>
            </View>
            <Switch checked={supportFollowUp} onChange={(event) => saveSupportPreferences({ followUp: event.detail.value })} color="#EC4899" />
          </View>
          <View className={styles.settingRow}>
            <View>
              <Text className={styles.settingLabel}>允许记住倾诉正文</Text>
              <Text className={styles.cardDesc}>默认关闭；关闭时只存状态分数和事件类型</Text>
            </View>
            <Switch checked={supportMemory} onChange={(event) => saveSupportPreferences({ memory: event.detail.value })} color="#EC4899" />
          </View>
          <Text className={styles.cardDesc}>出现自伤风险时，Pinco 会优先提示联系可信任的人、12356 心理援助热线及紧急服务；Pinco 不替代医疗或危机干预。</Text>
        </View>

        <View className={classnames(styles.card, styles.pilotCard)}>
          <View className={styles.progressHeader}>
            <View>
              <Text className={styles.cardTitle}>首批用户共创</Text>
              <Text className={styles.cardDesc}>不是满意度作业。告诉我们 Pinco 是否真的推进了求职、有没有让你感到被理解。正文只用于产品迭代，不会公开。</Text>
            </View>
            {pilotFeedbackSaved && <Text className={styles.pilotSaved}>已提交</Text>}
          </View>

          <Text className={styles.pilotQuestion}>对求职推进有帮助</Text>
          <View className={styles.pilotScoreRow}>
            {PILOT_SCORE_OPTIONS.map((score) => (
              <View
                key={`professional-${score}`}
                className={classnames(styles.pilotScore, professionalValueScore === score && styles.pilotScoreActive)}
                onClick={() => { setProfessionalValueScore(score); setPilotFeedbackSaved(false) }}
              >
                <Text>{score}</Text>
              </View>
            ))}
          </View>
          <View className={styles.pilotScale}><Text>几乎没有</Text><Text>非常有用</Text></View>

          <Text className={styles.pilotQuestion}>让我感到被理解和支持</Text>
          <View className={styles.pilotScoreRow}>
            {PILOT_SCORE_OPTIONS.map((score) => (
              <View
                key={`emotional-${score}`}
                className={classnames(styles.pilotScore, emotionalValueScore === score && styles.pilotScoreActive)}
                onClick={() => { setEmotionalValueScore(score); setPilotFeedbackSaved(false) }}
              >
                <Text>{score}</Text>
              </View>
            ))}
          </View>
          <View className={styles.pilotScale}><Text>几乎没有</Text><Text>非常明显</Text></View>

          <Text className={styles.pilotQuestion}>未来 7 天，你会继续使用 Pinco 吗？</Text>
          <View className={styles.optionRowWrap}>
            {[
              { id: 'yes', label: '会' },
              { id: 'unsure', label: '不确定' },
              { id: 'no', label: '不会' },
            ].map((option) => (
              <View
                key={option.id}
                className={classnames(styles.optionChip, pilotReturnIntent === option.id && styles.optionChipActive)}
                onClick={() => { setPilotReturnIntent(option.id as 'yes' | 'unsure' | 'no'); setPilotFeedbackSaved(false) }}
              >
                <Text className={styles.optionChipText}>{option.label}</Text>
              </View>
            ))}
          </View>

          <Textarea
            className={styles.pilotInput}
            value={pilotMostHelpful}
            onInput={(event) => { setPilotMostHelpful(event.detail.value); setPilotFeedbackSaved(false) }}
            placeholder="哪一步最有帮助？（选填）"
            maxlength={500}
          />
          <Textarea
            className={styles.pilotInput}
            value={pilotBiggestBlocker}
            onInput={(event) => { setPilotBiggestBlocker(event.detail.value); setPilotFeedbackSaved(false) }}
            placeholder="你现在最大的卡点是什么？（选填）"
            maxlength={500}
          />
          <View className={classnames(styles.pilotSubmit, pilotFeedbackSaving && styles.pilotSubmitDisabled)} onClick={submitPilotFeedback}>
            <Text>{pilotFeedbackSaving ? '正在提交…' : pilotFeedbackSaved ? '更新我的反馈' : '提交共创反馈'}</Text>
          </View>
        </View>

        <View className={styles.card}>
          <Text className={styles.cardTitle}>设置</Text>
          <View className={styles.settingList}>
            <View className={styles.settingRow} onClick={() => Taro.navigateTo({ url: '/pages/conversation/index?scenario=resume&prompt=' + encodeURIComponent('帮我查看最近的简历诊断历史，并总结下一步优化重点。') })}>
              <Text className={styles.settingLabel}>诊断历史</Text>
              <Text className={styles.settingArrow}>›</Text>
            </View>
            <View className={styles.settingRow} onClick={() => Taro.navigateTo({ url: '/pages/conversation/index?scenario=general&prompt=' + encodeURIComponent('帮我解释当前模型配置，并告诉我怎样获得更稳定的回复。') })}>
              <Text className={styles.settingLabel}>模型配置</Text>
              <Text className={styles.settingArrow}>›</Text>
            </View>
            <View className={styles.settingRow} onClick={() => {
              Taro.showModal({
                title: '清空对话',
                content: '确定要清空所有对话记录吗？此操作不可恢复。',
                success: async (res) => {
                  if (res.confirm) {
                    try {
                      await clearMessages()
                      Taro.showToast({ title: '云端对话已清空', icon: 'success' })
                    } catch (error) {
                      console.error('[Mine] clear cloud messages failed', error)
                      Taro.showToast({ title: '清空失败，记录仍保留', icon: 'none' })
                    }
                  }
                }
              })
            }}>
              <Text className={styles.settingLabel}>清空对话</Text>
              <Text className={styles.settingDanger}>清空</Text>
            </View>
            <View className={styles.settingRow} onClick={exportMyData}>
              <Text className={styles.settingLabel}>导出我的数据</Text>
              <Text className={styles.settingArrow}>›</Text>
            </View>
            <View className={styles.settingRow} onClick={deleteMyAccount}>
              <Text className={styles.settingLabel}>删除账号与云端数据</Text>
              <Text className={styles.settingDanger}>删除</Text>
            </View>
            <View className={styles.settingRow}>
              <Text className={styles.settingLabel}>调试信息</Text>
              <Switch checked={showDebugInfo} onChange={(e) => setShowDebugInfo(e.detail.value)} color="#EC4899" />
            </View>
          </View>
        </View>

        {showDebugInfo && (
          <>
            <View className={styles.card}>
              <Text className={styles.cardTitle}>模型服务状态</Text>
              <Text className={styles.cardDesc}>{serviceHealth.summary}</Text>
              <View className={styles.statusRow}>
                <Text className={classnames(styles.statusBadge, serviceHealth.online ? styles.online : styles.offline)}>
                  {serviceHealth.online ? '服务在线' : '服务不可达'}
                </Text>
                <View className={styles.inlineButton} onClick={() => refreshServiceHealth()}>
                  <Text>刷新状态</Text>
                </View>
              </View>
            </View>

            <View className={styles.card}>
              <Text className={styles.cardTitle}>微信内测准备度</Text>
              <Text className={styles.cardDesc}>{miniappReadiness?.summary || '正在检查小程序接入条件...'}</Text>
              <View className={styles.checklist}>
                {(miniappReadiness?.items || []).map((item) => (
                  <View key={item.key} className={styles.checkItem}>
                    <View className={classnames(styles.checkMark, item.ready ? styles.checkMarkReady : styles.checkMarkPending)}>
                      <Text>{item.ready ? '✓' : '!'}</Text>
                    </View>
                    <View>
                      <Text className={styles.checkLabel}>{item.label}</Text>
                      <Text className={styles.checkDetail}>{item.detail}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            <View className={styles.card}>
              <Text className={styles.cardTitle}>当前运行态</Text>
              <Text className={styles.cardDesc}>这里展示的是开发者工具当前真正跑起来的环境。</Text>
              <View className={styles.runtimeList}>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>平台</Text>
                  <Text className={styles.runtimeValue}>{runtimeInfo.platform}</Text>
                </View>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>AppID</Text>
                  <Text className={styles.runtimeValue}>{runtimeInfo.isTouristAppId ? 'touristappid（待替换）' : runtimeInfo.appId}</Text>
                </View>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>环境版本</Text>
                  <Text className={styles.runtimeValue}>{runtimeInfo.envVersion}</Text>
                </View>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>API域名</Text>
                  <Text className={styles.runtimeValue}>{runtimeInfo.apiBaseUrl}</Text>
                </View>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>登录code</Text>
                  <Text className={styles.runtimeValue}>{runtimeInfo.loginCodeReady ? '已获取' : '未获取'}</Text>
                </View>
              </View>
              <View className={styles.actionRow}>
                <View className={styles.inlineButton} onClick={handleCopyChecklist}>
                  <Text>复制接入清单</Text>
                </View>
              </View>
            </View>

            <View className={styles.card}>
              <Text className={styles.cardTitle}>微信接入状态</Text>
              <Text className={styles.cardDesc}>{wechatReady ? '后端和域名条件已齐，可以进入更稳定的真机内测。' : '后端微信凭证已接入，但还没完成全部内测条件时，状态会继续显示未完成。'}</Text>
              <View className={styles.runtimeList}>
                <View className={styles.runtimeRow}>
                  <Text className={styles.runtimeLabel}>当前用户微信态</Text>
                  <Text className={styles.runtimeValue}>{userProfile?.wechat_bound ? `已拿到openid线索 · ${userProfile?.wechat_openid_hint || ''}` : '还没确认成功换到openid'}</Text>
                </View>
              </View>
            </View>

            <View className={styles.card}>
              <Text className={styles.cardTitle}>内测用户标识</Text>
              <Text className={styles.cardDesc}>{userProfile?.user_id || '尚未拿到用户标识'}</Text>
            </View>
          </>
        )}

      </View>

      {/* Triage Modal */}
      {showTriage && (
        <View className={styles.triageOverlay} onClick={() => setShowTriage(false)}>
          <View className={styles.triageModal} onClick={(e) => e.stopPropagation()}>
            <Text className={styles.triageTitle}>让学姐排优先级</Text>
            <Text className={styles.triageSubtitle}>30秒告诉我当前阶段，我直接给你生成今天的3个任务。</Text>

            <View className={styles.triageSection}>
              <Text className={styles.triageLabel}>你现在卡在哪一段？</Text>
              <View className={styles.stageGrid}>
                {STAGES.map((item) => (
                  <View
                    key={item.id}
                    className={classnames(styles.stageChip, triageStage === item.id && styles.stageChipActive)}
                    onClick={() => setTriageStage(item.id)}
                  >
                    <Text className={styles.stageChipText}>{item.label}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View className={styles.triageSection}>
              <Text className={styles.triageLabel}>目标岗位</Text>
              <Textarea
                className={styles.triageInput}
                value={triageRole}
                onInput={(e) => setTriageRole(e.detail.value)}
                placeholder="例如：AI产品经理"
                maxlength={50}
                autoHeight
                showConfirmBar={false}
              />
            </View>

            <View className={styles.triageSection}>
              <Text className={styles.triageLabel}>今天可用时间</Text>
              <View className={styles.optionRow}>
                {TIME_OPTIONS.map((item) => (
                  <View
                    key={item}
                    className={classnames(styles.optionChip, triageTime === item && styles.optionChipActive)}
                    onClick={() => setTriageTime(item)}
                  >
                    <Text className={styles.optionChipText}>{item}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View className={styles.triageSection}>
              <Text className={styles.triageLabel}>手上有什么材料？</Text>
              <View className={styles.optionRowWrap}>
                {MATERIAL_OPTIONS.map((material) => {
                  const active = triageMaterials.includes(material)
                  return (
                    <View
                      key={material}
                      className={classnames(styles.optionChip, active && styles.optionChipActive)}
                      onClick={() => {
                        if (material === '都没有') {
                          setTriageMaterials(['都没有'])
                        } else {
                          setTriageMaterials((prev) =>
                            active ? prev.filter((i) => i !== material) : [...prev.filter((i) => i !== '都没有'), material]
                          )
                        }
                      }}
                    >
                      <Text className={styles.optionChipText}>{material}</Text>
                    </View>
                  )
                })}
              </View>
            </View>

            <View className={styles.triageSection}>
              <Text className={styles.triageLabel}>现在最焦虑什么？</Text>
              <View className={styles.optionRowWrap}>
                {ANXIETY_OPTIONS.map((item) => (
                  <View
                    key={item}
                    className={classnames(styles.optionChip, triageAnxiety === item && styles.optionChipActive)}
                    onClick={() => setTriageAnxiety(item)}
                  >
                    <Text className={styles.optionChipText}>{item}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View className={styles.triageSubmit} onClick={submitTriage}>
              <Text className={styles.triageSubmitText}>生成今天3个任务</Text>
            </View>
          </View>
        </View>
      )}
    </View>
  )
}

export default MinePage
