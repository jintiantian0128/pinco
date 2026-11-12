# Pinco MVP 开发路线图

## 📅 Phase 1: 地基搭建 (Day 1-3)
- [ ] **项目初始化**: Git 仓库, Next.js 脚手架, 环境变量配置
- [ ] **技术选型**: 确认 LLM 模型供应商 (DeepSeek/Gemini/OpenAI) 和 数据库方案
- [ ] **基础设施**: 配置 CI/CD, 部署环境 (Vercel/Zeabur/Docker)

## 📅 Phase 2: 核心功能 - "Pinco" 对话 (Day 4-7)
- [ ] **人设系统 (Prompt Engineering)**: 打造 "温柔学姐" 的 System Prompt，包含语气、回复策略、拒绝策略
- [ ] **聊天界面 (UI)**: 实现类似 ChatGPT/Feishu 的对话窗口，支持流式输出 (Streaming)
- [ ] **记忆系统**: 实现简单的短期记忆 (Session Context)，让 Pinco 记住用户的名字和基本情况

## 📅 Phase 3: 核心功能 - 简历诊所 (Day 8-14)
- [ ] **文件上传**: 支持 PDF/Word 简历上传
- [ ] **简历解析 (Parser)**: 提取文本内容
- [ ] **AI 评分引擎**: 对照 JD (职位描述) 进行打分，输出 "优化建议" 和 "改写案例"

## 📅 Phase 4: 上线准备 (Day 15+)
- [ ] **Landing Page**: 宣传单页 (Slogan, Waitlist)
- [ ] **用户系统**: 简单的登录/注册 (Clerk/Auth.js)
- [ ] **Alpha 测试**: 邀请第一批种子用户 (校园大使)
