export default {
  pages: [
    'pages/conversation/index',
    'pages/home/index',
    'pages/hub/index',
    'pages/experts/index',
    'pages/mine/index',
    'pages/article/index',
    'pages/garden/index',
    'pages/circle/index',
    'pages/job-search/index',
    'pages/career/index',
    'pages/expert-center/index',
    'pages/membership/index',
    'pages/webview/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    backgroundColor: '#FAFAFA',
    navigationBarBackgroundColor: '#FAFAFA',
    navigationBarTitleText: 'Pinco AI职场学姐',
    navigationBarTextStyle: 'black'
  },
  tabBar: {
    color: '#9CA3AF',
    selectedColor: '#EC4899',
    backgroundColor: '#FFFFFF',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/conversation/index', text: '会话', iconPath: 'assets/tabbar/chat.png', selectedIconPath: 'assets/tabbar/chat_active.png' },
      { pagePath: 'pages/hub/index', text: '学社', iconPath: 'assets/tabbar/hub.png', selectedIconPath: 'assets/tabbar/hub_active.png' },
      { pagePath: 'pages/experts/index', text: '专家', iconPath: 'assets/tabbar/expert.png', selectedIconPath: 'assets/tabbar/expert_active.png' },
      { pagePath: 'pages/mine/index', text: '我的', iconPath: 'assets/tabbar/mine.png', selectedIconPath: 'assets/tabbar/mine_active.png' }
    ]
  },
  // 隐私信息类型在微信公众平台的「用户隐私保护指引」中声明。
  // app.json 的 permission 不支持剪贴板和录音，写入反而会触发 invalid permission 警告。
  __usePrivacyCheck__: true
}
