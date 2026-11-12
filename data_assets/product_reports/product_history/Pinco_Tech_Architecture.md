# Pinco (CareerPilot) 技术架构设计文档 v0.1

## 1. 系统概览
**目标**：构建一个高可用、低延迟、可扩展的 AI 职场助手平台。
**核心能力**：
*   **多模态交互**：支持文本、语音（未来）、文件（简历）输入。
*   **智能决策**：基于 LLM 的简历诊断、模拟面试、职场问答。
*   **数据驱动**：基于 RAG (检索增强生成) 的职位匹配与话术推荐。

## 2. 技术栈选型 (Tech Stack)

### 2.1 前端 (Client)
*   **移动端 (MVP)**：**微信小程序** (Taro / Uni-app 框架)，覆盖最广的 C 端用户，利用微信生态裂变。
*   **Web 端 (管理后台)**：**React (Next.js)** + **Tailwind CSS**，用于内容运营、数据看板。

### 2.2 后端 (Server)
*   **API 服务**：**Node.js (NestJS)** 或 **Python (FastAPI)**。
    *   *推荐 NestJS*：类型安全 (TypeScript)，适合构建复杂的业务逻辑层。
    *   *Python 服务*：作为独立微服务，专门处理简历解析 (PDFMiner) 和 向量计算。
*   **网关 (Gateway)**：Nginx / Kong，处理鉴权、限流、日志。

### 2.3 数据存储 (Data Layer)
*   **关系型数据库**：**PostgreSQL** (Supabase)。存储用户信息、订单、结构化简历数据。
*   **向量数据库**：**pgvector** (集成在 PG 中) 或 **ChromaDB**。存储职位 JD 向量、话术库嵌入 (Embeddings)。
*   **缓存**：**Redis**。存储会话上下文 (Session Context)、高频热点数据。
*   **对象存储**：**AWS S3** / **阿里云 OSS**。存储用户上传的原始简历文件。

### 2.4 AI 基础设施 (AI Infra)
*   **LLM 模型层**：
    *   **主模型 (推理/对话)**：接入 **DeepSeek-V3 / Qwen-Max** (性价比高，中文能力强) 或 **GPT-4o** (用于复杂逻辑)。
    *   **Embedding 模型**：**bge-m3** (多语言，支持长文本)。
*   **框架**：**LangChain** / **LlamaIndex**，用于构建 RAG 流程和 Agent 编排。
*   **ASR/TTS (语音)**：
    *   *ASR (语音转文字)*：OpenAI Whisper (API) 或 阿里云 Paraformer。
    *   *TTS (文字转语音)*：Edge TTS (免费) 或 11Labs (高质量)。

## 3. 核心模块架构

### 3.1 简历诊断系统 (Resume Doctor)
**流程**：
1.  **Upload**：用户上传 PDF/Word -> 存入 OSS。
2.  **Parse**：Python 服务调用 OCR/Parser 提取文本 -> 清洗 (去除页眉页脚)。
3.  **Analyze**：
    *   Prompt 1 (提取): 将非结构化文本转为 JSON (技能、经历、教育)。
    *   Prompt 2 (诊断): 对比 JD，识别缺失关键词 (Gap Analysis)。
    *   Prompt 3 (优化): 生成 STAR 法则改写建议。
4.  **Response**：返回 JSON 报告前端渲染。

### 3.2 模拟面试引擎 (Mock Interview Engine)
**流程**：
1.  **Context Load**：加载用户简历 + 目标职位 JD。
2.  **Session Init**：初始化面试 Session，加载 System Prompt ("你是一个严厉但专业的面试官...")。
3.  **Turn-taking (多轮对话)**：
    *   用户输入 -> 意图识别 (回答问题 / 提问 / 结束)。
    *   LLM 生成追问 -> 存入 Redis 上下文。
    *   实时评分 (可选)：后台异步分析当前回答质量。
4.  **Feedback**：面试结束 -> 汇总所有对话 -> 生成多维度评估报告。

### 3.3 RAG 知识库 (Knowledge Base)
**数据源**：
*   **职位库**：爬取/清洗的热门职位 JD (产品经理、Java 开发、运营...)。
*   **话术库**：高情商回复模板、面试经典 Q&A。
**流程**：
1.  数据入库 -> Embedding -> 存入 Vector DB。
2.  用户提问 ("怎么回答离职原因？") -> 检索最相似的话术 -> LLM 润色生成。

## 4. 数据库设计概览 (Schema Draft)

### Users (用户表)
*   `id`: UUID
*   `wx_openid`: String
*   `membership_tier`: Enum (Free, Silver, Gold)

### Resumes (简历表)
*   `id`: UUID
*   `user_id`: FK
*   `file_url`: String (OSS)
*   `parsed_content`: JSONB (结构化数据)
*   `diagnosis_report`: JSONB (诊断结果)

### Interviews (面试记录表)
*   `id`: UUID
*   `user_id`: FK
*   `target_job`: String
*   `chat_history`: JSONB (对话日志)
*   `score`: Integer
*   `feedback`: Text

## 5. 开发路线图 (Dev Roadmap)
1.  **Week 1**: 搭建 NestJS + Postgres 基础框架；跑通 LLM API 调用。
2.  **Week 2**: 实现简历解析 Demo (Python 脚本)；完成核心 Prompt 调试。
3.  **Week 3**: 开发小程序前端 (上传 + 聊天界面)；联调简历诊断接口。
4.  **Week 4**: 实现模拟面试逻辑 (文本版)；内测上线。
