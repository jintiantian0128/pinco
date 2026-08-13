# GitHub → 微信云托管部署验证

## 当前结论

- 云托管内置“代码库拉取”支持 GitHub，但需要在新建版本时选择仓库和分支；不能据此假定每次 `main` push 都会自动部署。
- 真正的 push 自动部署使用 GitHub Actions 检出代码，再调用微信官方 `@wxcloud/cli`。
- 首次验证只提供 `workflow_dispatch` 手动触发。只有部署和公网版本验收通过后，才增加 `main` push 触发，避免未验证流水线直接覆盖生产。

## GitHub Actions Secrets

在仓库 `Settings → Secrets and variables → Actions` 配置：

- `WXCLOUD_APP_ID`：微信云托管 CLI 密钥对应的 AppID。
- `WXCLOUD_PRIVATE_KEY`：在微信云托管 `设置 → CLI 密钥` 新建后获得的私钥；不要提交到代码或粘贴到聊天中。
- `WXCLOUD_ENV_ID`：`flask-jk7n` 所在云托管环境 ID，不是环境显示名称。

CLI 密钥需要账号管理员扫码创建。密钥生成后平台不会再次明文展示，应存入 GitHub Actions Secret 后妥善离线保管。

## 首次验证

1. 打开 GitHub 仓库 `Actions → Verify CloudBase deployment → Run workflow`。
2. 输入 `deploy`，手动触发。
3. 流水线依次执行密钥校验、CLI 登录、生产基线检查、记录回滚版本、dry-run、正式部署和公网健康检查。
4. 只有公网 `/health` 返回 HTTP 200 且 `version` 为 `0.7.0` 才会通过。
5. 若部署或健康检查失败，流水线会在需要时回滚到部署前版本，并确认公网恢复到原有健康版本；工作流仍保持失败状态，不能把“成功回滚”当成“成功部署”。如果自动恢复也失败，应立即在云托管控制台人工切回已知健康版本，不要反复重跑。

## 开启自动触发的前置条件

- 手动工作流至少连续通过一次。
- DeepSeek、MySQL、微信身份、管理员令牌和 ASR 环境变量在新版本中仍可见。
- 微信开发者工具真实对话通过，iOS/Android 真机验收仍应独立进行。
- 明确回滚版本和流量切换方式。

满足后再给工作流增加：

```yaml
push:
  branches: [main]
  paths:
    - backend/**
    - .github/workflows/verify-cloudbase-deploy.yml
```
