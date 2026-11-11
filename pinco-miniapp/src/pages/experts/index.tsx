import React, { useState } from 'react'
import { Picker, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh } from '@tarojs/taro'
import styles from './index.module.scss'
import { ExpertProfile } from '@/types/pinco'
import { fetchExperts } from '@/services/pinco'
import { usePincoStore } from '@/store/usePincoStore'
import { usePageAnalytics } from '@/hooks/usePageAnalytics'

const EXPERTS_CACHE_KEY = 'pinco.experts.catalogue.v1'

// A connectivity fallback, not a list of people claiming to be available.
// These service directions are deliberately non-bookable and carry no slots.
const OFFLINE_EXPERT_GUIDES: ExpertProfile[] = [
  {
    id: 'offline-direction-ai-product', name: 'AI 产品求职咨询方向', title: '岗位定位与产品面试',
    intro: '围绕目标岗位拆解、真实项目证据梳理、产品案例表达与 Offer 决策提供咨询。',
    tags: ['岗位定位', '项目证据', '产品面试', 'Offer选择'], price: 0, nextSlot: '', rating: 0, servedCount: 0,
    slots: [], verificationStatus: '服务方向介绍 · 暂不可预约', serviceName: 'AI 产品求职诊断',
    deliverables: ['问题诊断', '下一步行动清单'], durationMinutes: 30,
  },
  {
    id: 'offline-direction-ai-ops', name: 'AI 运营求职咨询方向', title: '增长、内容与数据复盘',
    intro: '围绕 AI 产品运营、增长与内容方向，梳理可核验的数据证据并准备面试复盘。',
    tags: ['AI运营', '增长', '内容策略', '数据复盘'], price: 0, nextSlot: '', rating: 0, servedCount: 0,
    slots: [], verificationStatus: '服务方向介绍 · 暂不可预约', serviceName: 'AI 运营求职诊断',
    deliverables: ['经历证据诊断', '表达改进建议'], durationMinutes: 30,
  },
  {
    id: 'offline-direction-agent', name: 'AI Agent 求职咨询方向', title: 'Agent 产品与方案表达',
    intro: '围绕 Agent 规划、记忆、工具调用与评测体系，梳理产品方案和作品集表达。',
    tags: ['AI Agent', '方案设计', '作品集', '技术理解'], price: 0, nextSlot: '', rating: 0, servedCount: 0,
    slots: [], verificationStatus: '服务方向介绍 · 暂不可预约', serviceName: 'AI Agent 方案诊断',
    deliverables: ['方案问题诊断', '作品集改进清单'], durationMinutes: 30,
  },
]

const getCachedExperts = (): ExpertProfile[] => {
  try {
    const cached = Taro.getStorageSync(EXPERTS_CACHE_KEY)
    return Array.isArray(cached) ? cached.filter((item) => item && typeof item.id === 'string') : []
  } catch {
    return []
  }
}

const asNonBookableCachedExperts = (experts: ExpertProfile[]) => experts.map((expert) => ({
  ...expert,
  slots: [],
  verificationStatus: '缓存资料 · 档期需联网确认',
}))

const ExpertsPage: React.FC = () => {
  usePageAnalytics('experts')
  const [initialDirectory] = useState(() => {
    const cached = getCachedExperts()
    return cached.length > 0
      ? {
          experts: asNonBookableCachedExperts(cached),
          usingOfflineGuides: false,
          notice: '正在刷新专家资料；为避免时段过期，缓存档期不会用于预约。',
        }
      : {
          experts: OFFLINE_EXPERT_GUIDES,
          usingOfflineGuides: true,
          notice: '正在连接专家服务；当前仅展示不可预约的服务方向介绍。',
        }
  })
  const [experts, setExperts] = useState<ExpertProfile[]>(initialDirectory.experts)
  const [selectedExpert, setSelectedExpert] = useState<ExpertProfile | null>(null)
  const [showBookingForm, setShowBookingForm] = useState(false)
  const [slot, setSlot] = useState('')
  const [topic, setTopic] = useState('')
  const [consultationType, setConsultationType] = useState<'chat' | 'phone'>('chat')
  const [loading, setLoading] = useState(false)
  const [expertsLoading, setExpertsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [directoryNotice, setDirectoryNotice] = useState(initialDirectory.notice)
  const [usingOfflineGuides, setUsingOfflineGuides] = useState(initialDirectory.usingOfflineGuides)
  const [selectedJobId, setSelectedJobId] = useState('')
  const [shareContextWithExpert, setShareContextWithExpert] = useState(false)
  const createBookingOrder = usePincoStore((state) => state.createBookingOrder)
  const bootstrap = usePincoStore((state) => state.bootstrap)
  const jobProgress = usePincoStore((state) => state.jobProgress)

  const loadExperts = async () => {
    setExpertsLoading(true)
    setLoadError('')
    setDirectoryNotice(experts.length > 0
      ? '正在刷新专家资料；缓存档期不会用于预约。'
      : '正在连接专家服务，请稍候。')
    // A stalled mini-program network request must not leave the core booking
    // screen in an endless spinner. Keep the request alive so a late success
    // can still populate the list, while exposing a retry state to the user.
    const loadingTimeout = setTimeout(() => {
      setExpertsLoading(false)
      setLoadError('连接专家服务超时，请检查网络后重试。')
      if (initialDirectory.usingOfflineGuides) {
        const cached = getCachedExperts()
        if (cached.length > 0) {
          setExperts(asNonBookableCachedExperts(cached))
          setUsingOfflineGuides(false)
          setDirectoryNotice('当前显示最近成功加载的专家资料。网络恢复后请刷新；为避免过期，缓存档期已隐藏。')
        } else {
          setExperts(OFFLINE_EXPERT_GUIDES)
          setUsingOfflineGuides(true)
          setDirectoryNotice('暂时连接不上预约服务，以下仅为服务方向介绍，不代表当前有可预约专家。')
        }
      } else {
        setDirectoryNotice('当前显示缓存的专家资料；档期已隐藏，请联网刷新后再预约。')
      }
    }, 12000)
    try {
      const result = await fetchExperts()
      const currentExperts = Array.isArray(result?.experts) ? result.experts : []
      if (currentExperts.length > 0) {
        setExperts(currentExperts)
        setUsingOfflineGuides(false)
        setDirectoryNotice('')
        try {
          Taro.setStorageSync(EXPERTS_CACHE_KEY, currentExperts)
        } catch (cacheError) {
          console.warn('[Experts] catalogue cache unavailable', cacheError)
        }
        setLoadError('')
      } else {
        setExperts(OFFLINE_EXPERT_GUIDES)
        setUsingOfflineGuides(true)
        setLoadError('暂时没有可展示的已审核专家。')
        setDirectoryNotice('以下仅为服务方向介绍，不代表当前有可预约专家；档期开放后会在这里显示。')
      }
    } catch (error) {
      console.error('[Experts] load failed', error)
      setLoadError('专家列表暂时加载失败，请下拉或点击重试。')
      const cached = getCachedExperts()
      if (cached.length > 0) {
        setExperts(asNonBookableCachedExperts(cached))
        setUsingOfflineGuides(false)
        setDirectoryNotice('当前显示最近成功加载的专家资料。网络恢复后请刷新；为避免过期，缓存档期已隐藏。')
      } else {
        setExperts(OFFLINE_EXPERT_GUIDES)
        setUsingOfflineGuides(true)
        setDirectoryNotice('暂时连接不上预约服务，以下仅为服务方向介绍，不代表当前有可预约专家。')
      }
    } finally {
      clearTimeout(loadingTimeout)
      setExpertsLoading(false)
    }
  }

  useDidShow(loadExperts)
  usePullDownRefresh(() => loadExperts().finally(() => Taro.stopPullDownRefresh()))

  const openExpertCenter = async () => {
    if (!usePincoStore.getState().userProfile?.user_id) await bootstrap()
    if (!usePincoStore.getState().userProfile?.user_id) {
      Taro.showToast({ title: '身份初始化失败，请检查网络后重试', icon: 'none' })
      return
    }
    try {
      await Taro.navigateTo({ url: '/pages/expert-center/index' })
    } catch (error) {
      console.error('[Experts] open expert center failed', error)
      Taro.showToast({ title: '专家工作台未能打开，请重试', icon: 'none' })
    }
  }

  const close = () => {
    setSelectedExpert(null)
    setShowBookingForm(false)
    setSlot('')
    setTopic('')
    setConsultationType('chat')
    setSelectedJobId('')
    setShareContextWithExpert(false)
  }

  const openBooking = (expert: ExpertProfile) => {
    setSelectedExpert(expert)
    setSlot(expert.slots[0] || '')
    setShowBookingForm(true)
  }

  const submitBooking = async () => {
    if (!selectedExpert || !slot || !topic.trim()) {
      Taro.showToast({ title: '请选择时段并填写想解决的问题', icon: 'none' })
      return
    }
    if (loading) return
    setLoading(true)
    try {
      await createBookingOrder({
        expert_id: selectedExpert.id,
        expert_name: selectedExpert.name,
        topic: selectedExpert.serviceName,
        slot,
        desc: topic.trim(),
        consultation_type: consultationType,
        contact_wechat: '',
        share_contact_with_expert: false,
        job_id: selectedJobId || undefined,
        share_context_with_expert: Boolean(selectedJobId && shareContextWithExpert),
      })
      close()
      Taro.showModal({
        title: '免费预约已送达',
        content: consultationType === 'chat'
          ? '专家接受后，你们可以直接在 Pinco 咨询消息里发送文字和图片。预约默认匿名，本次不会扣款。'
          : '专家接受后，会在 Pinco 站内信中发送电话或会议链接；接受前不会展示双方联系方式。本次不会扣款。',
        showCancel: false,
      })
    } catch (error: any) {
      console.error('[Experts] booking failed', error)
      Taro.showToast({ title: error?.message || '提交失败或时段已变化，请刷新重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.title}>专家市场</Text>
        <Text className={styles.desc}>可选 Pinco 内图文咨询或电话咨询，求职者默认匿名。目录展示当前已审核专家与实时档期；只有显示可约时段时才能提交预约。专家未绑定账号时由平台运营人工协调，暂不开放付费。</Text>
        <View className={styles.applyButton} onClick={openExpertCenter}>
          <Text>进入专家工作台 / 申请专家</Text>
        </View>
        <Text className={styles.desc}>已绑定专家从这个入口确认、改期或拒绝预约。</Text>
      </View>

      {directoryNotice && (
        <View className={styles.directoryNotice}>
          <Text>{directoryNotice}</Text>
          <View className={styles.noticeRetry} onClick={loadExperts}><Text>重试</Text></View>
        </View>
      )}

      {usingOfflineGuides && <Text className={styles.guideHeading}>可提供的咨询方向</Text>}

      {experts.length === 0 && (
        <View className={styles.emptyPanel}>
          <Text className={styles.emptyTitle}>{expertsLoading ? '正在加载专家信息…' : loadError || '首批专家正在审核中'}</Text>
          <Text className={styles.emptyDesc}>
            {expertsLoading
              ? '正在读取已审核专家和可约时段，请稍候。'
              : loadError
                ? '请检查网络连接后重试；如果仍无法加载，可以稍后再来。'
                : '平台不会用虚构履历填充列表。审核通过、档期可约后才会在这里出现。'}
          </Text>
          {!expertsLoading && (loadError
            ? <View className={styles.emptyAction} onClick={loadExperts}><Text>重新加载</Text></View>
            : <View className={styles.emptyAction} onClick={openExpertCenter}><Text>提交专家申请</Text></View>)}
        </View>
      )}

      {experts.map((expert) => (
        <View key={expert.id} className={styles.expertCard} onClick={() => setSelectedExpert(expert)}>
          <View className={styles.topRow}>
            <View>
              <Text className={styles.name}>{expert.name}</Text>
              <Text className={styles.titleText}>{expert.title}</Text>
            </View>
            <Text className={styles.priceTag}>{usingOfflineGuides ? '服务方向介绍' : '免费公测预约'}</Text>
          </View>
          <Text className={styles.verifiedLabel}>
            {expert.verificationStatus.includes('服务方向介绍') ? 'ℹ' : expert.verificationStatus.includes('缓存资料') ? '◷' : '✓'} {expert.verificationStatus}
          </Text>
          <Text className={styles.intro}>{expert.intro}</Text>
          <View className={styles.tagsRow}>
            {expert.tags.map((tag) => <Text key={tag} className={styles.tag}>{tag}</Text>)}
          </View>
          <View className={styles.bottomRow}>
            <Text className={styles.metrics}>
              {expert.servedCount > 0 ? `已完成 ${expert.servedCount} 次` : '暂无完成服务'}
              {' · '}
              {expert.rating > 0 ? `${expert.rating} 分真实评价` : '暂无评价'}
            </Text>
            <View
              className={styles.bookButton}
              onClick={(event) => {
                event.stopPropagation()
                if (expert.slots.length > 0) openBooking(expert)
                else Taro.showToast({ title: '当前没有可预约时段，请联网刷新后查看', icon: 'none' })
              }}
            >
              <Text>{expert.slots.length ? '去预约' : usingOfflineGuides ? '暂不可预约' : '暂无档期'}</Text>
            </View>
          </View>
        </View>
      ))}

      {selectedExpert && !showBookingForm && (
        <View className={styles.detailOverlay} onClick={close}>
          <ScrollView className={styles.detailPanel} scrollY onClick={(event) => event.stopPropagation()}>
            <View className={styles.detailHeader}>
              <Text className={styles.detailName}>{selectedExpert.name}</Text>
              <View className={styles.detailClose} onClick={close}><Text>✕</Text></View>
            </View>
            <Text className={styles.detailTitle}>{selectedExpert.title}</Text>
            <Text className={styles.detailPrice}>1.0 免费公测预约</Text>
            <View className={styles.detailSection}>
              <Text className={styles.detailSectionTitle}>专家介绍</Text>
              <Text className={styles.detailIntro}>{selectedExpert.intro}</Text>
            </View>
            <View className={styles.detailSection}>
              <Text className={styles.detailSectionTitle}>擅长领域</Text>
              <View className={styles.detailTags}>
                {selectedExpert.tags.map((tag) => <Text key={tag} className={styles.detailTag}>{tag}</Text>)}
              </View>
            </View>
            <View className={styles.detailSection}>
              <Text className={styles.detailSectionTitle}>固定服务包</Text>
              <Text className={styles.detailIntro}>{selectedExpert.serviceName} · {selectedExpert.durationMinutes}分钟</Text>
              <Text className={styles.detailIntro}>交付：{selectedExpert.deliverables.join('、')}</Text>
            </View>
            <View className={styles.detailSection}>
              <Text className={styles.detailSectionTitle}>真实服务记录</Text>
              <Text className={styles.detailIntro}>
                {selectedExpert.reviews?.length
                  ? selectedExpert.reviews.map((review) => `${review.score}分：${review.comment}`).join('\n')
                  : '还没有已完成服务的公开评价。'}
              </Text>
            </View>
            <View
              className={styles.detailBookButton}
              onClick={() => selectedExpert.slots.length
                ? openBooking(selectedExpert)
                : Taro.showToast({ title: '专家暂未发布档期', icon: 'none' })}
            >
              <Text className={styles.detailBookText}>{selectedExpert.slots.length ? '选择可约档期' : '暂无可约档期'}</Text>
            </View>
          </ScrollView>
        </View>
      )}

      {selectedExpert && showBookingForm && (
        <View className={styles.detailOverlay} onClick={close}>
          <ScrollView className={styles.detailPanel} scrollY onClick={(event) => event.stopPropagation()}>
            <View className={styles.detailHeader}>
              <Text className={styles.detailName}>预约 {selectedExpert.name}</Text>
              <View className={styles.detailClose} onClick={close}><Text>✕</Text></View>
            </View>
            <View className={styles.paySection}>
              <Text className={styles.payLabel}>选择咨询方式</Text>
              <View className={styles.consultationGrid}>
                <View
                  className={`${styles.consultationCard} ${consultationType === 'chat' ? styles.consultationCardActive : ''}`}
                  onClick={() => setConsultationType('chat')}
                >
                  <Text className={styles.consultationTitle}>{consultationType === 'chat' ? '✓ ' : ''}图文咨询</Text>
                  <Text className={styles.consultationDesc}>直接在 Pinco 内发送文字和图片，默认匿名</Text>
                </View>
                <View
                  className={`${styles.consultationCard} ${consultationType === 'phone' ? styles.consultationCardActive : ''}`}
                  onClick={() => setConsultationType('phone')}
                >
                  <Text className={styles.consultationTitle}>{consultationType === 'phone' ? '✓ ' : ''}电话咨询</Text>
                  <Text className={styles.consultationDesc}>专家接受后，在站内信发送电话或会议链接</Text>
                </View>
              </View>
            </View>
            <View className={styles.paySection}>
              <Text className={styles.payLabel}>希望沟通的时间（北京时间，待专家确认）</Text>
              {selectedExpert.slots.length > 0 ? (
                <Picker
                  mode="selector"
                  range={selectedExpert.slots}
                  value={Math.max(0, selectedExpert.slots.indexOf(slot))}
                  onChange={(event) => setSlot(selectedExpert.slots[Number(event.detail.value)] || '')}
                >
                  <View className={styles.slotSelect}>
                    <Text className={styles.slotSelectLabel}>预约时段</Text>
                    <Text className={styles.slotSelectValue}>{slot || '请选择专家可约时段'}　⌄</Text>
                  </View>
                </Picker>
              ) : (
                <Text className={styles.emptySlots}>专家还没有发布可约时段，暂时不能提交预约。</Text>
              )}
              <Text className={styles.detailIntro}>这里选择的是预约意向，不代表专家已确认。提交后会进入待确认流程；未绑定专家账号时由平台运营人工联系协调。</Text>
            </View>
            <View className={styles.paySection}>
              <Text className={styles.payLabel}>这次最想解决的问题</Text>
              <Textarea
                className={styles.payInput}
                value={topic}
                onInput={(event) => setTopic(event.detail.value)}
                placeholder="把背景、卡点和希望拿到的结果说清楚"
                maxlength={200}
                autoHeight
                showConfirmBar={false}
              />
            </View>
            <View className={styles.paySection}>
              <Text className={styles.payLabel}>隐私说明</Text>
              <Text className={styles.detailIntro}>默认以匿名身份预约，专家看不到你的微信昵称、OpenID 或联系方式。电话咨询由专家接受后主动发送联系方式。</Text>
            </View>
            {jobProgress.length > 0 && (
              <View className={styles.paySection}>
                <Text className={styles.payLabel}>关联岗位（可选）</Text>
                <View className={styles.slotGrid}>
                  <View className={`${styles.slotChip} ${!selectedJobId ? styles.slotChipActive : ''}`} onClick={() => setSelectedJobId('')}><Text>不关联</Text></View>
                  {jobProgress.map((job) => (
                    <View key={job.id} className={`${styles.slotChip} ${selectedJobId === job.id ? styles.slotChipActive : ''}`} onClick={() => setSelectedJobId(job.id)}>
                      <Text>{job.company} · {job.position}</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
            {selectedJobId && (
              <View className={styles.paySection}>
                <Text className={styles.payLabel}>会前摘要授权（可选）</Text>
                <Text className={styles.detailIntro}>开启后，仅向这位专家分享该岗位 JD 摘要、你已确认的职业证据、关联练习摘要和本次问题；不会分享会话全文或账号数据。</Text>
                <View
                  className={`${styles.slotChip} ${shareContextWithExpert ? styles.slotChipActive : ''}`}
                  onClick={() => setShareContextWithExpert((value) => !value)}
                >
                  <Text>{shareContextWithExpert ? '✓ 已授权本次分享' : '不分享会前摘要'}</Text>
                </View>
              </View>
            )}
            <Text className={styles.noChargeNote}>本次是免费公测预约，不会触发支付。咨询消息和处理结果可在“我的预约”查看。</Text>
            <View className={styles.detailBookButton} onClick={submitBooking}>
              <Text className={styles.detailBookText}>{loading ? '提交中…' : '提交预约意向（不扣款）'}</Text>
            </View>
          </ScrollView>
        </View>
      )}
    </View>
  )
}

export default ExpertsPage
