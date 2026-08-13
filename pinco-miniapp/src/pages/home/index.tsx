import React, { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { usePullDownRefresh, useShareAppMessage } from '@tarojs/taro'
import classnames from 'classnames'
import styles from './index.module.scss'
import { homeActions } from '@/data/home'
import { usePincoStore } from '@/store/usePincoStore'
import { ConversationScenario } from '@/types/pinco'

const HomePage: React.FC = () => {
  const serviceTimeline = usePincoStore((state) => state.serviceTimeline)
  const bookings = usePincoStore((state) => state.bookings)
  const messages = usePincoStore((state) => state.messages)
  const todayTasks = usePincoStore((state) => state.todayTasks)
  const jobProgress = usePincoStore((state) => state.jobProgress)
  const openConversation = usePincoStore((state) => state.openConversation)
  const refreshServiceHealth = usePincoStore((state) => state.refreshServiceHealth)
  const checkInEmotion = usePincoStore((state) => state.checkInEmotion)
  const supportDueFollowUps = usePincoStore((state) => state.supportDueFollowUps)
  const respondSupportFollowUp = usePincoStore((state) => state.respondSupportFollowUp)
  const [checkingMood, setCheckingMood] = useState(false)
  const latestBooking = bookings[0]
  const latestSummary = [...messages].reverse().find((item) => item.role === 'assistant')?.content || '还没开始正式会话，先把你最卡的一件事告诉学姐。'
  const undoneTasks = todayTasks.filter((t) => !t.done)
  const doneCount = todayTasks.filter((t) => t.done).length

  usePullDownRefresh(() => {
    refreshServiceHealth().finally(() => Taro.stopPullDownRefresh())
  })

  useShareAppMessage(() => ({
    title: 'Pinco AI职场学姐，帮你把求职和职场问题拆清楚',
    path: '/pages/home/index'
  }))

  const enterConversation = (scenario: ConversationScenario = 'general', subtitle = '继续和学姐往下聊') => {
    openConversation(scenario, subtitle)
    Taro.navigateTo({ url: `/pages/conversation/index?scenario=${scenario}` })
  }

  const handleMoodCheckIn = async (intensity: 1 | 2 | 3 | 4 | 5) => {
    if (checkingMood) return
    setCheckingMood(true)
    try {
      await checkInEmotion(intensity)
      Taro.navigateTo({ url: '/pages/conversation/index?scenario=emotion' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '状态打卡失败，请稍后再试', icon: 'none' })
    } finally {
      setCheckingMood(false)
    }
  }

  const handleFollowUp = async (checkInId: string, intensity: 1 | 3 | 4) => {
    if (checkingMood) return
    const actionResult = await Taro.showModal({
      title: '昨天约定的小行动完成了吗？',
      content: '如实回答就好，没有完成也不会被催促或评价。',
      confirmText: '完成了',
      cancelText: '还没有'
    })
    setCheckingMood(true)
    try {
      await respondSupportFollowUp(checkInId, intensity, actionResult.confirm)
      Taro.navigateTo({ url: '/pages/conversation/index?scenario=emotion' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '回访回应失败，请稍后再试', icon: 'none' })
    } finally {
      setCheckingMood(false)
    }
  }

  return (
    <View className={styles.page}>
      <View className={styles.heroCard}>
        <Text className={styles.eyebrow}>Pinco AI职场学姐</Text>
        <Text className={styles.heroTitle}>先别自己硬扛，让学姐帮你排清楚今天最该做的那一步</Text>
        <Text className={styles.heroDesc}>简历诊断、模拟面试、JD解读、情绪陪伴——带着场景进去，学姐帮你拆成可执行动作。</Text>
        <View className={styles.primaryButton} onClick={() => enterConversation('general', '继续和学姐往下聊')}>
          <Text>立即进入专属会话</Text>
        </View>
      </View>

      {jobProgress.length === 0 && (
        <View className={styles.section}>
          <View className={styles.sectionHeader}>
            <Text className={styles.sectionTitle}>第一次来，先建求职作战台</Text>
            <Text className={styles.sectionHint}>约 5 分钟</Text>
          </View>
          <Text className={styles.heroDesc}>只补四件事：目标 AI 岗、求职期限、当前简历、第一份真实 JD。之后的材料、练习、学社和专家服务都会围绕同一个岗位沉淀。</Text>
          <View className={styles.primaryButton} onClick={() => Taro.navigateTo({ url: '/pages/career/index' })}>
            <Text>填写目标并粘贴第一份 JD</Text>
          </View>
          <View className={styles.actionChip} onClick={() => enterConversation('resume', '先上传当前简历')}>
            <Text className={styles.actionChipText}>我先上传当前简历</Text>
          </View>
        </View>
      )}

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>学姐先问一句：今天状态怎么样？</Text>
          <Text className={styles.sectionHint}>不是绩效打分</Text>
        </View>
        <View className={styles.moodRow}>
          {([
            { score: 1, emoji: '🌧', label: '撑不住' },
            { score: 2, emoji: '🥲', label: '很累' },
            { score: 3, emoji: '😮‍💨', label: '有点绷' },
            { score: 4, emoji: '🙂', label: '还可以' },
            { score: 5, emoji: '🌤', label: '有力量' },
          ] as const).map((mood) => (
            <View key={mood.score} className={styles.moodItem} onClick={() => handleMoodCheckIn(mood.score)}>
              <Text className={styles.moodEmoji}>{mood.emoji}</Text>
              <Text className={styles.moodLabel}>{mood.label}</Text>
            </View>
          ))}
        </View>
        <Text className={styles.moodPrivacy}>默认只记录状态分数，不保存你的倾诉正文；可在“我的”里调整陪伴方式。</Text>
      </View>

      {supportDueFollowUps.map((followUp) => (
        <View key={followUp.check_in_id} className={styles.followUpCard}>
          <Text className={styles.followUpEyebrow}>学姐按约回来看看你</Text>
          <Text className={styles.followUpMessage}>{followUp.message}</Text>
          <View className={styles.followUpActions}>
            <View onClick={() => handleFollowUp(followUp.check_in_id, 4)}><Text>好一些</Text></View>
            <View onClick={() => handleFollowUp(followUp.check_in_id, 3)}><Text>差不多</Text></View>
            <View onClick={() => handleFollowUp(followUp.check_in_id, 1)}><Text>更难受</Text></View>
          </View>
        </View>
      ))}

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>今日任务</Text>
          <Text className={styles.sectionHint}>{doneCount}/{todayTasks.length} 已完成</Text>
        </View>
        <View className={styles.taskList}>
          {undoneTasks.length > 0 ? undoneTasks.map((task) => (
            <View key={task.id} className={styles.taskItem} onClick={() => {
              if (task.action === 'chat') {
                openConversation(task.scenario || 'general', task.title)
                Taro.navigateTo({ url: `/pages/conversation/index?scenario=${task.scenario || 'general'}` })
              } else if (task.action === 'booking') {
                Taro.switchTab({ url: '/pages/experts/index' })
              } else if (task.action === 'circle') {
                Taro.navigateTo({ url: '/pages/circle/index' })
              }
            }}>
              <Text className={styles.taskEmoji}>{task.emoji}</Text>
              <View className={styles.taskContent}>
                <Text className={styles.taskTitle}>{task.title}</Text>
                <Text className={styles.taskDesc}>{task.desc}</Text>
              </View>
              <Text className={styles.taskArrow}>›</Text>
            </View>
          )) : (
            <View className={styles.taskEmpty}>
              <Text className={styles.taskEmptyText}>{todayTasks.length ? '今天的任务都完成了，先歇一会儿。' : '还没有今日任务，可在“我的”里根据当前阶段生成。'}</Text>
            </View>
          )}
        </View>
      </View>

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>搜岗位</Text>
          <Text className={styles.sectionHint}>只展示可验证来源</Text>
        </View>
        <View className={styles.searchEntry} onClick={() => Taro.navigateTo({ url: '/pages/job-search/index' })}>
          <Text className={styles.searchEntryIcon}>🔍</Text>
          <Text className={styles.searchEntryPlaceholder}>搜索岗位，如：AI产品经理、前端开发...</Text>
          <Text className={styles.searchEntryArrow}>›</Text>
        </View>
      </View>

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>快捷操作</Text>
        </View>
        <View className={styles.actionRow}>
          {homeActions.map((item) => (
            <View
              key={item.id}
              className={styles.actionChip}
              onClick={() => {
                openConversation(item.scenario, item.subtitle)
                Taro.navigateTo({
                  url: `/pages/conversation/index?scenario=${item.scenario}&prompt=${encodeURIComponent(item.prompt)}`
                })
              }}
            >
              <Text className={styles.actionChipText}>{item.title}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>今天先看这两件事</Text>
          <Text className={styles.sectionHint}>优先级会影响你的手感</Text>
        </View>
        <View className={styles.statusGrid}>
          <View className={styles.statusCard} onClick={() => enterConversation()}>
            <Text className={styles.statusLabel}>最近会话</Text>
            <Text className={styles.statusValue}>{messages.length > 1 ? '已开启' : '未开始'}</Text>
            <Text className={styles.statusDesc}>{latestSummary.slice(0, 36)}</Text>
          </View>
          <View className={styles.statusCard} onClick={() => Taro.switchTab({ url: '/pages/experts/index' })}>
            <Text className={styles.statusLabel}>最近服务</Text>
            <Text className={styles.statusValue}>{latestBooking ? latestBooking.expertName : '还没预约专家'}</Text>
            <Text className={styles.statusDesc}>{latestBooking ? latestBooking.slot : '需要的时候再约，不用硬下单'}</Text>
          </View>
        </View>
      </View>

      <View className={styles.section}>
        <View className={styles.sectionHeader}>
          <Text className={styles.sectionTitle}>服务推进中</Text>
          <Text className={styles.sectionHint}>学姐在帮你盯节奏</Text>
        </View>
        <View className={styles.timelineCard}>
          {serviceTimeline.map((item) => (
            <View key={item.id} className={styles.timelineItem}>
              <View className={classnames(styles.timelineDot, {
                [styles.dotDone]: item.status === 'done',
                [styles.dotActive]: item.status === 'active',
                [styles.dotPending]: item.status === 'pending'
              })}
              >
                <Text>{item.status === 'done' ? '✓' : item.status === 'active' ? '!' : '·'}</Text>
              </View>
              <View>
                <Text className={styles.timelineTitle}>{item.title}</Text>
                <Text className={styles.timelineDesc}>{item.desc}</Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  )
}

export default HomePage
