# Pinco 开源方案借鉴与适配决策（2026-08-04）

原则：先验证成熟的产品闭环和数据契约，再在微信小程序、国内招聘渠道、中文求职语境下做最小适配。除非许可证和运行条件明确，不直接复制源码。

| 能力 | 参考项目/官方方案 | 许可证与现状 | Pinco 采用内容 | 明确不采用 |
| --- | --- | --- | --- | --- |
| 岗位聚合 | [JobSpy](https://github.com/speedyapply/JobSpy) | MIT；覆盖 LinkedIn、Indeed、Glassdoor、Google 等，Python 3.10+ | 借鉴统一岗位 Schema、来源标识、发布时间与失败降级；后续可作为海外岗位适配器 | 不把搜索摘要或模型生成岗位冒充真实岗位；不默认抓取其未覆盖的国内平台 |
| 面试练习 | [DeepInterview](https://github.com/ngoanpv/DeepInterview) | Apache-2.0；公开说明仍属 early build，真实语音依赖供应商 Key | 借鉴 prep → live → post 三段式、CV+JD 生成计划、逐题自适应追问、练后评分与弱项练习 | 暂不引入 LiveKit、视频头像和实时隐形面试辅助；不复制其 mock 成功状态 |
| 简历解析 | [OpenResume](https://github.com/xitanggg/open-resume) | AGPL-3.0；PDF.js、本地解析、ATS 可读性检查 | 只借鉴“本地优先、结构化字段、ATS 可读性”产品思路；Pinco 后端继续使用 pypdf/python-docx 自研结构化抽取 | 不复制 AGPL 源码进入当前闭源商业代码；不声称模型评分等于 ATS 官方评分 |
| 产品埋点 | [PostHog](https://github.com/PostHog/posthog) | 核心 MIT，`ee` 目录另有许可 | 借鉴 event + properties + distinct_id 的事件模型；首批内测先用 Pinco 自有轻量事件接口，减少 SDK 和隐私面 | 暂不接入自动录屏、全量 autocapture 和额外个人信息采集 |
| 专家预约 | [Cal.diy](https://github.com/calcom/cal.diy) | MIT 社区版；官方明确提示生产自托管需自行保障安全 | 借鉴 availability → hold → confirm → complete/cancel 的状态机、幂等订单号和时段冲突校验 | 不引入整套 Next.js/Prisma/Daily 技术栈；未接微信支付前不把订单标记为已支付 |
| 微信支付 | [微信支付商户官方文档](https://pay.wechatpay.cn/doc/v3/merchant/4012791897) + [wechatpayv3](https://github.com/minibear2021/wechatpayv3) | 官方协议 + MIT 第三方 Python 传输封装；依赖固定为 2.0.2 | 适配 JSAPI 下单、RSA 调起签名、平台公钥验签、AES-GCM 解密、主动查询/关单/退款；Pinco 自己负责服务端定价、金额核对、用户归属、幂等履约和开关 | 不信任客户端支付成功；不把商户私钥打包；不在实付与退款验收前公开售卖 |
| 岗位来源质量 | [Google JobPosting 官方内容政策](https://developers.google.com/search/docs/appearance/structured-data/job-posting) + [Schema.org JobPosting](https://schema.org/JobPosting) | Google 要求单一真实职位、完整描述、招聘主体、地点/远程范围、发布时间，并排除新闻/广告/过期职位；Schema.org 定义标准字段 | 不复制爬虫；将其适配为保守的来源摘要门禁：必须有招聘主体、职位信号和 HTTP(S) 来源，过滤新闻/科普/榜单，只称“带来源候选”并要求打开确认有效期 | 搜索摘要不能证明仍在招聘；不把“URL 可打开”写成“真实在招”，不补写薪资、公司、职责或有效期 |
| 云端数据 | 微信云托管自带 MySQL | 当前环境已自动提供内网地址和账号；无需额外购买 MongoDB 或配置 VPC | 后端使用 MySQL 状态仓库并通过重新部署后的同记录回读；本地仍允许 JSON 便于开发测试 | 不再把容器内 JSON 描述为云端持久化；未完成线上回读时不宣称跨设备/重启可用 |
| 图片文字识别 | [RapidOCR](https://github.com/RapidAI/RapidOCR) + PaddleOCR ONNX 模型 | Apache-2.0 工程代码；官方说明默认中英文、离线部署，small 模型随 wheel 提供 | 使用 ONNX Runtime 在 Pinco 容器内瞬时识别 JPG/PNG；结果先填入输入框由用户审阅，原图不持久化 | 不把图片发送给新增 OCR 云服务；不自动把识别文字发送给对话模型；不声称能理解非文字画面 |

## 首批内测的实现顺序

1. 可信基础：真实模型失败透明、微信身份、微信云托管 MySQL 持久化、录音链路、真实岗位来源和最小事件埋点。
2. 求职闭环：岗位对象、证据库、JD 定制材料、投递状态和下一步行动。
3. 面试前练习：5/10/20/30 分钟模式、逐题追问、结构化报告、历史进步对比。
4. 情感支持底座：支持偏好、事件触发、跟进、危机提示和效果反馈，贯穿对话/进度/学社/练习。
5. 生态与商业化：学社内容转练习，专家审核、可用时段、待支付订单、履约与评价；支付代码先白名单实付/退款验收，再分别开放会员与专家收款。

## 验收规则

- 只通过静态检查或后端接口不算完成；必须通过小程序构建和微信开发者工具的用户路径。
- 依赖云配置的能力必须显示“待配置/不可用”，不能走固定文案或 mock 支付冒充成功。
- 岗位必须携带可打开的来源 URL、来源名称和抓取/发布时间；缺失时不进入“真实岗位”列表。
- 每个关键闭环至少记录开始、成功、失败三类事件，并避免在埋点里写入简历全文、录音或聊天原文。
