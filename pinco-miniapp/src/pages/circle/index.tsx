import React, { useEffect, useMemo, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useShareAppMessage } from '@tarojs/taro'
import styles from './index.module.scss'
import { CommunityPost } from '@/types/pinco'
import { fetchCommunityPosts, summonCommunityReply, toggleCommunityLike } from '@/services/pinco'
import { usePincoStore } from '@/store/usePincoStore'

const CirclePage: React.FC = () => {
  const [posts, setPosts] = useState<CommunityPost[]>([])
  const userProfile = usePincoStore((state) => state.userProfile)

  const loadPosts = async () => {
    if (!userProfile) return
    try {
      const result = await fetchCommunityPosts(userProfile.user_id)
      setPosts(result.posts)
    } catch (error) {
      console.error('[Circle] load posts failed', error)
      Taro.showToast({ title: '圈子加载失败', icon: 'none' })
    }
  }

  useDidShow(() => {
    loadPosts()
  })

  useEffect(() => {
    if (userProfile) {
      loadPosts()
    }
  }, [userProfile])

  usePullDownRefresh(() => {
    loadPosts().finally(() => Taro.stopPullDownRefresh())
  })

  useShareAppMessage(() => ({
    title: '来 Pinco 圈子看看大家都在怎么熬过求职低谷',
    path: '/pages/circle/index'
  }))

  const postCount = useMemo(() => posts.length, [posts])

  const handleLike = async (postId: string) => {
    if (!userProfile) return
    try {
      const result = await toggleCommunityLike(postId, userProfile.user_id)
      setPosts((prev) => prev.map((item) => item.id === postId ? result.post : item))
    } catch (error) {
      console.error('[Circle] like failed', error)
      Taro.showToast({ title: '点赞失败，请重试', icon: 'none' })
    }
  }

  const handleSummon = async (post: CommunityPost) => {
    if (!userProfile || post.aiCommentLoading) return
    setPosts((prev) => prev.map((item) => item.id === post.id ? { ...item, aiCommentLoading: true } : item))
    try {
      const result = await summonCommunityReply(post.id, userProfile.user_id)
      setPosts((prev) => prev.map((item) => item.id === post.id ? result.post : item))
      Taro.showToast({ title: '学姐已经到场', icon: 'success' })
    } catch (error) {
      console.error('[Circle] summon failed', error)
      setPosts((prev) => prev.map((item) => item.id === post.id ? { ...item, aiCommentLoading: false } : item))
      Taro.showToast({ title: '这次召唤失败了，再点一次', icon: 'none' })
    }
  }

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.title}>职场圈子</Text>
        <Text className={styles.desc}>这里是低气压时的缓冲带。你可以看别人的样本，也可以直接召唤学姐来接住你的情绪。</Text>
        <Text className={styles.desc}>当前共有 {postCount} 条公开内容；官方内容会明确标注，不展示虚构互动数。</Text>
      </View>

      {posts.map((post) => (
        <View key={post.id} className={styles.postCard}>
          <View className={styles.postTop}>
            <View className={styles.authorBlock}>
              <Text className={styles.author}>{post.author}</Text>
              <Text className={styles.meta}>{post.roleTag} · {post.time}</Text>
            </View>
            <View className={styles.summonButton} onClick={() => handleSummon(post)}>
              <Text>{post.aiCommentLoading ? '学姐组织语言中' : '召唤学姐'}</Text>
            </View>
          </View>
          <Text className={styles.titleText}>{post.title}</Text>
          <Text className={styles.contentText}>{post.content}</Text>
          <View className={styles.actions}>
            <Text className={styles.actionText} onClick={() => handleLike(post.id)}>{post.isLiked ? '已点赞' : '点赞'} · {post.likes}</Text>
            <Text className={styles.actionText}>评论 · {post.comments.length}</Text>
          </View>
          <View className={styles.commentList}>
            {post.comments.map((comment) => (
              <View key={comment.id} className={styles.commentCard}>
                <Text className={styles.commentAuthor}>{comment.author}</Text>
                <Text className={styles.commentText}>{comment.text}</Text>
              </View>
            ))}
          </View>
        </View>
      ))}
    </View>
  )
}

export default CirclePage
