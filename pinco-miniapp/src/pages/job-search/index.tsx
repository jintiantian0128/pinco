import React, { useEffect, useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import styles from './index.module.scss'
import { searchJobsByPlatform } from '@/services/pinco'
import { JobSearchResult, JobPlatform } from '@/types/pinco'
import { usePincoStore } from '@/store/usePincoStore'
import { apiRequest } from '@/services/api'

const PLATFORM_TABS: Array<{ label: string; value: JobPlatform | 'all'; icon: string }> = [
  { label: '全部', value: 'all', icon: '🔍' },
  { label: '脉脉', value: 'maimai', icon: '💼' },
  { label: '猎聘', value: 'liepin', icon: '🎯' },
]

const CITY_OPTIONS = ['不限', '北京', '上海', '杭州', '深圳', '广州', '成都']

const JobSearchPage: React.FC = () => {
  const [query, setQuery] = useState('')
  const [city, setCity] = useState('不限')
  const [platform, setPlatform] = useState<JobPlatform | 'all'>('all')
  const [results, setResults] = useState<JobSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const userId = usePincoStore((state) => state.userProfile?.user_id)

  const saveJob = async (job: JobSearchResult) => {
    if (!userId || !job.url) return
    try {
      const response = await apiRequest<any>('/api/v1/workspace/jobs', 'POST', {
        user_id: userId,
        title: job.title,
        company: job.company,
        location: job.location,
        source: job.source,
        source_url: job.url,
        jd_text: job.summary,
        status: 'saved',
      })
      Taro.showToast({ title: response.created ? '已保存到岗位工作区' : '这个岗位已保存', icon: 'none' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '保存失败', icon: 'none' })
    }
  }

  useLoad((options) => {
    if (options?.q) {
      setQuery(decodeURIComponent(options.q))
      doSearch(decodeURIComponent(options.q))
    }
  })

  useEffect(() => {
    if (searched && query.trim()) {
      doSearch()
    }
  }, [platform, city])

  const doSearch = async (q?: string) => {
    const keyword = q || query
    if (!keyword.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const platformParam = platform === 'all' ? undefined : platform
      const resp = await searchJobsByPlatform({
        query: keyword,
        city: city === '不限' ? undefined : city,
        platforms: platformParam,
        limit: 30,
      })
      let filtered = resp.jobs
      filtered = filtered.filter((job) => job.verified_source && job.url)
      setResults(filtered)
    } catch (e) {
      console.error('[JobSearch] failed', e)
      Taro.showToast({ title: '搜索失败，请重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const platformLabel = (p?: string) => {
    if (!p) return '网络'
    const map: Record<string, string> = { maimai: '脉脉', liepin: '猎聘', jike: '即刻', official: '公司官网', 'Google Jobs': 'Google Jobs' }
    return map[p] || p
  }

  const platformColor = (p?: string) => {
    if (!p) return '#6B7280'
    const map: Record<string, string> = { maimai: '#FF6B35', liepin: '#4A90D9', jike: '#F5C542', official: '#10B981', 'Google Jobs': '#4285F4' }
    return map[p] || '#6B7280'
  }

  return (
    <View className={styles.page}>
      <View className={styles.searchBar}>
        <Textarea
          className={styles.searchInput}
          value={query}
          onInput={(e) => setQuery(e.detail.value)}
          placeholder="搜索岗位，如：AI产品经理、前端开发..."
          maxlength={100}
          autoHeight
          showConfirmBar={false}
          onConfirm={() => doSearch()}
        />
        <View className={styles.searchButton} onClick={() => doSearch()}>
          <Text>{loading ? '...' : '搜索'}</Text>
        </View>
      </View>

      <View className={styles.filterRow}>
        <ScrollView scrollX className={styles.platformTabs}>
          {PLATFORM_TABS.map((tab) => (
            <View
              key={tab.value}
              className={`${styles.platformTab} ${platform === tab.value ? styles.platformTabActive : ''}`}
              onClick={() => setPlatform(tab.value)}
            >
              <Text>{tab.icon} {tab.label}</Text>
            </View>
          ))}
        </ScrollView>
        <View className={styles.cityFilter}>
          {CITY_OPTIONS.slice(0, 4).map((c) => (
            <View
              key={c}
              className={`${styles.cityChip} ${city === c ? styles.cityChipActive : ''}`}
              onClick={() => setCity(c)}
            >
              <Text>{c}</Text>
            </View>
          ))}
        </View>
      </View>

      <ScrollView className={styles.results} scrollY>
        {loading && (
          <View className={styles.loadingState}>
            <Text className={styles.loadingText}>正在搜索 {platform !== 'all' ? platformLabel(platform) : '全平台'} 岗位...</Text>
          </View>
        )}

        {!loading && searched && results.length === 0 && (
          <View className={styles.emptyState}>
            <Text className={styles.emptyIcon}>🔍</Text>
            <Text className={styles.emptyTitle}>没有找到相关岗位</Text>
            <Text className={styles.emptyDesc}>试试换个关键词或调整筛选条件</Text>
          </View>
        )}

        {!loading && !searched && (
          <View className={styles.emptyState}>
            <Text className={styles.emptyIcon}>💼</Text>
            <Text className={styles.emptyTitle}>搜索你感兴趣的岗位</Text>
            <Text className={styles.emptyDesc}>仅展示带可打开来源链接的脉脉、猎聘等公开岗位</Text>
            <View className={styles.hotTags}>
              {['AI产品经理', '前端开发', '数据分析', '运营', 'Java后端'].map((tag) => (
                <View key={tag} className={styles.hotTag} onClick={() => { setQuery(tag); doSearch(tag) }}>
                  <Text>{tag}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {results.map((job, idx) => (
          <View key={idx} className={styles.jobCard}>
            <View className={styles.jobHeader}>
              <Text className={styles.jobTitle}>{job.title}</Text>
              {job.salary && <Text className={styles.jobSalary}>{job.salary}</Text>}
            </View>
            <View className={styles.jobMeta}>
              <Text className={styles.jobCompany}>{job.company} · {job.location}</Text>
              <View className={styles.platformBadge} style={{ backgroundColor: platformColor(job.platform) + '1A', borderColor: platformColor(job.platform) }}>
                <Text className={styles.platformBadgeText} style={{ color: platformColor(job.platform) }}>{platformLabel(job.platform)}</Text>
              </View>
            </View>
            <Text className={styles.jobSummary}>{job.summary}</Text>
            <View className={styles.jobFooter}>
              <Text className={styles.jobSource}>来源: {job.source}</Text>
              {job.verified_source && <Text className={styles.jobSource}> · 已校验来源链接</Text>}
              <View className={styles.jobFooterActions}>
                <View className={styles.linkButton} onClick={() => saveJob(job)}>
                  <Text className={styles.linkButtonText}>保存岗位</Text>
                </View>
                <View className={styles.linkButton} onClick={() => {
                  if (!job.url) return
                  Taro.setClipboardData({ data: job.url })
                  Taro.showToast({ title: '已复制', icon: 'success' })
                }}>
                  <Text className={styles.linkButtonText}>复制链接</Text>
                </View>
                {job.url && (
                  <View className={styles.linkButton} onClick={() => {
                    Taro.navigateTo({ url: '/pages/webview/index?url=' + encodeURIComponent(job.url!) })
                  }}>
                    <Text className={styles.linkButtonText}>查看详情</Text>
                  </View>
                )}
                <View className={styles.jdButton} onClick={() => {
                  const jdContent = `${job.title} - ${job.company}\n地点: ${job.location}\n${job.summary}`
                  Taro.navigateTo({
                    url: '/pages/conversation/index?scenario=jd&jd_text=' + encodeURIComponent(jdContent)
                  })
                }}>
                  <Text className={styles.jdButtonText}>解读JD</Text>
                </View>
              </View>
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  )
}

export default JobSearchPage
