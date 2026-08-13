import { GardenArticle } from '@/types/pinco'

const staticGardenArticles: GardenArticle[] = [
  {
    id: 'g1',
    category: '面试通关',
    title: 'AI面试必背八股文',
    subtitle: '不要背简历，用「标签+亮点+期待」结构自我介绍。准备好3个能讲15分钟的项目故事。',
    highlight: '准备3个能讲15分钟的项目故事，面试时不要背简历，要讲清标签、亮点和期待。',
    reads: 'Pinco 编辑方法卡',
    content: [
      '一、自我介绍框架：不要背简历，用「标签+亮点+期待」结构。',
      '高频问题：项目亮点深挖、失败经历、职业规划。每类都提前准备1分钟版和5分钟版。',
      '反问环节：问团队挑战、岗位半年内KPI、理想候选人特质。'
    ]
  },
  {
    id: 'g2',
    category: '面试通关',
    title: '宝洁八大问解析',
    subtitle: 'STAR 拆解 + 核心技巧，每个故事准备「1分钟版」和「5分钟版」。',
    highlight: '每个故事都用 STAR 法则讲清楚：情境、任务、行动、结果。',
    reads: 'Pinco 编辑方法卡',
    content: [
      '宝洁八大问不是背题，而是准备可迁移的故事库。',
      '每个故事准备「1分钟版」和「5分钟版」，并提前写好逐字稿练习。',
      '用数字说话：用户增长300% 比「增长很多」更可信。'
    ]
  },
  {
    id: 'g3',
    category: '职场防坑',
    title: '新人入职第一周生存指南',
    subtitle: 'Day 1 观察不表现，Day 2-3 建立信任，Day 4-5 第一次交付超预期。',
    highlight: '第一周最重要的不是表现聪明，而是建立信任和交付稳定性。',
    reads: 'Pinco 编辑方法卡',
    content: [
      'Day 1：观察，不表现。记住同事名字和角色，先理解协作关系。',
      'Day 2-3：建立信任。主动问清楚工作产出给谁看、以什么形式看。',
      'Day 4-5：第一次交付。哪怕任务很小，也要超预期完成。'
    ]
  },
  {
    id: 'g4',
    category: '职场防坑',
    title: '反内耗：把面试当带薪调研',
    subtitle: '面试 = 带薪调研。每次面试至少问3个问题，面挂了也要写面试日记。',
    highlight: '每次挂面都不是人格否定，而是市场在给你反馈。',
    reads: 'Pinco 编辑方法卡',
    content: [
      '错误心态：面试 = 被审判。正确心态：面试 = 带薪调研。',
      '每次面试至少问3个问题：你在收集信息，不是被拷问。',
      '面挂了也要复盘：记录问到了什么、你卡在哪、下次怎么答。'
    ]
  },
  {
    id: 'g5',
    category: '简历包装',
    title: 'STAR法则实战手册',
    subtitle: 'STAR 万能公式：情境一句话、任务要量化、行动不超过3点、结果用数字。',
    highlight: '行动不超过3点，结果尽量用数字，避免流水账。',
    reads: 'Pinco 编辑方法卡',
    content: [
      'S 情境：一句话交代背景，不要啰嗦。',
      'T 任务：目标要量化，别只写「提高用户活跃」。',
      'A 行动：分1、2、3点说明关键动作。',
      'R 结果：用数字说话，如果没有数字，用前后对比。'
    ]
  }
]

// Only ship cards reviewed and maintained in this file. The earlier generated
// knowledge dump mixed inferred content with source descriptions and is not
// suitable to present as verified editorial material.
export const gardenArticles: GardenArticle[] = staticGardenArticles
