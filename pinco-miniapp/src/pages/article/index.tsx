import React, { useMemo } from 'react'
import { Button, ScrollView, Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import styles from './index.module.scss'
import { gardenArticles } from '@/data/articles'
import { usePincoStore } from '@/store/usePincoStore'
import { usePageAnalytics } from '@/hooks/usePageAnalytics'

const ArticlePage: React.FC = () => {
  usePageAnalytics('article')
  const [articleId, setArticleId] = React.useState(gardenArticles[0]?.id)
  const seedConversation = usePincoStore((state) => state.seedConversation)

  useLoad((options) => {
    if (typeof options?.id === 'string') {
      setArticleId(options.id)
    }
  })

  const article = useMemo(() => gardenArticles.find((item) => item.id == articleId) || gardenArticles[0], [articleId])

  useShareAppMessage(() => ({
    title: article.title,
    path: `/pages/article/index?id=${article.id}`
  }))

  const startArticlePractice = async () => {
    const prompt = `学姐，我刚看完《${article.title}》。请把文章观点转成一个 5 分钟求职练习：先告诉我练习目标，再一次只给一个问题，等我回答后再反馈，不要虚构我的经历。`
    try {
      // 先同步启动全局 store 任务，再切 tab。部分微信基础库虽然已经完成
      // switchTab，却不会继续 resolve 原页面里的 Promise；若把 seed 放在 await
      // 之后，用户会看到页面跳转成功但练习永远没有创建。
      const practiceTask = seedConversation('garden', prompt, '把文章变成一次练习')
      await Taro.switchTab({ url: '/pages/conversation/index' })
      await practiceTask
    } catch (error) {
      console.error('[Article] failed to start practice', error)
      Taro.showToast({ title: '未能打开练习，请重试', icon: 'none' })
    }
  }

  return (
    <ScrollView className={styles.reader} scrollY enhanced showScrollbar>
      <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.category}>{article.category}</Text>
        <Text className={styles.title}>{article.title}</Text>
        <Text className={styles.subtitle}>{article.subtitle}</Text>
      </View>

      <View className={styles.section}>
        {article.sections?.map((section) => (
          <View key={section.heading} className={styles.articleSection}>
            <Text className={styles.sectionHeading}>{section.heading}</Text>
            <Text className={styles.paragraph}>{section.body}</Text>
            {section.bullets?.length ? (
              <View className={styles.bulletList}>
                {section.bullets.map((bullet) => (
                  <View key={bullet} className={styles.bulletRow}>
                    <Text className={styles.bulletMark}>•</Text>
                    <Text className={styles.bulletText}>{bullet}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            {section.practice ? (
              <View className={styles.practiceCard}>
                <Text className={styles.practiceLabel}>带走练习</Text>
                <Text className={styles.practiceText}>{section.practice}</Text>
              </View>
            ) : null}
          </View>
        ))}
        {article.content?.map((paragraph) => (
          <Text key={paragraph} className={styles.paragraph}>{paragraph}</Text>
        ))}
        <Button className={styles.primaryButton} onClick={startArticlePractice} ariaLabel="带着文章去实战">
          <Text>带着文章去实战</Text>
        </Button>
      </View>
      </View>
    </ScrollView>
  )
}

export default ArticlePage
