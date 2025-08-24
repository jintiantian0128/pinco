# 小红书AI产品经理MCP服务器

## 📖 项目介绍

小红书AI产品经理MCP服务器是一个基于Model Context Protocol (MCP)的工具，用于实时获取小红书上关于AI产品经理求职相关的内容。该服务器可以帮助AI模型获取最新的行业动态、求职经验、技能要求等信息。

## 🚀 功能特性

### 核心功能
- 🔍 **智能搜索**：搜索小红书上的AI产品经理相关内容
- 📈 **热门内容**：获取当前热门的AI产品经理求职话题
- 🕒 **实时更新**：获取最近几小时的最新内容
- 📊 **趋势分析**：提供技能、薪资、职业发展、面试经验等多维度分析

### 工具列表
1. `search_xiaohongshu_content` - 搜索特定关键词的内容
2. `get_trending_ai_pm_content` - 获取热门AI产品经理内容
3. `get_recent_ai_pm_content` - 获取最近的AI产品经理内容
4. `get_ai_pm_insights` - 获取AI产品经理求职见解

## 🛠️ 安装和使用

### 环境要求
- Python 3.7+
- requests库

### 安装依赖
```bash
pip install requests
```

### 基本使用

#### 1. 查看可用工具
```bash
python xiaohongshu_mcp.py tools
```

#### 2. 搜索AI产品经理内容
```bash
python xiaohongshu_mcp.py call search_xiaohongshu_content '{"query": "AI产品经理面试", "limit": 10}'
```

#### 3. 获取热门内容
```bash
python xiaohongshu_mcp.py call get_trending_ai_pm_content '{"limit": 10}'
```

#### 4. 获取最近内容
```bash
python xiaohongshu_mcp.py call get_recent_ai_pm_content '{"hours": 24, "limit": 20}'
```

#### 5. 获取求职见解
```bash
python xiaohongshu_mcp.py call get_ai_pm_insights '{"analysis_type": "skills", "limit": 10}'
```

### Python API使用

```python
from xiaohongshu_mcp_example import XiaohongshuMCPClient

client = XiaohongshuMCPClient()

# 搜索内容
result = client.search_content("AI产品经理技能", 10)

# 获取热门内容
trending = client.get_trending_content(5)

# 获取最近内容
recent = client.get_recent_content(12, 10)

# 获取技能分析
skills = client.get_insights("skills", 8)
```

## 📊 数据分析功能

### 技能分析
分析AI产品经理需要掌握的核心技能，包括：
- Python编程
- 机器学习/深度学习
- 数据分析能力
- 产品设计思维
- 用户研究方法
- 项目管理能力

### 薪资分析
统计不同薪资范围的AI产品经理职位讨论：
- 15-20k/月
- 20-30k/月
- 30-50k/月
- 50k+/月

### 职业发展分析
分析AI产品经理的职业发展路径：
- 入门阶段
- 初级产品经理
- 中级产品经理
- 高级产品经理
- 资深产品经理
- 产品总监

### 面试经验分析
收集AI产品经理的面试经验和技巧：
- 面试题类型
- 面试官关注点
- 常见问题解答
- Offer获取经验

## 🔧 技术实现

### 架构设计
```
┌─────────────────┐
│   MCP Server    │
│                 │
│  ┌────────────┐ │
│  │  Tools     │ │
│  │            │ │
│  │ • Search   │ │
│  │ • Trending │ │
│  │ • Recent   │ │
│  │ • Insights │ │
│  └────────────┘ │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Scraper Engine │
│                 │
│  ┌────────────┐ │
│  │  Content   │ │
│  │  Analysis  │ │
│  │  Caching   │ │
│  │  Updates   │ │
│  └────────────┘ │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│   Xiaohongshu   │
│     API/Site    │
└─────────────────┘
```

### 核心组件

#### 1. XiaohongshuScraper
- 负责与小红书平台的交互
- 实现内容搜索和数据解析
- 处理反爬虫机制
- 缓存管理

#### 2. XiaohongshuMCP
- 实现MCP协议
- 管理工具定义
- 处理工具调用
- 自动数据更新

#### 3. 内容分析引擎
- 相关性评分算法
- 关键词提取
- 趋势分析
- 数据聚合

## 📈 使用场景

### 1. AI助手集成
将此MCP服务器集成到AI助手中，为用户提供实时的AI产品经理求职信息。

### 2. 求职辅导
为求职者提供最新的行业动态和求职经验分享。

### 3. 市场研究
分析AI产品经理岗位的技能要求和薪资水平。

### 4. 内容创作
为内容创作者提供AI产品经理领域的热门话题。

## ⚠️ 注意事项

### 1. 法律合规
- 遵守小红书的使用条款
- 尊重内容创作者的版权
- 仅用于学习和研究目的

### 2. 数据限制
- 内容获取可能受到小红书API限制
- 部分内容可能需要登录才能访问
- 数据实时性取决于网络状况

### 3. 使用限制
- 请勿用于商业用途
- 避免高频请求
- 尊重平台规则

## 🔄 更新计划

### 短期计划
- [ ] 支持更多小红书内容类型
- [ ] 增加内容过滤和质量评估
- [ ] 优化缓存策略
- [ ] 添加错误重试机制

### 长期计划
- [ ] 支持多平台内容聚合
- [ ] 增加AI分析和摘要功能
- [ ] 构建用户画像分析
- [ ] 提供个性化推荐

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进这个项目！

### 开发环境
1. Fork本仓库
2. 创建特性分支: `git checkout -b feature/new-feature`
3. 提交更改: `git commit -am 'Add new feature'`
4. 推送分支: `git push origin feature/new-feature`
5. 提交Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看[LICENSE](LICENSE)文件了解详情。

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至项目维护者

---

**最后更新**: 2024年12月
**版本**: 1.0.0
