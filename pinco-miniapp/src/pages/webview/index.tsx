import React from 'react'
import { WebView } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { usePageAnalytics } from '@/hooks/usePageAnalytics'

const WebviewPage: React.FC = () => {
  usePageAnalytics('webview')
  const [url, setUrl] = React.useState('')

  useLoad((options) => {
    if (typeof options?.url === 'string') {
      setUrl(decodeURIComponent(options.url))
    }
  })

  return (
    <WebView src={url} onError={() => Taro.showToast({ title: '页面加载失败', icon: 'none' })} />
  )
}

export default WebviewPage
