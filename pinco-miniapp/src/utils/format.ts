export const formatTimeLabel = (value: string) => value

export const buildConversationTitle = (scenario?: string) => {
  switch (scenario) {
    case 'resume':
      return '简历诊断会话'
    case 'interview':
      return '模拟面试会话'
    case 'emotion':
      return '情绪陪伴会话'
    case 'expert':
      return '专家备战会话'
    case 'garden':
      return '知识实战会话'
    case 'jd':
      return 'JD解读会话'
    default:
      return '专属会话'
  }
}
