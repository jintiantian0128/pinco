import React, { useMemo } from 'react'
import { Text, View } from '@tarojs/components'
import Taro, { useLoad, useShareAppMessage } from '@tarojs/taro'
import styles from './index.module.scss'
import { gardenArticles } from '@/data/articles'
import { usePincoStore } from '@/store/usePincoStore'

const ArticlePage: React.FC = () => {
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
    await Taro.switchTab({ url: '/pages/conversation/index' })
    await seedConversation('garden', prompt, '把文章变成一次练习')
  }

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.category}>{article.category}</Text>
        <Text className={styles.title}>{article.title}</Text>
        <Text className={styles.subtitle}>{article.subtitle}</Text>
      </View>

      <View className={styles.section}>
        {article.content.map((paragraph) => (
          <Text key={paragraph} className={styles.paragraph}>{paragraph}</Text>
        ))}
        <View className={styles.primaryButton} onClick={startArticlePractice}>
          <Text>带着文章去实战</Text>
        </View>
      </View>
    </View>
  )
}

export default ArticlePage
