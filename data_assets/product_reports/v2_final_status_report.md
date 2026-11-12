# Pinco 求职 Agent MVP - 最终状态报告

> 报告日期：2026-04-16  
> 项目路径：`/Users/bytedance/clawd/projects/pinco`  
> 当前版本：v0.5.0

## 一、产品定位

**Pinco（CareerPilot）** 是一个面向 0-5 年职场人的 AI 求职辅导 Agent，核心定位是 **"温柔专业的职场学姐"**。

## 二、当前可用功能

| 功能模块 | 状态 | 说明 |
|---------|------|------|
| 💬 智能聊天 | ✅ 可用 | 支持多轮对话，带 persona 人设 |
| 📄 简历诊断 | ✅ 可用 | 上传 PDF，返回 **四维雷达图** 评分报告 |
| 📝 JD 解读 | ✅ 可用 | 粘贴岗位描述，输出核心要求/面试重点/谈薪建议 |
| 🎤 模拟面试 | ✅ 可用 | 输入目标岗位，AI 扮演面试官逐轮提问 |
| 👨‍🏫 专家预约 | ✅ 可用 | 3 位 mock 专家，支持模拟支付流程 |
| ⚙️ 模型配置 | ✅ 可用 | 支持配置 OpenAI/Anthropic 兼容的 API Key |
| 💾 历史持久化 | ✅ 可用 | 对话记录保存在浏览器 localStorage |

## 三、技术栈

- **前端**：Next.js 14 + React 18 + TypeScript + Tailwind CSS + Recharts
- **后端**：FastAPI + Python 3.9 + Pydantic
- **LLM 接入**：兼容 OpenAI / Anthropic 格式（默认 Kimi `kimi-k2.5`）
- **PDF 解析**：pypdf
- **部署**：Docker（已提供 Dockerfile）

## 四、项目结构（当前主线）

```
projects/pinco/
├── frontend/              # 当前前端主线
│   ├── app/page.tsx       # 主应用入口（单页 App）
│   ├── components/        # Chat、Markdown、Uploader、RadarChart 等
│   └── package.json
├── backend/               # 当前后端主线
│   ├── main.py            # FastAPI 应用（聊天/简历/JD/面试/配置）
│   ├── requirements.txt
│   └── .env.example
├── DEPLOYMENT.md          # 部署与运行指南
├── reports/               # 迭代测试报告
│   ├── v1_round1_test_report.md
│   └── v2_final_status_report.md
└── pinco-app/             # 高价值 UI 原型资产（已部分回收）
```

## 五、运行方式

### 后端
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端
```bash
cd frontend
npx next dev --port 3000
```

然后访问 `http://localhost:3000`

详细部署说明见：`DEPLOYMENT.md`

## 六、当前限制与待解决事项

| 优先级 | 事项 | 说明 |
|--------|------|------|
| P0 | **API Key 待更新** | 测试发现当前提供的 Kimi Key 返回 401 Invalid Authentication。在获取有效 Key 前，产品以 **MOCK 模式** 运行，所有 AI 输出为模拟数据。 |
| P1 | 真实支付未接入 | 专家预约为演示流程，无真实资金流转 |
| P2 | 用户系统未搭建 | 无登录/注册，数据仅保存在浏览器本地 |
| P2 | PDF 扫描件不支持 | 当前仅支持文本型 PDF |

## 七、配置真实 LLM 的方法

### 方式 1：前端配置页面（推荐快速测试）
1. 打开前端页面
2. 点击顶部黄色提示条「配置 API Key」或进入「我的 → 模型配置」
3. 填写 Provider、API Key、Base URL、Model
4. 保存后后端热更新，无需重启

### 方式 2：环境变量（推荐用于部署）
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-your-valid-key
export OPENAI_BASE_URL=https://api.moonshot.cn/v1
export DEFAULT_MODEL=kimi-k2.5
```

## 八、体验测试结论

经过三轮迭代（市场调研 → 设计 → 开发 → 测试 → 迭代），产品已具备以下能力：

1. **完整的核心链路**：从简历诊断 → JD 解读 → 模拟面试 → 专家咨询，形成闭环
2. **可用的移动端 UI**：底部导航 + 卡片式交互 + 雷达图可视化，接近产品级体验
3. **灵活的配置机制**：mock / 真实 LLM 可一键切换，便于演示和正式使用
4. **可本地一键启动**：前后端依赖安装完毕，文档齐全

## 九、建议的下一步

1. **获取有效的 Kimi / 其他大模型 API Key**，切换出 mock 模式，验证真实 LLM 输出质量
2. **基于真实输出调优 Prompt**，特别是简历诊断的 JSON 稳定性
3. **部署到公网**（如 Vercel + 阿里云 ECS），进行小范围用户测试
4. **根据用户反馈迭代**，重点打磨模拟面试的追问逻辑和简历诊断的针对性

---

**总结：Pinco 求职 Agent MVP 已开发完成，当前处于"功能完整、UI 可用、待接入真实 AI"的状态。**
