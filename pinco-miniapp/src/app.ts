import { useEffect, useRef } from 'react'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { usePincoStore } from '@/store/usePincoStore'
import './app.scss'

// 初始化微信云开发（用于 callContainer 调用云托管）
if (typeof wx !== 'undefined' && wx.cloud) {
  console.info('[App] Initializing wx.cloud', 'env=prod-d1g71nka2ab801ddb')
  wx.cloud.init({
    env: 'prod-d1g71nka2ab801ddb',
    traceUser: false
  })
  console.info('[App] wx.cloud initialized successfully')
} else {
  console.warn('[App] wx.cloud not available, running in non-weapp environment')
}

function App(props) {
  const bootstrap = usePincoStore((state) => state.bootstrap)
  const setLaunchScene = usePincoStore((state) => state.setLaunchScene)
  const careerReminders = usePincoStore((state) => state.careerReminders)
  const reminderPromptOpen = useRef(false)

  useEffect(() => {
    const options = Taro.getLaunchOptionsSync?.()
    if (options?.scene) {
      setLaunchScene(String(options.scene))
    }
    bootstrap()

  }, [bootstrap, setLaunchScene])

  const loadMessages = usePincoStore((state) => state.loadMessages)
  const loadTodayTasks = usePincoStore((state) => state.loadTodayTasks)
  useEffect(() => {
    loadMessages()
    loadTodayTasks()
  }, [loadMessages, loadTodayTasks])

  useDidShow(() => {
    const state = usePincoStore.getState()
    if (!state.userProfile?.user_id) bootstrap()
    else state.refreshCareerReminders().catch((error) => console.warn('[App] refresh career reminders failed', error))
  })

  // 小程序没有后台定时执行能力；用户启动或回到前台时检查云端到期提醒。
  useEffect(() => {
    if (reminderPromptOpen.current) return
    const reminder = careerReminders.find((item) => item.status === 'pending' && Date.parse(item.due_at) <= Date.now())
    if (!reminder) return

    const today = new Date()
    const dayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    const storageKey = `pinco_career_reminder_alert_${reminder.id}`
    try {
      if (Taro.getStorageSync(storageKey) === dayKey) return
      Taro.setStorageSync(storageKey, dayKey)
    } catch {}

    reminderPromptOpen.current = true
    Taro.showModal({
      title: '求职跟进时间到了',
      content: `${reminder.company} · ${reminder.title}\n${reminder.note || '要不要和学姐一起确认下一步？'}`,
      confirmText: '现在跟进',
      cancelText: '稍后再看',
    }).then(async (result) => {
      if (!result.confirm) return
      const state = usePincoStore.getState()
      try { await state.updateCareerReminderStatus(reminder.id, 'completed') }
      catch (error) { console.warn('[App] mark reminder started failed', error) }
      state.openConversation('general')
      await Taro.switchTab({ url: '/pages/conversation/index' })
      await state.seedConversation('general', `提醒我跟进 ${reminder.company} 的 ${reminder.title}。请回顾已记录进度，给我一个具体、可执行的下一步。`)
    }).catch((error) => console.warn('[App] show career reminder failed', error))
      .finally(() => { reminderPromptOpen.current = false })
  }, [careerReminders])

  useDidHide(() => {})

  return props.children
}

export default App
