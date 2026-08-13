import React from 'react'
import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import styles from './index.module.scss'
import { gardenArticles } from '@/data/articles'

const GardenPage: React.FC = () => {
  const categories = Array.from(new Set(gardenArticles.map((item) => item.category)))

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <Text className={styles.title}>知识花园</Text>
        <Text className={styles.desc}>把求职知识变成可执行动作。先读一篇，再回会话页做实战拆解。</Text>
      </View>

      <ScrollView className={styles.categoryScroll} scrollX enhanced showScrollbar={false}>
        {categories.map((category) => (
          <View key={category} className={styles.categoryChip}>
            <Text>{category}</Text>
          </View>
        ))}
      </ScrollView>

      {gardenArticles.map((article) => (
        <View
          key={article.id}
          className={styles.articleCard}
          onClick={() => Taro.navigateTo({ url: `/pages/article/index?id=${article.id}` })}
        >
          <View className={styles.articleMeta}>
            <Text className={styles.articleCategory}>{article.category}</Text>
            <Text className={styles.articleReads}>{article.reads}</Text>
          </View>
          <Text className={styles.articleTitle}>{article.title}</Text>
          <Text className={styles.articleSubtitle}>{article.subtitle}</Text>
          <View className={styles.highlight}>
            <Text>{article.highlight}</Text>
          </View>
        </View>
      ))}
    </View>
  )
}

export default GardenPage
