import React, { useMemo, useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useShareAppMessage } from '@tarojs/taro'
import styles from './index.module.scss'
import { usePageAnalytics } from '@/hooks/usePageAnalytics'
import { gardenArticles } from '@/data/articles'

const HubPage: React.FC = () => {
  usePageAnalytics('hub')
  const [searchQuery, setSearchQuery] = useState('')

  useShareAppMessage(() => ({
    title: 'Pinco学姐精选：AI 求职与职业成长干货',
    path: '/pages/hub/index',
  }))

  const articles = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return gardenArticles
    return gardenArticles.filter((article) =>
      [article.title, article.subtitle, article.category, article.content.join(' ')]
        .join(' ')
        .toLowerCase()
        .includes(query)
    )
  }, [searchQuery])

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

  return (
    <View className={styles.page}>
      <View className={styles.header}>
        <View>
          <Text className={styles.title}>学社</Text>
          <Text className={styles.desc}>Pinco学姐精选干货 · {gardenArticles.length} 篇</Text>
        </View>
      </View>

      <View className={styles.searchBar}>
        <Text className={styles.searchIcon}>🔍</Text>
        <Textarea
          className={styles.searchInput}
          value={searchQuery}
          onInput={(event) => setSearchQuery(event.detail.value)}
          placeholder="搜索精选文章..."
          maxlength={50}
          autoHeight
          showConfirmBar={false}
        />
        {!!searchQuery && (
          <View className={styles.searchClear} onClick={() => setSearchQuery('')}>
            <Text>✕</Text>
          </View>
        )}
      </View>

      <Text className={styles.sectionTitle}>精选干货</Text>
      {articles.length > 0 ? articles.map((article) => (
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
              <Text className={styles.articleType}>📚 Pinco学姐</Text>
              <Text className={styles.articleCategory}>{article.category}</Text>
              <Text className={styles.articleReads}>精选干货</Text>
            </View>
            <Text className={styles.articleTitle}>{article.title}</Text>
            <Text className={styles.articleSubtitle}>{article.subtitle}</Text>
          </View>
        </View>
      )) : (
        <View className={styles.emptyState}>
          <Text>没有找到相关文章，试试其他关键词。</Text>
        </View>
      )}
    </View>
  )
}

export default HubPage
