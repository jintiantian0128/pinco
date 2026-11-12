# Pinco Project Agent Guide

这份文件说明 AI 编码助手和新加入的开发者如何在 Pinco 仓库中安全、可验证地开展工作。若本文件与代码、锁文件或当前部署工作流不一致，以代码和自动化工作流为准，并及时更新本文。

## 项目概览

Pinco 是面向 0–5 年职场人的全生命周期 Career Agent，覆盖职业方向、简历与求职材料、岗位探索、面试练习、Offer/入职适应，以及求职过程中的情绪支持。产品原则是“专业、有判断、有人味”：先提供可用价值，再在必要时澄清；尊重隐私；不把模型猜测当成用户事实；服务失败时明确说明，不用固定模板假装模型回答。

当前唯一线上产品主线：

- `pinco-miniapp/`：Taro + React + TypeScript 微信小程序。
- `backend/`：FastAPI 服务，直接调用 DeepSeek Chat Completions；使用微信云托管 MySQL 保存生产状态。ASR、OCR 等能力按后端配置运行。
- `data_assets/`：知识原稿、历史岗位数据与产品报告的迁移归档，不是程序运行依赖，不要把它当作在线职位库或用户可见内容。

历史目录（例如 `frontend/`、`pinco-app/`、`legacy/`、`archive/`、`_workspace/`、`pinco/`、`pinco-server/`）不是当前线上小程序/后端主线。除非任务明确涉及历史资产迁移，不要在这些目录开发当前产品功能，也不要从中复制未经核验的旧实现。

## 改动前必读

按任务范围阅读，不必一次性加载所有资料：

1. `README.md` 与 `DEVELOPMENT_ENTRYPOINT.md`：仓库主线、开发入口与快速验证。
2. `STATUS.md`：项目状态记录；它可能滞后，需与当前代码、线上状态交叉核对。
3. `backend/DEPLOY_CLOUDRUN.md`：云托管环境、部署与验收边界。
4. `docs/` 中与所改模块对应的产品决策、迁移与安全文档。
5. 修改页面时阅读对应 `pinco-miniapp/src/pages/<page>/`、服务层与 store；修改 API 时阅读 `backend/main.py`、`backend/state_store.py` 及对应测试。

先检查 `git status`、当前分支和最近提交。工作区中可能存在用户的未跟踪旧资产或本地配置；不要清理、覆盖、批量格式化或顺手加入提交。

## 分层架构与边界

```text
pinco-miniapp/src/pages/       页面与交互
pinco-miniapp/src/services/    API、Pinco 会话与埋点服务
pinco-miniapp/src/store/       客户端会话和界面状态
pinco-miniapp/src/types/       前端共享类型
backend/main.py                FastAPI 路由、业务编排与外部服务
backend/state_store.py         文件/MySQL/MongoDB 状态存储适配
backend/career_taxonomy.py     岗位分类、同义词及面试维度
backend/expert_knowledge.py    专家知识上下文
backend/community_seed.py      学社初始化精选内容
backend/test_*.py              后端回归测试
pinco-miniapp/critical-flows.test.mjs  小程序关键流程静态/结构检查
data_assets/                   非运行时的迁移资料
```

约束：

- 小程序请求经 `src/services/api.ts` 等现有服务层进入后端；不要在页面散落重复的 URL、认证或错误处理逻辑。
- 职业 Memory 是用户长期信息；任务执行状态是当前任务进度，二者不可混为一份状态。事实、假设、待澄清项和用户拒答要区分。
- 求职材料必须以用户证据为边界；不能编造经历、指标、公司数据或岗位信息。岗位被称为“真实”前必须有可核验来源。
- 生产服务是无状态容器；生产数据必须经持久化状态层，不能依赖容器本地文件。未配置或持久化失败时采取失败关闭策略。
- 微信支付默认关闭；不能仅凭客户端结果声称支付/退款成功。未审核的专家不可公开展示；用户内容开关和小程序服务类目/备案要求需保持一致。
- DeepSeek 调用失败要返回可识别错误，不得切换到固定答案或假装已生成。密钥只在本地忽略文件或云托管密钥中配置，禁止进入 Git、前端包、日志、URL 或报告。
- `data_assets/` 中的岗位快照是研究资料，不代表实时招聘；原稿版权、个人信息和使用授权需在对外复用前核对。

## 常用命令

### 后端

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8090 --reload
```

运行完整后端测试：

```bash
python3 -m unittest discover -s backend -p 'test_*.py'
```

### 微信小程序

```bash
cd pinco-miniapp
npm ci
node critical-flows.test.mjs
npm run build:weapp
```

微信开发者工具应打开项目根目录 `pinco-miniapp/`，该项目配置的 `miniprogramRoot` 是 `dist/`。不要把 `dist/` 当作独立源代码项目打开；它是构建输出。构建通过不代表页面交互或真机验收通过。

## 开发与验证流程

1. 确认当前分支、工作区和任务相关代码；保留不属于本任务的修改。
2. 按改动范围建立独立任务分支，尽量保持变更聚焦；不擅自把历史目录、缓存、`.env`、个人数据或构建产物加入 Git。
3. 同步实现与测试。涉及用户路径、错误状态或数据模型时，补充相应自动化回归。
4. 执行相关测试；提交前至少运行小程序关键流程检查和生产构建。后端有变更时运行完整后端测试。
5. 对外报告时区分“自动化检查”“线上接口检查”“微信开发者工具页面点击测试”“真机测试”，不把其中一种冒充另一种。任何测试未能实际完成，都写明阻塞点与未覆盖部分。
6. 按用户要求的发布流程操作。合并到 `main`、推送或部署属于发布动作，须遵循当前对话中用户给出的确认规则；不要把“代码已合并”表述成“微信版本已审核/发布”。

## 发布与环境

- GitHub 仓库：`https://github.com/jintiantian0128/pinco`（私有仓库）。
- 当前后端部署目标：微信云托管服务 `flask-jk7n`；环境变量与云托管密钥不能从仓库推断或输出。
- `.github/workflows/verify-cloudbase-deploy.yml`：当前自动化工作流。它在 `main` 上涉及 `backend/**` 或该 workflow 文件的 push 时运行验证，并在验证后尝试部署后端、检查公开 readiness 与用户旅程。修改只涉及小程序时，该路径触发规则本身不会自动触发此后端部署工作流。
- 小程序构建/体验版上传和微信审核是不同步骤。CI 或本地构建不会自动代表已上传、已提交审核或已获审核通过；每一步都要以开发者工具/平台回执为准。
- 云托管公开检查优先看 `/health` 和 `/ready`。上线应核对 `release_sha`，以及真实模型、持久化状态等 readiness 项，而不只看容器启动成功。
- 手动部署步骤、需要的变量和验收边界以 `backend/DEPLOY_CLOUDRUN.md` 为准。禁止将真实凭证写入本文件。

## 完成定义

一个功能只有在代码与对应自动化检查完成后，才能称为“开发完成”；只有实际运行相应微信开发者工具用户路径后，才能称为“页面实测通过”；只有发布平台给出成功回执后，才能称为“已上传/已提审”；只有微信审核平台确认后，才能称为“审核通过”。报告结果时同时列出未验证边界。
