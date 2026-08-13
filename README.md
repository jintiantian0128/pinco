# Pinco

Pinco 是面向 0–5 年 AI 求职者的微信小程序求职 Agent：既提供简历、JD、岗位、面试练习和专家服务，也在拒信、等待和临场压力中提供可控、尊重隐私的情绪支持。

当前唯一上线主线：

- `pinco-miniapp/`：Taro 微信小程序
- `backend/`：FastAPI + DeepSeek-compatible LLM + 微信云托管 MySQL + 阿里云 ASR

先阅读：

1. `DEVELOPMENT_ENTRYPOINT.md`
2. `STATUS.md`
3. `docs/PMF_IMPLEMENTATION_STATUS_2026-08-05.md`
4. `docs/OPEN_SOURCE_ADOPTION_2026-08-04.md`
5. `backend/DEPLOY_CLOUDRUN.md`
6. `docs/LEGACY_ASSET_MIGRATION_2026-08-13.md`
7. `docs/DEPENDENCY_SECURITY_2026-08-13.md`

可信原则：没有来源链接的岗位不称为真实岗位；模型失败不返回固定诊断；未审核专家不展示；支付只以微信服务端验签、金额核对后的结果为准；自动化构建不替代微信开发者工具、实付退款和真机验收。

## GitHub 主线范围

GitHub `main` 只发布当前可运行主线和必要文档。2025 年旧职位搜索原型保存在 `legacy/job-search-2025` 分支；其中仅岗位同义词和稳定的面试能力维度经过审计后适配到 `backend/career_taxonomy.py`。过期招聘 JSON、第三方内容抓取、固定模拟岗位和无法核验的公司面试断言不进入生产。

发布前运行 `scripts/prepare_github_release.sh <空目录>` 生成白名单副本。脚本不会复制 `.env`、用户状态、简历、录音、日志、压缩包、依赖缓存或微信开发者工具私有配置。
