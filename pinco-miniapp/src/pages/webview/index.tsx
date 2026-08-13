import React from 'react'
import { WebView } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'

const WebviewPage: React.FC = () => {
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
