# GitHub → 微信云托管部署验证

## 当前结论

- 云托管内置“代码库拉取”支持 GitHub，但需要在新建版本时选择仓库和分支；不能据此假定每次 `main` push 都会自动部署。
- 真正的 push 自动部署使用 GitHub Actions 检出代码，再调用微信官方 `@wxcloud/cli`。
- `main` 的 `backend/**` 或本工作流发生变更时已经自动触发；仍保留 `workflow_dispatch` 供受控重跑。两种入口使用同一套测试、版本指纹、用户旅程和回滚门禁。
- 2026-08-13 运行 `31712741669` 的干净环境预检、CLI 登录、环境发现、基线、回滚版本和 dry-run 均通过，云托管也确认创建了 `flask-jk7n-023`。之后官方 CLI 因构建日志主题返回 `ResourceNotFound.TopicNotExist` 而错误退出，但云端异步构建继续完成，公网随后实际切到健康的 v0.7.0。此前工作流把这次成功提交误判为失败；修订版不再把日志轮询结果当作上线结果。
- 修订版会把 GitHub commit SHA 写入容器，公网 `/health.release_sha` 必须与本次 Actions 的 SHA 完全一致。只有精确提交、DeepSeek 和 MySQL 同时健康才算成功；版本号相同但仍是旧容器不会被放行。
- 运行 `31720393869` 曾把提交 `73466cf` 成功部署并通过精确版本健康检查，但真实 Agent 旅程发现回答使用了职业记忆、模型却漏报 `used_memory_keys`。流水线因此正确失败，且因新版本本身健康而没有错误回滚；这证明功能门禁不会把“容器已上线”误写成“产品已通过”。
- 2026-08-14 自动触发运行 [`31773770914`](https://github.com/jintiantian0128/pinco/actions/runs/31773770914) 已整链路绿色通过：验证作业、云托管发布、精确提交健康检查、三轮账号闭环、三轮真实 Agent 记忆/历史恢复和三轮容器内 OCR 全部成功，未触发回滚。公网 `/health.release_sha` 为 `c203c9f4dff8117342de30935580124d1a8cecca`，DeepSeek `connected`，MySQL `durable=true/online=true`。

## GitHub Actions Secrets

在仓库 `Settings → Secrets and variables → Actions` 配置：

- `WXCLOUD_APP_ID`：微信云托管 CLI 密钥对应的 AppID。
- `WXCLOUD_PRIVATE_KEY`：在微信云托管 `设置 → CLI 密钥` 新建后获得的私钥；不要提交到代码或粘贴到聊天中。

环境 ID 不再要求人工配置。CLI 登录后，工作流会遍历当前 AppID 的环境并要求只能找到一个包含 `flask-jk7n` 的环境；找不到或匹配多个都会失败关闭，不会猜测目标环境。

CLI 密钥需要账号管理员扫码创建。密钥生成后平台不会再次明文展示，应存入 GitHub Actions Secret 后妥善离线保管。

## 首次验证

1. 打开 GitHub 仓库 `Actions → Verify CloudBase deployment → Run workflow`。
2. 输入 `deploy`，手动触发。
3. 独立验证作业先在 GitHub 干净环境运行完整后端测试、前端关键流程检查、微信小程序生产构建和后端 Docker 镜像构建；全部通过后，部署作业才执行密钥校验、CLI 登录、自动定位唯一环境、生产基线检查、记录回滚版本、dry-run、正式部署和公网健康检查。
4. CLI 确认“版本创建成功”后，即使后续日志轮询异常，工作流仍会等待公网结果；CLI 日志轮询最多等待 12 分钟。先要求 `/health` 返回 HTTP 200、`version=0.7.0`、`release_sha` 等于本次 GitHub SHA，且 DeepSeek/MySQL 同时在线，再连续三轮执行一次性账号闭环、三轮真实 Agent 职业记忆/重进历史恢复和三轮本地 OCR 识别。测试账号都会自动注销和清理。
5. 若部署、健康检查或任一公网用户旅程失败，流水线会在需要时回滚到部署前版本，并确认公网恢复到原有健康版本；工作流仍保持失败状态，不能把“成功回滚”当成“成功部署”。如果自动恢复也失败，应立即在云托管控制台人工切回已知健康版本，不要反复重跑。
6. 生产基线和新版本验收都允许有限次数重试，以容纳云托管异步构建与冷启动；每次仍同时要求应用在线、DeepSeek 在线和 MySQL 持久化在线，持续异常不会被放行。

## 自动触发范围

```yaml
push:
  branches: [main]
  paths:
    - backend/**
    - .github/workflows/verify-cloudbase-deploy.yml
```

文档和纯小程序页面改动不会单独部署后端。自动化仍不替代微信开发者工具、iOS/Android、录音权限和支付实付退款验收。
