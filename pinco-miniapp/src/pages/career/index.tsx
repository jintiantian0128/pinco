import React, { useEffect, useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { usePullDownRefresh } from '@tarojs/taro'
import { apiRequest } from '@/services/api'
import { usePincoStore } from '@/store/usePincoStore'
import { CareerWorkspace, WorkspaceJob } from '@/types/pinco'
import styles from './index.module.scss'

const emptyWorkspace: CareerWorkspace = {
  career_profile: { target_roles: [], years_experience: 0, cities: [], strengths: [] },
  evidence: [],
  jobs: [],
  interview_sessions: [],
  resume_analyses: [],
  capability_radar: { dimensions: [], disclaimer: '' },
}

const jobStatuses = [
  ['saved', '已收藏'], ['applied', '已投递'], ['written', '笔试'], ['interview1', '一面'],
  ['interview2', '二面'], ['hr', 'HR面'], ['offer', 'Offer'], ['rejected', '未通过'],
] as const

const interviewDimensionLabels: Record<string, string> = {
  content: '内容', structure: '结构', evidence: '证据', role_fit: '岗位匹配', clarity: '表达清晰', adaptability: '临场应变',
}

const CareerPage: React.FC = () => {
  const userId = usePincoStore((state) => state.userProfile?.user_id)
  const [workspace, setWorkspace] = useState<CareerWorkspace>(emptyWorkspace)
  const [loading, setLoading] = useState(false)
  const [targetRoles, setTargetRoles] = useState('')
  const [years, setYears] = useState('0')
  const [cities, setCities] = useState('')
  const [strengths, setStrengths] = useState('')
  const [jobSearchDeadline, setJobSearchDeadline] = useState('')
  const [evidenceTitle, setEvidenceTitle] = useState('')
  const [evidenceSituation, setEvidenceSituation] = useState('')
  const [evidenceAction, setEvidenceAction] = useState('')
  const [evidenceResult, setEvidenceResult] = useState('')
  const [evidenceMetrics, setEvidenceMetrics] = useState('')
  const [evidenceSkills, setEvidenceSkills] = useState('')
  const [jobCompany, setJobCompany] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [jobJd, setJobJd] = useState('')
  const [generatingJobId, setGeneratingJobId] = useState('')
  const [editingJobId, setEditingJobId] = useState('')
  const [editBullets, setEditBullets] = useState('')
  const [editOutreach, setEditOutreach] = useState('')

  const splitItems = (value: string) => value.split(/[，,、\n]/).map((item) => item.trim()).filter(Boolean)

  const loadWorkspace = async () => {
    if (!userId) return
    setLoading(true)
    try {
      const data = await apiRequest<CareerWorkspace>(`/api/v1/workspace?user_id=${encodeURIComponent(userId)}`)
      setWorkspace(data)
      setTargetRoles(data.career_profile.target_roles.join('、'))
      setYears(String(data.career_profile.years_experience || 0))
      setCities(data.career_profile.cities.join('、'))
      setStrengths(data.career_profile.strengths.join('、'))
      setJobSearchDeadline(data.career_profile.job_search_deadline || '')
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '加载失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadWorkspace() }, [userId])
  usePullDownRefresh(() => loadWorkspace().finally(() => Taro.stopPullDownRefresh()))

  const saveProfile = async () => {
    if (!userId) return
    try {
      const response = await apiRequest<any>('/api/v1/workspace/profile', 'POST', {
        user_id: userId,
        target_roles: splitItems(targetRoles),
        years_experience: Number(years) || 0,
        cities: splitItems(cities),
        strengths: splitItems(strengths),
        job_search_deadline: jobSearchDeadline.trim(),
      })
      setWorkspace((current) => ({ ...current, career_profile: response.career_profile }))
      Taro.showToast({ title: '目标画像已保存', icon: 'success' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '保存失败', icon: 'none' })
    }
  }

  const addEvidence = async () => {
    if (!userId) return
    try {
      const response = await apiRequest<any>('/api/v1/workspace/evidence', 'POST', {
        user_id: userId,
        title: evidenceTitle,
        situation: evidenceSituation,
        action: evidenceAction,
        result: evidenceResult,
        metrics: evidenceMetrics,
        skills: splitItems(evidenceSkills),
      })
      setWorkspace((current) => ({ ...current, evidence: [response.evidence, ...current.evidence] }))
      setEvidenceTitle(''); setEvidenceSituation(''); setEvidenceAction(''); setEvidenceResult(''); setEvidenceMetrics(''); setEvidenceSkills('')
      Taro.showToast({ title: '真实证据已保存', icon: 'success' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '请补全证据', icon: 'none' })
    }
  }

  const addJob = async () => {
    if (!userId) return
    try {
      const response = await apiRequest<any>('/api/v1/workspace/jobs', 'POST', {
        user_id: userId,
        company: jobCompany,
        title: jobTitle,
        jd_text: jobJd,
        source: 'manual',
        status: 'saved',
      })
      setWorkspace((current) => ({ ...current, jobs: [response.job, ...current.jobs.filter((job) => job.id !== response.job.id)] }))
      setJobCompany(''); setJobTitle(''); setJobJd('')
      Taro.showToast({ title: '岗位已加入工作区', icon: 'success' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '保存岗位失败', icon: 'none' })
    }
  }

  const generateMaterials = async (job: WorkspaceJob) => {
    if (!userId || generatingJobId) return
    setGeneratingJobId(job.id)
    try {
      const response = await apiRequest<any>(`/api/v1/workspace/jobs/${job.id}/materials`, 'POST', {
        user_id: userId,
        evidence_ids: workspace.evidence.map((item) => item.id),
      })
      setWorkspace((current) => ({
        ...current,
        jobs: current.jobs.map((item) => item.id === job.id ? { ...item, materials: response.materials } : item),
      }))
      Taro.showToast({ title: '定制材料已生成', icon: 'success' })
    } catch (error: any) {
      Taro.showModal({ title: '没有生成材料', content: error?.message || '请确认已填写完整 JD 和真实证据', showCancel: false })
    } finally {
      setGeneratingJobId('')
    }
  }

  const updateJobStatus = async (job: WorkspaceJob, status: string) => {
    if (!userId) return
    try {
      const response = await apiRequest<any>(`/api/v1/workspace/jobs/${job.id}/status`, 'POST', {
        user_id: userId,
        status,
      })
      setWorkspace((current) => ({
        ...current,
        jobs: current.jobs.map((item) => item.id === job.id ? response.job : item),
      }))
      if (response.support_action) {
        const action = response.support_action
        const result = await Taro.showModal({
          title: action.title,
          content: action.message,
          confirmText: action.action_label,
          cancelText: '先不用',
        })
        if (result.confirm) {
          Taro.navigateTo({ url: `/pages/conversation/index?scenario=emotion&prompt=${encodeURIComponent(action.prompt)}` })
        }
      } else {
        Taro.showToast({ title: '进度已同步云端', icon: 'none' })
      }
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '更新进度失败', icon: 'none' })
    }
  }

  const beginEditMaterials = (job: WorkspaceJob) => {
    setEditingJobId(job.id)
    setEditBullets((job.materials?.resume_bullets || []).join('\n'))
    setEditOutreach(job.materials?.outreach_message || '')
  }

  const saveMaterials = async (job: WorkspaceJob) => {
    if (!userId) return
    try {
      const response = await apiRequest<any>(`/api/v1/workspace/jobs/${job.id}/materials`, 'PUT', {
        user_id: userId,
        resume_bullets: editBullets.split('\n').map((item) => item.trim()).filter(Boolean),
        outreach_message: editOutreach.trim(),
      })
      setWorkspace((current) => ({
        ...current,
        jobs: current.jobs.map((item) => item.id === job.id ? { ...item, materials: response.materials } : item),
      }))
      setEditingJobId('')
      Taro.showToast({ title: '修改已保存到云端', icon: 'success' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '保存失败', icon: 'none' })
    }
  }

  const copyMaterials = async (job: WorkspaceJob) => {
    const materials = job.materials || {}
    const text = [
      `${job.company} · ${job.title}`,
      materials.match_summary ? `匹配判断：${materials.match_summary}` : '',
      ...(materials.resume_bullets || []).map((item: string) => `• ${item}`),
      materials.outreach_message ? `投递话术：${materials.outreach_message}` : '',
      (materials.gaps || []).length ? `待补证据：${materials.gaps.join('、')}` : '',
    ].filter(Boolean).join('\n')
    try {
      await Taro.setClipboardData({ data: text })
      const verified = await Taro.getClipboardData()
      if (verified.data !== text) throw new Error('CLIPBOARD_VERIFY_FAILED')
      Taro.showToast({ title: '岗位材料已复制', icon: 'success' })
    } catch (error) {
      console.error('[Career] copy materials failed', error)
      Taro.showToast({ title: '复制失败，请稍后重试', icon: 'none' })
    }
  }

  const submitMaterialFeedback = async (job: WorkspaceJob, rating: 'direct_use' | 'minor_edit' | 'major_rework' | 'fabricated') => {
    if (!userId) return
    const labels = { direct_use: '可直接用', minor_edit: '小改可用', major_rework: '需要重做', fabricated: '发现疑似编造' }
    try {
      const response = await apiRequest<any>(`/api/v1/workspace/jobs/${job.id}/materials/feedback`, 'POST', {
        user_id: userId,
        rating,
      })
      setWorkspace((current) => ({
        ...current,
        jobs: current.jobs.map((item) => item.id === job.id ? {
          ...item,
          materials: { ...item.materials, user_feedback: response.feedback },
        } : item),
      }))
      Taro.showToast({ title: `已记录：${labels[rating]}`, icon: 'none' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '反馈保存失败', icon: 'none' })
    }
  }

  const practiceAgain = (position: string, job?: WorkspaceJob) => {
    const params = [
      'scenario=interview',
      'duration=10',
      `position=${encodeURIComponent(position)}`,
      job?.id ? `job_id=${encodeURIComponent(job.id)}` : '',
      job?.company ? `company=${encodeURIComponent(job.company)}` : '',
    ].filter(Boolean).join('&')
    Taro.navigateTo({ url: `/pages/conversation/index?${params}` })
  }

  const toggleLearningDay = async (day: number, completed: boolean) => {
    if (!userId || !workspace.learning_plan) return
    try {
      const response = await apiRequest<any>('/api/v1/workspace/learning-plan/progress', 'POST', {
        user_id: userId,
        plan_id: workspace.learning_plan.id,
        day,
        completed,
      })
      setWorkspace((current) => ({ ...current, learning_plan: response.learning_plan }))
      Taro.showToast({ title: completed ? '已记录今天的推进' : '已取消完成', icon: 'none' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '计划状态保存失败，请刷新重试', icon: 'none' })
    }
  }

  const publishInterviewReport = async (session: any) => {
    if (!userId || session.community_post_id) return
    const confirmed = await Taro.showModal({
      title: '匿名发布练习复盘？',
      content: '只发布结构化分数、做得好的、优先改进和下一次练习；不会公开你的原始回答、姓名或会话全文。',
      confirmText: '匿名发布',
      cancelText: '先不发',
    })
    if (!confirmed.confirm) return
    try {
      const response = await apiRequest<any>(`/api/v1/interview/practice/${session.id}/publish`, 'POST', { user_id: userId })
      setWorkspace((current) => ({
        ...current,
        interview_sessions: current.interview_sessions.map((item) => item.id === session.id ? {
          ...item,
          community_post_id: response.post.id,
        } : item),
      }))
      Taro.showToast({ title: response.created ? '匿名复盘已发布' : '这条复盘已经发布过', icon: 'none' })
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '发布失败，报告仍保留', icon: 'none' })
    }
  }

  const completedSessions = workspace.interview_sessions.filter((item) => item.status === 'completed' && item.report)
  const latestScore = Number(completedSessions[0]?.report?.overall_score || 0)
  const previousScore = Number(completedSessions[1]?.report?.overall_score || 0)

  return (
    <ScrollView className={styles.page} scrollY>
      <View className={styles.hero}>
        <Text className={styles.heroTitle}>求职证据库</Text>
        <Text className={styles.heroDesc}>先存真实事实，再让 AI 为不同 JD 重组表达。没有证据的内容会标成缺口，不会替你编经历。</Text>
      </View>

      <View className={styles.card}>
        <Text className={styles.title}>目标画像</Text>
        <Textarea className={styles.input} value={targetRoles} onInput={(e) => setTargetRoles(e.detail.value)} placeholder="目标岗位，用逗号分隔" autoHeight />
        <Textarea className={styles.input} value={years} onInput={(e) => setYears(e.detail.value)} placeholder="工作年限，如 2.5" autoHeight />
        <Textarea className={styles.input} value={cities} onInput={(e) => setCities(e.detail.value)} placeholder="目标城市" autoHeight />
        <Textarea className={styles.input} value={strengths} onInput={(e) => setStrengths(e.detail.value)} placeholder="已验证的优势/技能" autoHeight />
        <Textarea className={styles.input} value={jobSearchDeadline} onInput={(e) => setJobSearchDeadline(e.detail.value)} placeholder="希望多久进入下一轮/拿到 Offer，例如：30 天内" maxlength={40} autoHeight />
        <View className={styles.button} onClick={saveProfile}><Text>保存目标画像</Text></View>
      </View>

      <View className={styles.card}>
        <Text className={styles.title}>AI 岗能力雷达</Text>
        <Text className={styles.desc}>{workspace.capability_radar?.disclaimer || '完成真实证据、简历诊断和面试练习后逐步形成。'}</Text>
        {workspace.capability_radar?.target_track && <Text className={styles.itemText}>当前目标方向：{workspace.capability_radar.target_track}</Text>}
        {workspace.capability_radar?.next_gap && <Text className={styles.itemText}>下一证据缺口：{workspace.capability_radar.next_gap.label} · {workspace.capability_radar.next_gap.score}分{workspace.capability_radar.next_gap.suggestion ? ` · ${workspace.capability_radar.next_gap.suggestion}` : ''}</Text>}
        {(workspace.capability_radar?.dimensions || []).map((dimension) => (
          <View key={dimension.key} className={styles.item}>
            <Text className={styles.itemTitle}>{dimension.label} · {dimension.score}</Text>
            <Text className={styles.itemText}>数据来源：{dimension.source}</Text>
          </View>
        ))}
      </View>

      {workspace.learning_plan && (
        <View className={styles.card}>
          <Text className={styles.title}>本周 7 天证据补缺</Text>
          <Text className={styles.desc}>{workspace.learning_plan.disclaimer}</Text>
          <Text className={styles.itemTitle}>目标：补强“{workspace.learning_plan.focus_dimension.label}” · 已完成 {workspace.learning_plan.completed_count}/7</Text>
          <Text className={styles.itemText}>本周产出：{workspace.learning_plan.target_output}</Text>
          <Text className={styles.itemText}>下一批岗位策略：{workspace.learning_plan.next_batch_strategy}</Text>
          {workspace.learning_plan.days.map((item) => (
            <View key={item.day} className={styles.item}>
              <Text className={styles.itemTitle}>第 {item.day} 天 · {item.title}</Text>
              <Text className={styles.itemText}>{item.action}</Text>
              <Text className={styles.itemText}>应留下：{item.evidence_output}</Text>
              <View className={`${styles.secondaryButton} ${item.completed ? styles.statusChipActive : ''}`} onClick={() => toggleLearningDay(item.day, !item.completed)}>
                <Text>{item.completed ? '✓ 已完成，点击撤销' : '完成后点这里记录'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <View className={styles.card}>
        <Text className={styles.title}>添加一条真实证据</Text>
        <Text className={styles.desc}>用简化 STAR 记录，结果不知道数字可以留空，不能猜。</Text>
        <Textarea className={styles.input} value={evidenceTitle} onInput={(e) => setEvidenceTitle(e.detail.value)} placeholder="证据标题：例如独立推动推荐页改版" autoHeight />
        <Textarea className={styles.input} value={evidenceSituation} onInput={(e) => setEvidenceSituation(e.detail.value)} placeholder="当时背景/目标" autoHeight />
        <Textarea className={styles.input} value={evidenceAction} onInput={(e) => setEvidenceAction(e.detail.value)} placeholder="你具体做了什么（必填）" autoHeight />
        <Textarea className={styles.input} value={evidenceResult} onInput={(e) => setEvidenceResult(e.detail.value)} placeholder="结果/影响（必填）" autoHeight />
        <Textarea className={styles.input} value={evidenceMetrics} onInput={(e) => setEvidenceMetrics(e.detail.value)} placeholder="可验证数字或证据链接（可空）" autoHeight />
        <Textarea className={styles.input} value={evidenceSkills} onInput={(e) => setEvidenceSkills(e.detail.value)} placeholder="体现的技能" autoHeight />
        <View className={styles.button} onClick={addEvidence}><Text>保存真实证据</Text></View>
        {workspace.evidence.map((item) => (
          <View key={item.id} className={styles.item}>
            <Text className={styles.itemTitle}>{item.title}</Text>
            <Text className={styles.itemText}>行动：{item.action}</Text>
            <Text className={styles.itemText}>结果：{item.result}{item.metrics ? ` · ${item.metrics}` : ''}</Text>
          </View>
        ))}
      </View>

      <View className={styles.card}>
        <Text className={styles.title}>简历诊断记录</Text>
        <Text className={styles.desc}>只保存诊断结构，不保存上传文件原文。模型调用失败时不会生成记录或固定分数。</Text>
        {workspace.resume_analyses.length === 0 && <Text className={styles.itemText}>还没有成功的简历诊断。</Text>}
        {workspace.resume_analyses.map((analysis) => (
          <View key={analysis.id} className={styles.item}>
            <Text className={styles.itemTitle}>{analysis.filename} · {analysis.score}分</Text>
            <Text className={styles.itemText}>{analysis.summary}</Text>
            <Text className={styles.itemText}>优先改进：{(analysis.weaknesses || []).join('、')}</Text>
          </View>
        ))}
      </View>

      <View className={styles.card}>
        <Text className={styles.title}>岗位与定制材料</Text>
        <Textarea className={styles.input} value={jobCompany} onInput={(e) => setJobCompany(e.detail.value)} placeholder="公司" autoHeight />
        <Textarea className={styles.input} value={jobTitle} onInput={(e) => setJobTitle(e.detail.value)} placeholder="岗位" autoHeight />
        <Textarea className={styles.input} value={jobJd} onInput={(e) => setJobJd(e.detail.value)} placeholder="粘贴完整 JD" maxlength={10000} autoHeight />
        <View className={styles.button} onClick={addJob}><Text>加入岗位工作区</Text></View>
        {workspace.jobs.map((job) => (
          <View key={job.id} className={styles.item}>
            <Text className={styles.itemTitle}>{job.company} · {job.title}</Text>
            <Text className={styles.itemText}>状态：{job.status} · 来源：{job.source}</Text>
            {job.source_url && <Text className={styles.itemText}>原始链接已保存 · 检索时间：{job.source_checked_at || job.created_at}（不保证岗位仍在招聘，请投递前打开确认）</Text>}
            <ScrollView className={styles.statusScroller} scrollX>
              <View className={styles.statusRow}>
                {jobStatuses.map(([status, label]) => (
                  <View key={status} className={`${styles.statusChip} ${job.status === status ? styles.statusChipActive : ''}`} onClick={() => updateJobStatus(job, status)}><Text>{label}</Text></View>
                ))}
              </View>
            </ScrollView>
            <View className={styles.secondaryButton} onClick={() => generateMaterials(job)}><Text>{generatingJobId === job.id ? '生成中...' : '用证据生成定制材料'}</Text></View>
            <View className={styles.secondaryButton} onClick={() => practiceAgain(job.title, job)}><Text>围绕这个岗位练10分钟</Text></View>
            {job.materials?.match_summary && <Text className={styles.materialText}>匹配判断：{job.materials.match_summary}</Text>}
            {job.materials?.fit_decision && <Text className={styles.itemTitle}>投递建议：{job.materials.fit_decision === 'GO' ? '建议投递' : job.materials.fit_decision === 'MAYBE' ? '补关键证据后再投' : '暂不建议投递'}</Text>}
            {(job.materials?.fit_reasons || []).map((reason: string, index: number) => <Text key={`fit-${index}`} className={styles.materialText}>判断依据：{reason}</Text>)}
            {(job.materials?.resume_bullets || []).map((bullet: string, index: number) => <Text key={index} className={styles.materialText}>• {bullet}</Text>)}
            {job.materials?.outreach_message && <Text className={styles.materialText}>投递话术：{job.materials.outreach_message}</Text>}
            {(job.materials?.gaps || []).length > 0 && <Text className={styles.materialText}>待补证据：{job.materials.gaps.join('、')}</Text>}
            {job.materials?.match_summary && editingJobId !== job.id && (
              <View className={styles.statusRow}>
                <View className={styles.secondaryButton} onClick={() => beginEditMaterials(job)}><Text>审阅并修改</Text></View>
                <View className={styles.secondaryButton} onClick={() => copyMaterials(job)}><Text>复制导出</Text></View>
              </View>
            )}
            {job.materials?.generated_at && (
              <View className={styles.item}>
                <Text className={styles.itemText}>这份材料对你真实有多大帮助？反馈会进入 PMF 质量与编造护栏，不影响你的内容。</Text>
                <View className={styles.statusRow}>
                  {([
                    ['direct_use', '可直接用'], ['minor_edit', '小改可用'], ['major_rework', '需要重做'], ['fabricated', '疑似编造'],
                  ] as const).map(([rating, label]) => (
                    <View key={rating} className={`${styles.statusChip} ${job.materials?.user_feedback?.rating === rating ? styles.statusChipActive : ''}`} onClick={() => submitMaterialFeedback(job, rating)}><Text>{label}</Text></View>
                  ))}
                </View>
              </View>
            )}
            {editingJobId === job.id && (
              <View className={styles.item}>
                <Text className={styles.itemText}>每行一条简历要点。请删除任何你无法证明的内容。</Text>
                <Textarea className={styles.input} value={editBullets} onInput={(e) => setEditBullets(e.detail.value)} maxlength={4000} autoHeight />
                <Textarea className={styles.input} value={editOutreach} onInput={(e) => setEditOutreach(e.detail.value)} maxlength={1000} autoHeight />
                <View className={styles.button} onClick={() => saveMaterials(job)}><Text>保存修改</Text></View>
                <View className={styles.secondaryButton} onClick={() => setEditingJobId('')}><Text>取消</Text></View>
              </View>
            )}
          </View>
        ))}
      </View>

      <View className={styles.card}>
        <Text className={styles.title}>面试练习进步</Text>
        <Text className={styles.desc}>每次练习都来自真实模型评分。分数只用于纵向比较自己的表达，不代表真实录用概率。</Text>
        {completedSessions.length >= 2 && (
          <View className={styles.scoreSummary}>
            <Text className={styles.scoreValue}>{latestScore}</Text>
            <Text className={styles.scoreDelta}>{latestScore >= previousScore ? '+' : ''}{latestScore - previousScore} 较上次</Text>
          </View>
        )}
        {completedSessions.length === 0 && <Text className={styles.itemText}>还没有完成的练习报告。可从会话页选择 5/10/20/30 分钟开始。</Text>}
        {completedSessions.map((session) => (
          <View key={session.id} className={styles.item}>
            <Text className={styles.itemTitle}>{session.position} · {session.duration_minutes}分钟 · {session.report.overall_score}分</Text>
            {session.company && <Text className={styles.itemText}>{session.company}{session.interview_round ? ` · ${session.interview_round}` : ''}{session.interview_date ? ` · ${session.interview_date}` : ''}</Text>}
            {session.mode && <Text className={styles.itemText}>模式：{session.mode} · 题目来源：{(session.question_sources || []).join('、')}</Text>}
            {session.report.dimension_scores && <Text className={styles.itemText}>六维：{Object.entries(session.report.dimension_scores).map(([key, value]) => `${interviewDimensionLabels[key] || key} ${value}`).join(' · ')}</Text>}
            <Text className={styles.itemText}>做得好：{(session.report.strengths || []).join('、') || '报告未提供'}</Text>
            <Text className={styles.itemText}>下一步：{session.report.next_drill || (session.report.improvements || []).join('、')}</Text>
            <View className={styles.secondaryButton} onClick={() => practiceAgain(session.position, workspace.jobs.find((job) => job.id === session.job_id))}><Text>再练10分钟</Text></View>
            <View className={styles.secondaryButton} onClick={() => publishInterviewReport(session)}><Text>{session.community_post_id ? '✓ 已匿名发布到学社' : '匿名发布结构化复盘'}</Text></View>
          </View>
        ))}
      </View>
      <Text className={styles.footer}>{loading ? '正在同步云端工作区...' : '岗位、证据和材料会随你的微信用户态同步'}</Text>
    </ScrollView>
  )
}

export default CareerPage
