import React, { useState } from 'react'
import { Input, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import styles from './index.module.scss'
import { BookingItem, ExpertApplication, ExpertProfile } from '@/types/pinco'
import {
  applyAsExpert,
  completeExpertBooking,
  decideExpertBooking,
  fetchExpertApplicationStatus,
  fetchMyExpertWorkspace,
  updateExpertAvailability,
} from '@/services/pinco'
import { usePincoStore } from '@/store/usePincoStore'

const statusText: Record<string, string> = {
  pending: '平台审核中',
  approved: '审核已通过',
  rejected: '本次未通过',
  changes_requested: '需要补充资料',
}

const ExpertCenterPage: React.FC = () => {
  const userProfile = usePincoStore((state) => state.userProfile)
  const [application, setApplication] = useState<ExpertApplication | null>(null)
  const [expert, setExpert] = useState<ExpertProfile | null>(null)
  const [bookings, setBookings] = useState<BookingItem[]>([])
  const [realName, setRealName] = useState('')
  const [title, setTitle] = useState('')
  const [intro, setIntro] = useState('')
  const [tags, setTags] = useState('')
  const [proofUrls, setProofUrls] = useState('')
  const [slotText, setSlotText] = useState('')
  const [deliveryBookingId, setDeliveryBookingId] = useState('')
  const [deliverySummary, setDeliverySummary] = useState('')
  const [deliveryNextActions, setDeliveryNextActions] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')

  const load = async () => {
    if (!userProfile?.user_id) {
      setLoadError('身份正在准备，请返回后稍后再进入。')
      return
    }
    const [statusResult, workspaceResult] = await Promise.allSettled([
      fetchExpertApplicationStatus(userProfile.user_id),
      fetchMyExpertWorkspace(userProfile.user_id),
    ])
    const errors: string[] = []
    if (statusResult.status === 'fulfilled') {
      const nextApplication = statusResult.value.application
      setApplication(nextApplication)
      if (nextApplication && ['rejected', 'changes_requested'].includes(nextApplication.status)) {
        setRealName(nextApplication.real_name || '')
        setTitle(nextApplication.title || '')
        setIntro(nextApplication.intro || '')
        setTags((nextApplication.tags || []).join('，'))
        setSlotText((nextApplication.slots || []).join('\n'))
      }
    } else {
      console.error('[ExpertCenter] status load failed', statusResult.reason)
      errors.push('申请状态暂时无法读取')
    }
    if (workspaceResult.status === 'fulfilled') {
      const workspace = workspaceResult.value
      setExpert(workspace.expert)
      setBookings(workspace.bookings || [])
      if (workspace.expert) setSlotText(workspace.expert.slots.join('\n'))
    } else {
      console.error('[ExpertCenter] workspace load failed', workspaceResult.reason)
      errors.push('预约工作台暂时无法读取')
    }
    setLoadError(errors.join('；'))
  }

  useDidShow(load)

  const submitApplication = async () => {
    if (!userProfile?.user_id || loading) return
    const normalizedProofUrls = proofUrls.split('\n').map((item) => item.trim()).filter(Boolean)
    const validationError = realName.trim().length < 2 ? '真实姓名至少填写 2 个字'
      : title.trim().length < 2 ? '专业头衔至少填写 2 个字'
      : intro.trim().length < 20 ? '对求职者的介绍至少填写 20 个字'
      : normalizedProofUrls.length === 0 ? '请至少填写一个可核验的证明链接'
      : normalizedProofUrls.some((url) => !/^https?:\/\//i.test(url)) ? '证明链接需要以 http:// 或 https:// 开头'
      : ''
    if (validationError) {
      Taro.showToast({ title: validationError, icon: 'none', duration: 3000 })
      return
    }
    setLoading(true)
    try {
      const result = await applyAsExpert({
        user_id: userProfile.user_id,
        real_name: realName.trim(),
        title: title.trim(),
        intro: intro.trim(),
        tags: tags.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean),
        experience_summary: intro.trim(),
        proof_urls: normalizedProofUrls,
        reference_price: 0,
        slots: [],
        service_name: '30分钟求职问题诊断',
        service_deliverables: ['问题诊断', '下一步行动清单'],
      })
      setApplication(result.application)
      Taro.showModal({
        title: '申请已进入审核',
        content: '平台会核验履历与作品链接。审核通过前不会在专家市场展示，也不会接收预约。',
        showCancel: false,
      })
    } catch (error: any) {
      console.error('[ExpertCenter] apply failed', error)
      Taro.showToast({ title: error?.message || '提交失败，请检查资料', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const saveAvailability = async () => {
    if (!expert || !userProfile?.user_id || loading) return
    setLoading(true)
    try {
      const result = await updateExpertAvailability(
        expert.id,
        userProfile.user_id,
        slotText.split(/\n/).map((item) => item.trim()).filter(Boolean),
      )
      setExpert(result.expert)
      Taro.showToast({ title: '真实档期已更新', icon: 'success' })
    } catch (error) {
      console.error('[ExpertCenter] slots failed', error)
      Taro.showToast({ title: '档期更新失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const decide = async (booking: BookingItem, decision: 'confirmed' | 'rejected') => {
    if (!userProfile?.user_id || loading) return
    setLoading(true)
    try {
      const result = await decideExpertBooking(booking.id, userProfile.user_id, decision)
      setBookings((prev) => prev.map((item) => item.id === booking.id ? result.booking : item))
      Taro.showToast({ title: decision === 'confirmed' ? '已确认接单' : '已拒绝预约', icon: 'none' })
    } catch (error) {
      console.error('[ExpertCenter] decision failed', error)
      Taro.showToast({ title: '处理失败，请刷新重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const complete = async (booking: BookingItem) => {
    const nextActions = deliveryNextActions.split(/\n/).map((item) => item.trim()).filter(Boolean)
    if (!userProfile?.user_id || deliverySummary.trim().length < 10 || nextActions.length === 0 || loading) {
      Taro.showToast({ title: '请填写交付摘要和至少1条下一步', icon: 'none' })
      return
    }
    setLoading(true)
    try {
      const result = await completeExpertBooking(booking.id, userProfile.user_id, deliverySummary.trim(), nextActions)
      setBookings((prev) => prev.map((item) => item.id === booking.id ? result.booking : item))
      setDeliveryBookingId('')
      setDeliverySummary('')
      setDeliveryNextActions('')
      Taro.showToast({ title: '服务已交付，等待评价', icon: 'success' })
    } catch (error) {
      console.error('[ExpertCenter] complete failed', error)
      Taro.showToast({ title: '交付失败，请重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const canApply = !application || ['rejected', 'changes_requested'].includes(application.status)

  return (
    <View className={styles.page}>
      <View className={styles.hero}>
        <Text className={styles.title}>开放专家工作台</Text>
        <Text className={styles.desc}>先核验，后展示；先确认服务，再形成真实评价。平台不会自动伪造履历、档期或评分。</Text>
      </View>

      {loadError && (
        <View className={styles.warningCard} onClick={load}>
          <Text className={styles.warningTitle}>部分数据加载失败</Text>
          <Text className={styles.warningText}>{loadError}。申请表仍可填写，点这里重试加载。</Text>
        </View>
      )}

      {application && (
        <View className={styles.statusCard}>
          <Text className={styles.statusTitle}>{statusText[application.status] || application.status}</Text>
          <Text className={styles.statusDesc}>申请人：{application.real_name} · {application.title}</Text>
          {application.review_note && <Text className={styles.reviewNote}>审核意见：{application.review_note}</Text>}
        </View>
      )}

      {canApply && (
        <View className={styles.card}>
          <Text className={styles.sectionTitle}>{application ? '补充并重新申请' : '申请成为专家'}</Text>
          <Text className={styles.hint}>首步只收集 4 项核心资料。服务包、价格和档期在审核通过后再配置。</Text>
          <Text className={styles.label}>真实姓名 *</Text>
          <Input className={styles.input} value={realName} onInput={(event) => setRealName(event.detail.value)} placeholder="用于平台核验和公开展示" maxlength={30} />
          <Text className={styles.label}>专业头衔 *</Text>
          <Input className={styles.input} value={title} onInput={(event) => setTitle(event.detail.value)} placeholder="公司/岗位/专业方向，请如实填写" maxlength={80} />
          <Text className={styles.label}>你能帮谁解决什么问题 *</Text>
          <Textarea className={styles.textarea} value={intro} onInput={(event) => setIntro(event.detail.value)} placeholder="适合帮助什么人、解决什么问题（至少20字）" maxlength={600} cursorSpacing={24} disableDefaultPadding showConfirmBar={false} />
          <Text className={styles.fieldCount}>{intro.length}/600</Text>
          <Text className={styles.label}>擅长标签（可选）</Text>
          <Input className={styles.input} value={tags} onInput={(event) => setTags(event.detail.value)} placeholder="用逗号分隔，如：AI产品，技术面" />
          <Text className={styles.label}>一个可核验的履历 / 作品链接 *</Text>
          <Textarea className={styles.textarea} value={proofUrls} onInput={(event) => setProofUrls(event.detail.value)} placeholder="公开主页、作品集或可核验材料的 https 链接，至少一个" maxlength={1000} cursorSpacing={24} disableDefaultPadding showConfirmBar={false} />
          <View className={styles.primaryButton} onClick={submitApplication}><Text>{loading ? '提交中…' : '提交平台审核'}</Text></View>
        </View>
      )}

      {expert && (
        <>
          <View className={styles.card}>
            <Text className={styles.sectionTitle}>维护真实档期</Text>
            <Text className={styles.hint}>只填写你确认能提供服务的北京时间，每行一个。已确认预约的时段会自动移除。</Text>
            <Textarea className={styles.textarea} value={slotText} onInput={(event) => setSlotText(event.detail.value)} maxlength={1000} autoHeight />
            <View className={styles.primaryButton} onClick={saveAvailability}><Text>{loading ? '保存中…' : '保存可约时段'}</Text></View>
          </View>

          <Text className={styles.listTitle}>预约与交付</Text>
          {bookings.length === 0 && <View className={styles.card}><Text className={styles.hint}>还没有用户提交预约意向。</Text></View>}
          {bookings.map((booking) => (
            <View key={booking.id} className={styles.card}>
              <Text className={styles.bookingTitle}>{booking.topic}</Text>
              <Text className={styles.bookingMeta}>{booking.slot} · {booking.status}</Text>
              <Text className={styles.bookingDesc}>{booking.desc}</Text>
              {booking.expert_briefing && (
                <View className={styles.statusCard}>
                  <Text className={styles.statusTitle}>用户已授权的会前摘要</Text>
                  <Text className={styles.bookingMeta}>{booking.expert_briefing.job.label}</Text>
                  {booking.expert_briefing.job.fit_decision && <Text className={styles.bookingDesc}>投递判断：{booking.expert_briefing.job.fit_decision}</Text>}
                  {booking.expert_briefing.evidence.map((item, index) => (
                    <Text key={`evidence-${index}`} className={styles.bookingDesc}>证据：{item.title}｜{item.result}{item.metrics ? `｜${item.metrics}` : ''}</Text>
                  ))}
                  {booking.expert_briefing.latest_practice && (
                    <Text className={styles.bookingDesc}>最近练习：{booking.expert_briefing.latest_practice.position}｜{booking.expert_briefing.latest_practice.overall_score ?? '暂无总分'}</Text>
                  )}
                  {booking.expert_briefing.key_questions.map((item, index) => <Text key={`question-${index}`} className={styles.bookingDesc}>关键问题 {index + 1}：{item}</Text>)}
                  <Text className={styles.hint}>{booking.expert_briefing.privacy_note}</Text>
                </View>
              )}
              {booking.status_code === 'intent_submitted' && (
                <View className={styles.actionRow}>
                  <View className={styles.secondaryButton} onClick={() => decide(booking, 'rejected')}><Text>无法接单</Text></View>
                  <View className={styles.primarySmall} onClick={() => decide(booking, 'confirmed')}><Text>确认接单</Text></View>
                </View>
              )}
              {booking.status_code === 'confirmed' && deliveryBookingId !== booking.id && (
                <View className={styles.primaryButton} onClick={() => setDeliveryBookingId(booking.id)}><Text>填写交付摘要</Text></View>
              )}
              {booking.status_code === 'confirmed' && deliveryBookingId === booking.id && (
                <>
                  <Textarea className={styles.textarea} value={deliverySummary} onInput={(event) => setDeliverySummary(event.detail.value)} placeholder="如实记录本次服务解决的问题、建议和下一步（至少10字）" maxlength={2000} autoHeight />
                  <Textarea className={styles.textarea} value={deliveryNextActions} onInput={(event) => setDeliveryNextActions(event.detail.value)} placeholder="用户下一步行动，每行一条，至少1条" maxlength={1000} autoHeight />
                  <View className={styles.primaryButton} onClick={() => complete(booking)}><Text>确认完成服务</Text></View>
                </>
              )}
              {booking.delivery_summary && <Text className={styles.delivery}>交付摘要：{booking.delivery_summary}</Text>}
              {(booking.next_actions || []).map((item, index) => <Text key={`next-${index}`} className={styles.delivery}>下一步 {index + 1}：{item}</Text>)}
            </View>
          ))}
        </>
      )}
    </View>
  )
}

export default ExpertCenterPage
