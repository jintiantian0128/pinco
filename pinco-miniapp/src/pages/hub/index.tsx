import React, { useMemo, useState } from 'react'
import { Input, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh, useShareAppMessage } from '@tarojs/taro'
import classnames from 'classnames'
import styles from './index.module.scss'
import { CommunityPost, PostType } from '@/types/pinco'
import {
  createCommunityComment,
  createCommunityPost,
  fetchCommunityPosts,
  reportCommunityPost,
  recordCommunityAction,
  summonCommunityReply,
  toggleCommunityHug,
  toggleCommunityLike,
} from '@/services/pinco'
import { gardenArticles } from '@/data/articles'
import { usePincoStore } from '@/store/usePincoStore'
import { trackProductEvent } from '@/services/analytics'

type FilterTab = 'all' | 'article' | PostType

const filterOptions: { key: FilterTab; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'article', label: '📖 精选' },
  { key: 'treehole', label: '🌰 树洞' },
  { key: 'help', label: '❓ 问答' },
  { key: 'share', label: '📚 干货' },
  { key: 'success', label: '🎉 上岸' },
]

const HubPage: React.FC = () => {
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all')
  const [posts, setPosts] = useState<CommunityPost[]>([])
  const [showPostModal, setShowPostModal] = useState(false)
  const [newPostTitle, setNewPostTitle] = useState('')
  const [newPostContent, setNewPostContent] = useState('')
  const [newPostType, setNewPostType] = useState<PostType>('treehole')
  const [searchQuery, setSearchQuery] = useState('')
  const [commentingPostId, setCommentingPostId] = useState<string | null>(null)
  const [commentText, setCommentText] = useState('')
  const [isPublishing, setIsPublishing] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [selectedJobId, setSelectedJobId] = useState('')
  const [experienceRound, setExperienceRound] = useState('')
  const [experienceDate, setExperienceDate] = useState('')
  const userProfile = usePincoStore((state) => state.userProfile)
  const jobProgress = usePincoStore((state) => state.jobProgress)
  const openConversation = usePincoStore((state) => state.openConversation)
  const seedConversation = usePincoStore((state) => state.seedConversation)
  const startInterview = usePincoStore((state) => state.startInterview)

  const loadPosts = async () => {
    if (!userProfile) {
      setPosts([])
      setLoadError('正在建立你的社区身份，请稍候…')
      return
    }
    try {
      const result = await fetchCommunityPosts(userProfile.user_id)
      setPosts(result.posts || [])
      setLoadError('')
    } catch (error) {
      console.error('[Hub] load posts failed', error)
      setPosts([])
      setLoadError('社区内容暂时加载失败，下拉可以重试。')
    }
  }

  useDidShow(() => {
    loadPosts()
  })

  usePullDownRefresh(() => {
    loadPosts().finally(() => Taro.stopPullDownRefresh())
  })

  useShareAppMessage(() => ({
    title: '来 Pinco 学社，知识 + 圈子一起学',
    path: '/pages/hub/index'
  }))

  const publishPost = async () => {
    if (!newPostTitle.trim() || !newPostContent.trim()) {
      Taro.showToast({ title: '标题和内容都不能为空', icon: 'none' })
      return
    }
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    if (isPublishing) return
    setIsPublishing(true)
    try {
      const result = await createCommunityPost({
        user_id: userProfile.user_id,
        title: newPostTitle.trim(),
        content: newPostContent.trim(),
        post_type: newPostType,
        job_id: selectedJobId || undefined,
        interview_round: experienceRound.trim(),
        experience_date: experienceDate.trim(),
      })
      setPosts((prev) => [result.post, ...prev])
      setNewPostTitle('')
      setNewPostContent('')
      setNewPostType('treehole')
      setSelectedJobId('')
      setExperienceRound('')
      setExperienceDate('')
      setShowPostModal(false)
      Taro.showToast({ title: '已发布到学社', icon: 'success' })
    } catch (error) {
      console.error('[Hub] publish failed', error)
      Taro.showToast({ title: '发布失败，内容已保留', icon: 'none' })
    } finally {
      setIsPublishing(false)
    }
  }

  const getArticleIcon = (category: string) => {
    if (/AI|人工智能|大模型/.test(category)) return '🤖'
    if (/洞察|趋势|数据/.test(category)) return '📊'
    if (/轻松|生活|情绪/.test(category)) return '☕'
    if (/职业|成长|转型/.test(category)) return '🚀'
    if (/面试|通关/.test(category)) return '🎯'
    if (/防坑|避坑/.test(category)) return '🛡️'
    if (/简历|包装/.test(category)) return '✨'
    return '📄'
  }

  const filteredContent = useMemo(() => {
    let filteredPosts = posts
    if (activeFilter !== 'all' && activeFilter !== 'article') {
      filteredPosts = posts.filter((p) => p.postType === activeFilter)
    }
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filteredPosts = filteredPosts.filter((p) =>
        p.title.toLowerCase().includes(query) ||
        p.content.toLowerCase().includes(query) ||
        p.author.toLowerCase().includes(query)
      )
    }
    if (activeFilter === 'all') {
      return { articles: gardenArticles, posts: filteredPosts }
    }
    if (activeFilter === 'article') {
      return { articles: gardenArticles, posts: [] }
    }
    return { articles: [], posts: filteredPosts }
  }, [activeFilter, posts, searchQuery])

  const handleLike = async (postId: string) => {
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    try {
      const result = await toggleCommunityLike(postId, userProfile.user_id)
      setPosts((prev) => prev.map((item) => (item.id === postId ? result.post : item)))
      Taro.showToast({ title: result.post.isLiked ? '已点赞' : '已取消点赞', icon: 'none' })
    } catch (error) {
      console.error('[Hub] like failed', error)
      Taro.showToast({ title: '操作失败，请重试', icon: 'none' })
    }
  }

  const submitComment = async (postId: string) => {
    if (!commentText.trim()) {
      Taro.showToast({ title: '评论不能为空', icon: 'none' })
      return
    }
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    try {
      const result = await createCommunityComment(postId, userProfile.user_id, commentText.trim())
      setPosts((prev) => prev.map((item) => (item.id === postId ? result.post : item)))
      setCommentText('')
      setCommentingPostId(null)
      Taro.showToast({ title: '评论已发布', icon: 'success' })
    } catch (error) {
      console.error('[Hub] comment failed', error)
      Taro.showToast({ title: '评论失败，内容已保留', icon: 'none' })
    }
  }

  const handleHug = async (postId: string) => {
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    try {
      const result = await toggleCommunityHug(postId, userProfile.user_id)
      setPosts((prev) => prev.map((item) => (item.id === postId ? result.post : item)))
      Taro.showToast({ title: result.post.isHugged ? '已送出抱抱' : '已收回抱抱', icon: 'none' })
    } catch (error) {
      console.error('[Hub] hug failed', error)
      Taro.showToast({ title: '抱抱没有送达，请重试', icon: 'none' })
    }
  }

  const handleSummon = async (post: CommunityPost) => {
    if (post.aiCommentLoading) return
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    setPosts((prev) => prev.map((item) => (item.id === post.id ? { ...item, aiCommentLoading: true } : item)))
    try {
      const result = await summonCommunityReply(post.id, userProfile.user_id)
      setPosts((prev) => prev.map((item) => (item.id === post.id ? result.post : item)))
      Taro.showToast({ title: '学姐已经到场', icon: 'success' })
    } catch (error) {
      console.error('[Hub] summon failed', error)
      setPosts((prev) => prev.map((item) => (item.id === post.id ? { ...item, aiCommentLoading: false } : item)))
      Taro.showToast({ title: '这次召唤失败了，再点一次', icon: 'none' })
    }
  }

  const handleReport = async (post: CommunityPost) => {
    if (!userProfile) return
    try {
      const options = ['疑似虚假求职信息', '骚扰或攻击', '广告或引流', '隐私泄露']
      const selected = await Taro.showActionSheet({ itemList: options })
      const reason = options[selected.tapIndex]
      const result = await reportCommunityPost(post.id, userProfile.user_id, reason)
      if (result.pending_review) {
        setPosts((current) => current.filter((item) => item.id !== post.id))
      }
      Taro.showToast({ title: '已提交人工审核', icon: 'none' })
    } catch (error: any) {
      if (String(error?.errMsg || '').includes('cancel')) return
      Taro.showToast({ title: error?.message || '举报未提交', icon: 'none' })
    }
  }

  const turnPostIntoAction = async (post: CommunityPost) => {
    if (!userProfile) {
      Taro.showToast({ title: '社区身份还在准备，请稍后重试', icon: 'none' })
      return
    }
    const scenario = post.postType === 'treehole' ? 'emotion' : 'interview'
    const boundJob = jobProgress.find((item) => item.id === post.boundJobId)
    const prompt = post.postType === 'treehole'
      ? `我在学社看到/写下了这段话：\n标题：${post.title}\n内容：${post.content}\n请先听我说，不要急着给大道理；再问我此刻更想被陪伴，还是一起找一个最小行动。`
      : `把下面这条学社内容转成一个 5 分钟、可直接完成的求职练习。先说明目标，再一次只给我一道题，等我回答后指出证据是否充分，不要虚构我的经历。\n标题：${post.title}\n内容：${post.content}`
    try {
      await recordCommunityAction(post.id, {
        user_id: userProfile.user_id,
        action: 'practice',
        job_id: boundJob?.id,
      })
    } catch (error) {
      console.error('[Hub] action attribution failed', error)
      Taro.showToast({ title: '行动记录暂未保存，仍可继续练习', icon: 'none' })
    }
    openConversation(scenario, post.postType === 'treehole' ? '从树洞继续聊' : '从干货开始练')
    trackProductEvent('community.action_started', userProfile?.user_id, { post_type: post.postType, action: scenario })
    await Taro.switchTab({ url: '/pages/conversation/index' })
    if (post.postType === 'treehole') {
      await seedConversation('emotion', prompt, '从树洞继续聊')
      return
    }
    await startInterview(boundJob?.position || 'AI 求职面试', 5, {
      company: boundJob?.company || '',
      jobId: boundJob?.id,
      sourcePostId: post.id,
      anxietyFocus: `把《${post.title}》转成可练习的行动`,
      practiceStyle: 'warmup',
    })
  }

  const renderPost = (post: CommunityPost) => {
    const isTreehole = post.postType === 'treehole'
    return (
      <View key={post.id} className={styles.postCard}>
        <View className={styles.postTop}>
          <View className={styles.authorBlock}>
            <Text className={styles.author}>{isTreehole ? '匿名树洞' : post.author}</Text>
            <View style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
              {isTreehole && <Text className={styles.treeholeBadge}>树洞</Text>}
              {post.isExample && <Text className={styles.exampleBadge}>官方示例</Text>}
              {post.isFeatured && <Text className={styles.exampleBadge}>人工精选</Text>}
              <Text className={styles.meta}>{post.roleTag} · {post.time}</Text>
            </View>
          </View>
          <View className={styles.summonButton} onClick={() => handleSummon(post)}>
            <Text>{post.aiCommentLoading ? '学姐组织语言中' : '召唤学姐'}</Text>
          </View>
        </View>
        <Text className={styles.titleText}>{post.title}</Text>
        <Text className={styles.contentText}>{post.content}</Text>
        {post.boundJobLabel && <Text className={styles.meta}>关联岗位：{post.boundJobLabel}</Text>}
        {(post.experienceRound || post.experienceDate) && <Text className={styles.meta}>经验标签：{[post.experienceRound, post.experienceDate].filter(Boolean).join(' · ')}</Text>}
        <View className={styles.practiceButton} onClick={() => turnPostIntoAction(post)}>
          <Text>{isTreehole ? '和学姐继续聊 →' : '把这条转成 5 分钟练习 →'}</Text>
        </View>
        <View className={styles.actions}>
          {isTreehole ? (
            <View className={styles.hugButton} onClick={() => handleHug(post.id)}>
              <Text className={classnames(styles.actionText, post.isHugged && styles.actionTextActive)}>
                {post.isHugged ? '🤗 已抱抱' : '🤗 抱抱'} · {post.hugs || 0}
              </Text>
            </View>
          ) : (
            <Text
              className={classnames(styles.actionText, post.isLiked && styles.actionTextActive)}
              onClick={() => handleLike(post.id)}
            >
              {post.isLiked ? '已点赞' : '点赞'} · {post.likes}
            </Text>
          )}
          <Text className={styles.actionText}>评论 · {post.comments.length}</Text>
          {!post.isExample && <Text className={styles.actionText} onClick={() => handleReport(post)}>举报</Text>}
        </View>
        {post.comments.length > 0 && (
          <View className={styles.commentList}>
            {post.comments.map((comment) => (
              <View key={comment.id} className={styles.commentCard}>
                <Text className={styles.commentAuthor}>{comment.isAi ? 'Pinco学姐' : comment.author}</Text>
                <Text className={styles.commentText}>{comment.text}</Text>
              </View>
            ))}
          </View>
        )}
        {commentingPostId === post.id ? (
          <View className={styles.commentInputBar}>
            <Textarea
              className={styles.commentInput}
              value={commentText}
              onInput={(e) => setCommentText(e.detail.value)}
              placeholder="写下你的评论..."
              maxlength={200}
              autoHeight
              showConfirmBar={false}
            />

            <View className={styles.commentActions}>
              <View className={styles.commentCancel} onClick={() => { setCommentingPostId(null); setCommentText(''); }}>
                <Text>取消</Text>
              </View>
              <View className={styles.commentSubmit} onClick={() => submitComment(post.id)}>
                <Text>发布</Text>
              </View>
            </View>
          </View>
        ) : (
          <View className={styles.commentTrigger} onClick={() => setCommentingPostId(post.id)}>
            <Text className={styles.commentTriggerText}>💬 写评论...</Text>
          </View>
        )}
      </View>
    )
  }

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <View>
          <Text className={styles.title}>学社</Text>
          <Text className={styles.desc}>{gardenArticles.length} 篇干货 · {posts.length} 条讨论</Text>
        </View>
        <View className={styles.headerPostButton} onClick={() => setShowPostModal(true)}>
          <Text>✎ 发布</Text>
        </View>
      </View>

      <View className={styles.searchBar}>
        <Text className={styles.searchIcon}>🔍</Text>
        <Textarea
          className={styles.searchInput}
          value={searchQuery}
          onInput={(e) => setSearchQuery(e.detail.value)}
          placeholder="搜索帖子标题或内容..."
          maxlength={50}
          autoHeight
          showConfirmBar={false}
        />
        {searchQuery && (
          <View className={styles.searchClear} onClick={() => setSearchQuery('')}>
            <Text>✕</Text>
          </View>
        )}
      </View>

      <ScrollView className={styles.filterBar} scrollX enhanced showScrollbar={false}>
        <View className={styles.filterBarInner}>
          {filterOptions.map((opt) => (
            <View
              key={opt.key}
              className={classnames(styles.filterChip, activeFilter === opt.key && styles.filterChipActive)}
              onClick={() => setActiveFilter(opt.key)}
            >
              <Text>{opt.label}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      {filteredContent.articles.length > 0 && (
        <>
          <Text className={styles.sectionTitle}>精选干货</Text>
          {filteredContent.articles.map((article) => (
            <View
              key={article.id}
              className={styles.articleCard}
              onClick={() => Taro.navigateTo({ url: `/pages/article/index?id=${article.id}` })}
            >
              <View className={styles.articleIconBox}>
                <Text>{getArticleIcon(article.category)}</Text>
              </View>
              <View className={styles.articleBody}>
                <View className={styles.articleMeta}>
                  <Text className={styles.articleType}>📚 干货</Text>
                  <Text className={styles.articleCategory}>{article.category}</Text>
                  <Text className={styles.articleReads}>{article.reads}</Text>
                </View>
                <Text className={styles.articleTitle}>{article.title}</Text>
                <Text className={styles.articleSubtitle}>{article.subtitle}</Text>
              </View>
            </View>
          ))}
        </>
      )}

      {filteredContent.posts.length > 0 && (
        <>
          <View className={styles.postSectionHeader}>
            <Text className={styles.sectionTitle}>社区动态</Text>
            <View className={styles.postButton} onClick={() => setShowPostModal(true)}>
              <Text className={styles.postButtonText}>+ 发布</Text>
            </View>
          </View>
          {filteredContent.posts.map(renderPost)}
        </>
      )}

      {filteredContent.articles.length === 0 && filteredContent.posts.length === 0 && (
        <View className={styles.emptyState}>
          <Text>{loadError || '这个分类下还没有内容，成为第一个分享的人吧。'}</Text>
        </View>
      )}

      {/* 发帖弹层 */}
      {showPostModal && (
        <View className={styles.postModalOverlay} onClick={() => setShowPostModal(false)}>
          <View className={styles.postModal} onClick={(e) => e.stopPropagation()}>
            <Text className={styles.postModalTitle}>发布新帖</Text>

            <ScrollView className={styles.postModalBody} scrollY enhanced showScrollbar={false}>
            <View className={styles.typeSelector}>
              {(['treehole', 'help', 'share', 'success'] as PostType[]).map((t) => (
                <View
                  key={t}
                  className={classnames(styles.typeChip, newPostType === t && styles.typeChipActive)}
                  onClick={() => setNewPostType(t)}
                >
                  <Text className={styles.typeChipText}>
                    {t === 'treehole' ? '🌰 树洞' : t === 'help' ? '❓ 问答' : t === 'share' ? '📚 干货' : '🎉 上岸'}
                  </Text>
                </View>
              ))}
            </View>

            <Input
              className={styles.postTitleInput}
              value={newPostTitle}
              onInput={(e) => setNewPostTitle(e.detail.value)}
              placeholder="标题"
              maxlength={100}
            />
            <Textarea
              className={styles.postContentInput}
              value={newPostContent}
              onInput={(e) => setNewPostContent(e.detail.value)}
              placeholder={newPostType === 'treehole' ? '这里很安全，想说就说...' : newPostType === 'help' ? '详细描述你的问题，大家一起来帮你...' : newPostType === 'share' ? '分享你的经验或心得...' : '恭喜上岸！分享你的成功经验，给学弟学妹们一点鼓励...'}
              maxlength={1000}
              fixed
              cursorSpacing={24}
              disableDefaultPadding
              showConfirmBar={false}
            />
            <Text className={styles.inputCount}>{newPostContent.length}/1000</Text>

            {jobProgress.length > 0 && (
              <View>
                <Text className={styles.meta}>关联岗位（可选，便于后续练习与复盘沉淀到同一岗位）</Text>
                <ScrollView className={styles.filterBar} scrollX enhanced showScrollbar={false}>
                  <View className={styles.filterBarInner}>
                    <View className={classnames(styles.typeChip, !selectedJobId && styles.typeChipActive)} onClick={() => setSelectedJobId('')}><Text>不关联</Text></View>
                    {jobProgress.map((job) => (
                      <View key={job.id} className={classnames(styles.typeChip, selectedJobId === job.id && styles.typeChipActive)} onClick={() => setSelectedJobId(job.id)}>
                        <Text>{job.company} · {job.position}</Text>
                      </View>
                    ))}
                  </View>
                </ScrollView>
              </View>
            )}
            {['share', 'success'].includes(newPostType) && (
              <View>
                <Text className={styles.meta}>经验标签（可选，帮助其他人判断是否适用）</Text>
                <Input className={styles.postTitleInput} value={experienceRound} onInput={(e) => setExperienceRound(e.detail.value)} placeholder="面试轮次 / 场景，如：业务一面、项目深挖" maxlength={40} />
                <Input className={styles.postTitleInput} value={experienceDate} onInput={(e) => setExperienceDate(e.detail.value)} placeholder="发生时间，如：2026年8月" maxlength={40} />
              </View>
            )}
            </ScrollView>

            <View className={styles.postModalButtons}>
              <View className={styles.postModalCancel} onClick={() => setShowPostModal(false)}>
                <Text>取消</Text>
              </View>
              <View
                className={classnames(styles.postModalConfirm, (!newPostTitle.trim() || !newPostContent.trim() || isPublishing) && styles.postModalConfirmDisabled)}
                onClick={publishPost}
              >
                <Text>{isPublishing ? '发布中…' : '发布'}</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  )
}

export default HubPage
