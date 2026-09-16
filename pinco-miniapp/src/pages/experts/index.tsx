import React, { useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh } from '@tarojs/taro'
import styles from './index.module.scss'
import { ExpertProfile } from '@/types/pinco'
import { fetchExperts } from '@/services/pinco'
import { usePincoStore } from '@/store/usePincoStore'

const ExpertsPage: React.FC = () => {
  const [experts, setExperts] = useState<ExpertProfile[]>([])
  const [selectedExpert, setSelectedExpert] = useState<ExpertProfile | null>(null)
  const [showBookingForm, setShowBookingForm] = useState(false)
  const [slot, setSlot] = useState('')
  const [topic, setTopic] = useState('')
  const [consultationType, setConsultationType] = useState<'chat' | 'phone'>('chat')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [selectedJobId, setSelectedJobId] = useState('')
  const [shareContextWithExpert, setShareContextWithExpert] = useState(false)
  const createBookingOrder = usePincoStore((state) => state.createBookingOrder)
  const jobProgress = usePincoStore((state) => state.jobProgress)

  const loadExperts = async () => {
    try {
      const result = await fetchExperts()
      setExperts(result.experts || [])
      setLoadError('')
    } catch (error) {
      console.error('[Experts] load failed', error)
      setExperts([])
      setLoadError('专家列表暂时加载失败，下拉可以重试。')
    }
  }

  useDidShow(loadExperts)
  usePullDownRefresh(() => loadExperts().finally(() => Taro.stopPullDownRefresh()))

  const close = () => {
    setSelectedExpert(null)
    setShowBookingForm(false)
    setSlot('')
    setTopic('')
    setConsultationType('chat')
    setSelectedJobId('')
    setShareContextWithExpert(false)
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
    } catch (error) {
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
        <Text className={styles.desc}>首批合作专家开放免费公测预约。可选 Pinco 内图文咨询或电话咨询，求职者默认匿名，暂不开放付费。</Text>
        <View className={styles.applyButton} onClick={() => Taro.navigateTo({ url: '/pages/expert-center/index' })}>
          <Text>申请成为专家 / 专家工作台</Text>
        </View>
      </View>

      {experts.length === 0 && (
        <View className={styles.emptyPanel}>
          <Text className={styles.emptyTitle}>{loadError || '首批专家正在审核中'}</Text>
          <Text className={styles.emptyDesc}>平台不会用虚构履历填充列表。审核通过、档期可约后才会在这里出现。</Text>
          <View className={styles.emptyAction} onClick={() => Taro.navigateTo({ url: '/pages/expert-center/index' })}>
            <Text>提交专家申请</Text>
          </View>
        </View>
      )}

      {experts.map((expert) => (
        <View key={expert.id} className={styles.expertCard} onClick={() => setSelectedExpert(expert)}>
          <View className={styles.topRow}>
            <View>
              <Text className={styles.name}>{expert.name}</Text>
              <Text className={styles.titleText}>{expert.title}</Text>
            </View>
            <Text className={styles.priceTag}>免费公测预约</Text>
          </View>
          <Text className={styles.verifiedLabel}>✓ {expert.verificationStatus}</Text>
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
              onClick={(event) => { event.stopPropagation(); setSelectedExpert(expert); setShowBookingForm(true) }}
            >
              <Text>{expert.slots.length ? '去预约' : '暂无档期'}</Text>
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
                ? setShowBookingForm(true)
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
              <Text className={styles.payLabel}>专家发布的可约时段（北京时间）</Text>
              <View className={styles.slotGrid}>
                {selectedExpert.slots.map((item) => (
                  <View
                    key={item}
                    className={`${styles.slotChip} ${slot === item ? styles.slotChipActive : ''}`}
                    onClick={() => setSlot(item)}
                  ><Text>{item}</Text></View>
                ))}
              </View>
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
