import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Image, Input, ScrollView, Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useRouter } from '@tarojs/taro'
import styles from './index.module.scss'
import { BookingMessage, BookingThreadResponse } from '@/types/pinco'
import { fetchBookingMessages, sendBookingMessage } from '@/services/pinco'
import { usePincoStore } from '@/store/usePincoStore'

declare const wx: any

const MAX_IMAGE_BYTES = 4 * 1024 * 1024

const BookingChatPage: React.FC = () => {
  const router = useRouter()
  const bookingId = String(router.params.booking_id || '')
  const userProfile = usePincoStore((state) => state.userProfile)
  const bootstrap = usePincoStore((state) => state.bootstrap)
  const [thread, setThread] = useState<BookingThreadResponse | null>(null)
  const [draft, setDraft] = useState('')
  const [pendingImage, setPendingImage] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(async (quiet = false) => {
    let userId = usePincoStore.getState().userProfile?.user_id
    if (!userId) {
      await bootstrap()
      userId = usePincoStore.getState().userProfile?.user_id
    }
    if (!bookingId || !userId) {
      if (!quiet) setLoadError('身份或预约信息尚未准备好，请返回后重试。')
      return
    }
    try {
      const result = await fetchBookingMessages(bookingId, userId)
      setThread(result)
      setLoadError('')
    } catch (error) {
      console.error('[BookingChat] load failed', error)
      if (!quiet) setLoadError('咨询消息暂时加载失败，下拉可以重试。')
    }
  }, [bookingId, bootstrap])

  useDidShow(() => { load() })
  usePullDownRefresh(() => load().finally(() => Taro.stopPullDownRefresh()))

  useEffect(() => {
    if (!userProfile?.user_id) return
    load()
    const timer = setInterval(() => load(true), 8000)
    return () => clearInterval(timer)
  }, [load, userProfile?.user_id])

  const canChat = thread?.booking.consultation_type === 'chat'
    && !['rejected', 'completed', 'cancelled'].includes(thread.booking.status_code || '')
  const scrollTarget = useMemo(() => {
    const messages = thread?.messages || []
    return messages.length ? `message-${messages[messages.length - 1].id}` : 'thread-start'
  }, [thread?.messages])

  const chooseImage = async () => {
    try {
      const result = await Taro.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: ['album', 'camera'] })
      const filePath = result.tempFilePaths?.[0]
      if (!filePath) return
      const info = await Taro.getFileInfo({ filePath })
      if ((info as any).size > MAX_IMAGE_BYTES) {
        Taro.showToast({ title: '图片需小于 4MB，请压缩后重试', icon: 'none' })
        return
      }
      setPendingImage(filePath)
    } catch (error: any) {
      if (!String(error?.errMsg || '').includes('cancel')) {
        console.error('[BookingChat] choose image failed', error)
        Taro.showToast({ title: '选择图片失败，请重试', icon: 'none' })
      }
    }
  }

  const uploadPendingImage = async () => {
    if (!pendingImage) return ''
    if (!wx?.cloud?.uploadFile) throw new Error('当前微信版本不支持云存储上传')
    const safeBookingId = bookingId.replace(/[^a-zA-Z0-9_-]/g, '')
    const suffix = (pendingImage.split('.').pop() || 'jpg').replace(/[^a-zA-Z0-9]/g, '')
    const cloudPath = `consultations/${safeBookingId}/${Date.now()}-${Math.random().toString(36).slice(2, 9)}.${suffix}`
    const result = await wx.cloud.uploadFile({ cloudPath, filePath: pendingImage })
    if (!result?.fileID) throw new Error('图片上传没有返回文件地址')
    return String(result.fileID)
  }

  const send = async () => {
    const userId = usePincoStore.getState().userProfile?.user_id
    if (!canChat || !userId || loading || (!draft.trim() && !pendingImage)) return
    setLoading(true)
    try {
      if (pendingImage) Taro.showLoading({ title: '正在发送…', mask: true })
      const imageFileId = await uploadPendingImage()
      const result = await sendBookingMessage(bookingId, userId, draft.trim(), imageFileId)
      setThread((current) => current ? { ...current, booking: result.booking, messages: result.messages } : current)
      setDraft('')
      setPendingImage('')
    } catch (error: any) {
      console.error('[BookingChat] send failed', error)
      Taro.showToast({ title: error?.message || '发送失败，请重试', icon: 'none', duration: 3000 })
    } finally {
      Taro.hideLoading()
      setLoading(false)
    }
  }

  const renderMessage = (message: BookingMessage) => {
    const isMine = message.sender_role === thread?.participant_role
    if (message.sender_role === 'system') {
      return <View id={`message-${message.id}`} key={message.id} className={styles.systemMessage}><Text>{message.content}</Text></View>
    }
    return (
      <View id={`message-${message.id}`} key={message.id} className={`${styles.messageRow} ${isMine ? styles.messageRowMine : ''}`}>
        <View className={`${styles.bubble} ${isMine ? styles.bubbleMine : ''}`}>
          <Text className={styles.senderName}>{message.sender_name}</Text>
          {message.content && <Text className={styles.messageText}>{message.content}</Text>}
          {message.image_file_id && <Image className={styles.messageImage} src={message.image_file_id} mode="widthFix" />}
          {message.contact_value && (
            <View className={styles.contactCard}>
              <Text className={styles.contactLabel}>{message.contact_type === 'phone' ? '电话联系方式' : '会议链接'}</Text>
              <Text className={styles.contactValue} selectable>{message.contact_value}</Text>
              <View className={styles.copyButton} onClick={() => Taro.setClipboardData({ data: message.contact_value || '' })}><Text>复制</Text></View>
            </View>
          )}
          <Text className={styles.time}>{message.created_at?.slice(5, 16).replace('T', ' ')}</Text>
        </View>
      </View>
    )
  }

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.title}>{thread?.booking.expertName || '咨询消息'}</Text>
        <Text className={styles.subtitle}>
          {thread?.booking.consultation_type === 'chat' ? '图文咨询 · 双方在 Pinco 内沟通' : '电话咨询 · 专家接受后发送联系方式'}
        </Text>
        {thread?.booking && <Text className={styles.status}>{thread.booking.slot} · {thread.booking.status}</Text>}
      </View>

      <ScrollView className={styles.messages} scrollY scrollIntoView={scrollTarget} scrollWithAnimation>
        <View id="thread-start" />
        {loadError && <View className={styles.errorCard} onClick={() => load()}><Text>{loadError}</Text></View>}
        {!loadError && thread?.messages.length === 0 && (
          <View className={styles.emptyCard}><Text>还没有消息。专家处理预约后，更新会显示在这里。</Text></View>
        )}
        {(thread?.messages || []).map(renderMessage)}
      </ScrollView>

      {canChat ? (
        <View className={styles.composer}>
          {pendingImage && (
            <View className={styles.previewWrap}>
              <Image className={styles.previewImage} src={pendingImage} mode="aspectFill" />
              <View className={styles.removePreview} onClick={() => setPendingImage('')}><Text>移除</Text></View>
            </View>
          )}
          <View className={styles.composerRow}>
            <View className={styles.imageButton} onClick={chooseImage}><Text>＋图片</Text></View>
            <Input
              className={styles.input}
              value={draft}
              onInput={(event) => setDraft(event.detail.value)}
              placeholder="输入咨询消息"
              maxlength={2000}
              confirmType="send"
              onConfirm={send}
            />
            <View className={`${styles.sendButton} ${loading ? styles.sendButtonDisabled : ''}`} onClick={send}><Text>发送</Text></View>
          </View>
          <Text className={styles.privacyNote}>仅本次预约的求职者和专家可见，请勿发送身份证、银行卡等敏感信息。</Text>
        </View>
      ) : (
        <View className={styles.readonlyBar}>
          <Text>{thread?.booking.consultation_type === 'phone' ? '电话咨询仅用于接收专家发送的电话或会议链接' : '本次咨询已结束，消息仅供查看'}</Text>
        </View>
      )}
    </View>
  )
}

export default BookingChatPage
