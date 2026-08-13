import React, { useEffect, useState } from 'react'
import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import styles from './index.module.scss'
import { usePincoStore } from '@/store/usePincoStore'
import {
  fetchMembershipPlans,
  fetchMembershipStatus,
  fetchPaymentOrder,
  fetchPaymentOrders,
  closePaymentOrder,
  registerMembershipInterest,
  subscribeMembership,
} from '@/services/pinco'
import { MembershipPlan, PaymentOrderStatus, UserMembership } from '@/types/pinco'

const MembershipPage: React.FC = () => {
  const userProfile = usePincoStore((s) => s.userProfile)
  const [plans, setPlans] = useState<MembershipPlan[]>([])
  const [membership, setMembership] = useState<UserMembership | null>(null)
  const [selectedPlan, setSelectedPlan] = useState<string>('pro')
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly')
  const [loading, setLoading] = useState(false)
  const [pendingOrder, setPendingOrder] = useState<PaymentOrderStatus | null>(null)

  useEffect(() => {
    loadData()
  }, [userProfile?.user_id])

  const loadData = async () => {
    try {
      if (!userProfile?.user_id) return
      const [plansResp, statusResp, paymentResp] = await Promise.all([
        fetchMembershipPlans(userProfile.user_id),
        fetchMembershipStatus(userProfile.user_id),
        fetchPaymentOrders(userProfile.user_id, 'membership').catch((error) => {
          console.warn('[Membership] pending payment list unavailable', error)
          return { orders: [] }
        }),
      ])
      setPlans(plansResp.plans)
      setMembership(statusResp)
      setPendingOrder(paymentResp.orders.find((item) => ['creating', 'unpaid'].includes(item.status)) || null)
    } catch (e) {
      console.error('[Membership] load failed', e)
    }
  }

  const handleSubscribe = async () => {
    if (!userProfile?.user_id) {
      Taro.showToast({ title: '身份正在准备，请稍后重试', icon: 'none' })
      return
    }
    if (selectedPlan === 'free') {
      Taro.showToast({ title: '你已经在使用内测版', icon: 'none' })
      return
    }
    if (loading) return
    const selected = plans.find((plan) => plan.id === selectedPlan)
    if (!selected) {
      Taro.showToast({ title: '方案信息还没加载好', icon: 'none' })
      return
    }
    if (pendingOrder) {
      setLoading(true)
      try {
        const status = await fetchPaymentOrder(pendingOrder.order_id, userProfile.user_id, true)
        if (status.status === 'paid' && status.fulfilled) {
          await loadData()
          Taro.showModal({ title: '支付已确认', content: '原订单已经由微信支付服务端确认，会员权益已生效。', showCancel: false })
          return
        }
        const decision = await Taro.showModal({
          title: '已有待确认订单',
          content: `${status.message}。为避免重复支付，请先关闭原订单，再重新发起。`,
          confirmText: '关闭原订单',
        })
        if (decision.confirm) {
          const closed = await closePaymentOrder(pendingOrder.order_id, userProfile.user_id)
          if (closed.status === 'paid') {
            await loadData()
            Taro.showModal({ title: '支付已确认', content: '关单前微信支付服务端已确认付款，会员权益已生效。', showCancel: false })
          } else {
            setPendingOrder(null)
            Taro.showToast({ title: '原订单已关闭，可重新发起', icon: 'none' })
          }
        }
      } catch (error: any) {
        Taro.showModal({ title: '订单状态待核对', content: error?.message || '请不要重复支付，稍后再试。', showCancel: false })
      } finally {
        setLoading(false)
      }
      return
    }
    setLoading(true)
    try {
      if (!selected.purchasable) {
        const resp = await registerMembershipInterest({
          user_id: userProfile.user_id,
          plan_id: selectedPlan,
          billing_cycle: billingCycle,
        })
        Taro.showModal({ title: '已登记开通意向', content: resp.message, showCancel: false })
        return
      }

      const requestId = `membership-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      const order = await subscribeMembership({
        user_id: userProfile.user_id,
        plan_id: selectedPlan,
        billing_cycle: billingCycle,
        payment_method: 'wechat',
        request_id: requestId,
      })
      try {
        await Taro.requestPayment(order.payment_params)
      } catch (paymentError: any) {
        const message = String(paymentError?.errMsg || paymentError?.message || '')
        if (message.includes('cancel')) {
          try {
            const closed = await closePaymentOrder(order.order_id, userProfile.user_id)
            if (closed.status === 'paid' && closed.fulfilled) {
              await loadData()
              Taro.showModal({ title: '支付已确认', content: '虽然收银台返回了取消，但微信支付服务端已确认付款，会员权益已经生效。', showCancel: false })
            } else {
              Taro.showToast({ title: '已取消支付，订单已关闭', icon: 'none' })
            }
          } catch (closeError) {
            console.error('[Membership] close cancelled order failed', closeError)
            Taro.showModal({
              title: '订单状态待核对',
              content: '取消后服务端暂未能关闭订单。请不要重复支付，先查看微信支付记录并稍后刷新会员状态。',
              showCancel: false,
            })
          }
          return
        }
        throw paymentError
      }

      let confirmed
      try {
        confirmed = await fetchPaymentOrder(order.order_id, userProfile.user_id, true)
      } catch (queryError) {
        console.error('[Membership] payment query failed', queryError)
        Taro.showModal({
          title: '支付结果确认中',
          content: '微信收银台已返回，但服务端暂未确认结果。请不要重复支付，稍后重新进入本页查看会员状态。',
          showCancel: false,
        })
        return
      }
      if (confirmed.status === 'paid' && confirmed.fulfilled) {
        await loadData()
        Taro.showModal({ title: '开通成功', content: '微信支付服务端已确认，会员权益已经生效。', showCancel: false })
      } else {
        Taro.showModal({
          title: '支付结果确认中',
          content: `${confirmed.message}。请不要重复支付，稍后刷新会员状态。`,
          showCancel: false,
        })
      }
    } catch (e: any) {
      console.error('[Membership] subscribe failed', e)
      Taro.showModal({
        title: selected.purchasable ? '支付未完成' : '登记失败',
        content: e?.message || (selected.purchasable ? '支付没有完成，请核对微信支付记录后再重试。' : '开通意向暂时未登记成功，请稍后再试；当前不会扣款。'),
        showCancel: false,
      })
    } finally {
      setLoading(false)
    }
  }

  const currentPlan = plans.find((p) => p.id === selectedPlan)
  const paymentAvailable = Boolean(currentPlan?.purchasable)
  const price = billingCycle === 'yearly' && currentPlan?.price_yearly
    ? (currentPlan.price_yearly / 12).toFixed(1)
    : currentPlan?.price.toFixed(1)
  const usageWidth = (used: number, limit: number) => limit < 0 ? 0 : Math.min(100, (used / Math.max(limit, 1)) * 100)

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.title}>Pinco 会员</Text>
        <Text className={styles.subtitle}>{plans.some((plan) => plan.purchasable) ? '支付只以微信服务端确认结果开通，客户端返回不代表扣款成功' : '内测版免费使用；付费方案是待验证草案，登记意向不会扣款'}</Text>
      </View>

      {membership && membership.plan_id !== 'free' && (
        <View className={styles.currentPlan}>
          <Text className={styles.currentPlanLabel}>当前方案</Text>
          <Text className={styles.currentPlanName}>{membership.plan_name}</Text>
          {membership.expire_at && <Text className={styles.currentPlanExpire}>有效期至 {membership.expire_at}</Text>}
        </View>
      )}

      {pendingOrder && (
        <View className={styles.currentPlan} onClick={handleSubscribe}>
          <Text className={styles.currentPlanLabel}>有一笔待确认订单</Text>
          <Text className={styles.currentPlanName}>点击核对服务端状态</Text>
          <Text className={styles.currentPlanExpire}>不要重复支付；可在核对后安全关闭原订单</Text>
        </View>
      )}

      <View className={styles.cycleToggle}>
        <View className={`${styles.cycleOption} ${billingCycle === 'monthly' ? styles.cycleActive : ''}`} onClick={() => setBillingCycle('monthly')}>
          <Text>月付</Text>
        </View>
        <View className={`${styles.cycleOption} ${billingCycle === 'yearly' ? styles.cycleActive : ''}`} onClick={() => setBillingCycle('yearly')}>
          <Text>年付</Text>
          {billingCycle === 'yearly' && <Text className={styles.saveTag}>价格假设约省17%</Text>}
        </View>
      </View>

      <ScrollView scrollX className={styles.planCards}>
        {plans.map((plan) => (
          <View
            key={plan.id}
            className={`${styles.planCard} ${selectedPlan === plan.id ? styles.planCardSelected : ''} ${plan.id === 'premium' ? styles.planCardPremium : ''}`}
            onClick={() => setSelectedPlan(plan.id)}
          >
            {plan.id === 'premium' && <View className={styles.recommendBadge}><Text>权益草案</Text></View>}
            <Text className={styles.planName}>{plan.name}</Text>
            <Text className={styles.planYearly}>{plan.billing_note}</Text>
            <View className={styles.planPrice}>
              <Text className={styles.planPriceAmount}>¥{billingCycle === 'yearly' && plan.price_yearly ? (plan.price_yearly / 12).toFixed(0) : plan.price.toFixed(0)}</Text>
              <Text className={styles.planPriceUnit}>/月</Text>
            </View>
            {billingCycle === 'yearly' && plan.price_yearly && (
              <Text className={styles.planYearly}>年付 ¥{plan.price_yearly}</Text>
            )}
            <View className={styles.featureList}>
              {plan.features.map((f, i) => (
                <Text key={i} className={styles.featureItem}>✓ {f}</Text>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>

      <View className={styles.usageSection}>
        <Text className={styles.usageTitle}>用量统计</Text>
        {membership?.usage_reset_at && <Text className={styles.currentPlanExpire}>本期额度重置时间：{membership.usage_reset_at.replace('T', ' ').replace('Z', '').slice(0, 16)}</Text>}
        {membership && (
          <View className={styles.usageList}>
            <View className={styles.usageItem}>
              <Text className={styles.usageLabel}>AI 对话</Text>
              <View className={styles.usageBar}>
                <View className={styles.usageBarFill} style={{ width: `${usageWidth(membership.ai_chat_used, membership.ai_chat_limit)}%` }} />
              </View>
              <Text className={styles.usageCount}>{membership.ai_chat_used}/{membership.ai_chat_limit === -1 ? '∞' : membership.ai_chat_limit}</Text>
            </View>
            <View className={styles.usageItem}>
              <Text className={styles.usageLabel}>简历诊断</Text>
              <View className={styles.usageBar}>
                <View className={styles.usageBarFill} style={{ width: `${usageWidth(membership.resume_used, membership.resume_limit)}%` }} />
              </View>
              <Text className={styles.usageCount}>{membership.resume_used}/{membership.resume_limit === -1 ? '∞' : membership.resume_limit}</Text>
            </View>
            <View className={styles.usageItem}>
              <Text className={styles.usageLabel}>模拟面试</Text>
              <View className={styles.usageBar}>
                <View className={styles.usageBarFill} style={{ width: `${usageWidth(membership.interview_used, membership.interview_limit)}%` }} />
              </View>
              <Text className={styles.usageCount}>{membership.interview_used}/{membership.interview_limit === -1 ? '∞' : membership.interview_limit}</Text>
            </View>
          </View>
        )}
      </View>

      <View className={styles.footer}>
        <View className={styles.priceSummary}>
          <Text className={styles.priceSummaryLabel}>{paymentAvailable ? '本次微信支付金额' : '待验证价格（当前不支付）'}</Text>
          <Text className={styles.priceSummaryAmount}>¥{price}/月</Text>
        </View>
        <View className={styles.subscribeButton} onClick={handleSubscribe}>
          <Text className={styles.subscribeButtonText}>{loading ? (paymentAvailable ? '正在核对安全订单…' : '登记中...') : pendingOrder ? '先核对待确认订单' : selectedPlan === 'free' ? '当前已在内测版' : paymentAvailable ? '微信安全支付' : '登记开通意向（不扣款）'}</Text>
        </View>
      </View>
    </View>
  )
}

export default MembershipPage
