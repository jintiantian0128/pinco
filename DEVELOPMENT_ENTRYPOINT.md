# Pinco Development Entrypoint

更新时间：2026-08-13

## 唯一产品主线

- 微信小程序：`pinco-miniapp/`
- API 与云托管：`backend/`
- PMF 实施状态：`docs/PMF_IMPLEMENTATION_STATUS_2026-08-05.md`
- 开源借鉴决策：`docs/OPEN_SOURCE_ADOPTION_2026-08-04.md`
- 旧资产迁移审计：`docs/LEGACY_ASSET_MIGRATION_2026-08-13.md`
- 部署手册：`backend/DEPLOY_CLOUDRUN.md`

`frontend/`、`pinco-app/` 和其他 demo/patch 目录均为历史资产，不再作为当前上线版本开发。新增功能、修复和验收只能落在 `pinco-miniapp/ + backend/`。

## 本地验证

```bash
cd backend
python3 main.py

cd ../pinco-miniapp
npm run build:weapp
node critical-flows.test.mjs
```

后端可信性回归：

```bash
cd backend
PYTHONPYCACHEPREFIX=/tmp/pinco-pycache python3 -m unittest -v test_trust_foundation.py
```

构建通过不等于产品通过。上线前还必须在微信开发者工具和真机完成会话、复制、录音、文件、学社、面试、情绪回访、专家流程的用户路径验收。
