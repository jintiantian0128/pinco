# Pinco 求职 Agent MVP - 第一轮体验测试报告

> 测试时间：2026-04-15
> 测试范围：frontend/ + backend/ 主线联调
> 测试模式：MOCK（无真实 LLM Key）

## 一、已验证功能

### 1. 前端页面
- [x] 首页聊天界面正常渲染（欢迎语 + 快速功能入口）
- [x] 底部导航切换（首页 / 专家 / 我的）
- [x] 专家列表展示（3 位 mock 专家）
- [x] 我的页面展示（会员状态 + 菜单入口）
- [x] 支付弹窗流程（模拟微信支付/支付宝）
- [x] JD 解读弹窗（输入 JD 后调用后端）
- [x] 模拟面试弹窗（输入岗位后调用后端）

### 2. 后端接口
- [x] `GET /health` - 返回正常，mock_mode=true
- [x] `POST /api/v1/chat` - 返回 mock 回复，中文自然
- [x] `POST /api/v1/resume/upload` - PDF 解析成功，返回四维评分报告
- [x] `POST /api/v1/jd/analyze` - 返回结构化 JD 解读
- [x] `POST /api/v1/interview/start` - 返回面试开场题 + 考察重点
- [x] `GET/POST /api/v1/config` - 模型配置接口已就绪

### 3. 端到端联调
- [x] 前端 `localhost:3000` 可访问
- [x] 前端成功调用后端 `localhost:8000` 接口
- [x] CORS 无问题

## 二、发现的问题

| 优先级 | 问题 | 影响 | 建议处理 |
|--------|------|------|----------|
| P0 | 缺少模型配置页面 | 用户无法自行配置 API Key，产品无法脱离 mock | 第二轮必须加 |
| P1 | 简历诊断无雷达图 | 可视化反馈缺失，不如 pinco-app 惊艳 | 回收 DiagnosisReportCard |
| P1 | 简历上传无拖拽进度 | 体验不如 pinco-app 的 ResumeUploader | 回收 ResumeUploader |
| P2 | 无 mock 模式提示 | 用户可能误以为 AI 能力是真实的 | 加全局提示条 |
| P2 | 对话历史不持久 | 刷新后聊天记录丢失 | localStorage 持久化 |
| P3 | 专家预约无真实支付 | 当前为演示流程 | MVP 阶段可接受 |

## 三、下一轮迭代重点

### 第二轮目标（Day 1 晚间 ~ Day 2）
1. **模型配置页面**：支持选择 provider、填写 API Key、Base URL、Model，对接后端 `/api/v1/config`
2. **回收可视化组件**：ResumeUploader（拖拽 + 进度）+ DiagnosisReportCard（雷达图）
3. **全局 Mock 提示条**：在 mock 模式下顶部显示"当前为演示模式，请配置模型 API Key"
4. **对话历史持久化**：使用 localStorage 保存聊天记录
5. **UI 细节优化**：输入框高度自适应、消息卡片间距微调

### 第三轮目标（Day 2 ~ Day 3）
1. 接入真实 LLM 测试（用户提供有效 Key 后）
2. Prompt 调优，让简历诊断和面试问题更精准
3. Bug 修复和边缘场景处理
4. 输出部署文档，确保产品可对外演示

## 四、结论

**第一轮迭代结果：前后端主线已成功跑通，核心功能链路（聊天、简历诊断、JD 解读、模拟面试、专家预约）均可正常使用。**

当前产品已进入"可用但为演示模式"的状态，第二轮重点是补齐配置能力和回收高价值 UI 组件，使产品在视觉和功能上都达到可直接对外演示的标准。
