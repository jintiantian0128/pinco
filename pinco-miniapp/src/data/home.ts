import { HomeActionItem, ServiceTimelineItem } from '@/types/pinco'

export const homeActions: HomeActionItem[] = [
  {
    id: 'career-planning',
    title: '职业规划',
    subtitle: '先看方向，再拆下一步',
    scenario: 'general',
    prompt: '我想和你一起做职业规划。请先结合你记得的职业背景给我一个初步判断；如果缺关键信息，一次只问我一个问题。我们可以一起梳理长期方向和接下来最现实的一步。',
    tone: 'purple'
  },
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
    title: '求职/职场陪伴',
    subtitle: '受挫、迷茫或工作卡住，都可以先说说',
    scenario: 'emotion',
    prompt: '我在求职或工作中遇到了一件让我难受/卡住的事。请先听我说并理解我的感受，不要马上给一堆建议，也不要默认我现在想行动。你可以先问我更希望你听我说、一起梳理，还是帮我想一个小小的下一步；等我愿意时，再把情绪支持和职业问题接起来。',
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
