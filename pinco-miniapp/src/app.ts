import { useEffect } from 'react'
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
    bootstrap()
  })

  useDidHide(() => {})

  return props.children
}

export default App
