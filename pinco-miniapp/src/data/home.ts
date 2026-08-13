import { HomeActionItem, ServiceTimelineItem } from '@/types/pinco'

export const homeActions: HomeActionItem[] = [
  {
    id: 'resume',
    title: '简历诊断',
    subtitle: '先找到最容易丢分的地方',
    scenario: 'resume',
    prompt: '我想做一轮简历诊断，请先问我最关键的背景信息。',
    tone: 'purple'
  },
  {
    id: 'interview',
    title: '模拟面试',
    subtitle: '从第一题开始热身',
    scenario: 'interview',
    prompt: '帮我开始一轮 AI 产品经理模拟面试，从自我介绍开始。',
    tone: 'orange'
  },
  {
    id: 'emotion',
    title: '情绪陪伴',
    subtitle: '不内耗，先把状态扶起来',
    scenario: 'emotion',
    prompt: '我最近在求职里有点内耗，你先接住我的情绪，再给我两个今天能做的动作。',
    tone: 'pink'
  },
  {
    id: 'jd',
    title: 'JD解读',
    subtitle: '把岗位要求拆成备战清单',
    scenario: 'jd',
    prompt: '请帮我解读这段岗位描述，提取核心要求、面试重点和谈薪建议。',
    tone: 'emerald'
  },
  {
    id: 'expert',
    title: '专家备战',
    subtitle: '连线前先把问题准备好',
    scenario: 'expert',
    prompt: '请帮我生成一份专家连线前的 15 分钟备战清单。',
    tone: 'emerald'
  }
]

export const defaultTimeline: ServiceTimelineItem[] = [
  {
    id: 'timeline-1',
    title: '先把问题说清',
    desc: '进入会话，学姐先帮你判断优先级',
    status: 'active'
  },
  {
    id: 'timeline-2',
    title: '再做一次诊断',
    desc: '从简历或面试里抓一个最短板的问题先突破',
    status: 'pending'
  },
  {
    id: 'timeline-3',
    title: '必要时约专家',
    desc: '复杂问题再用 1v1 连线加速',
    status: 'pending'
  }
]
