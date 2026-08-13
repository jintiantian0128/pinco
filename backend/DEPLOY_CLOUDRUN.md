# Pinco 后端：微信云托管部署与验收

更新时间：2026-08-13。当前生产服务名为 `flask-jk7n`，公网地址为：

`https://flask-jk7n-277209-9-1430442234.sh.run.tcloudbase.com`

## 1. 上传内容

上传 zip 的根目录必须直接包含：

- `Dockerfile`
- `main.py`
- `state_store.py`
- `career_taxonomy.py`
- `requirements.txt`
- `admin_console.html`

不要上传 `.env`、`data/`、日志、旧 zip 或测试文件。项目的 `.dockerignore` 已排除这些内容。可使用仓库内的 `scripts/package_cloudrun.sh` 生成安全包。

本次应上传：`pinco-backend-upload-20260813-212736-safe.zip`

SHA-256：`9b125835e84a2dc9ea51604f931b763b85db7e76d9205906def90a11199faa4d`

不要沿用旧包名，以免遗漏 `career_taxonomy.py`。

## 2. 必需环境变量

在云托管「服务设置 → 环境变量」中配置：

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=<DeepSeek API Key>
OPENAI_BASE_URL=https://api.deepseek.com
DEFAULT_MODEL=<控制台实际可用的 DeepSeek 模型名>

PINCO_STATE_BACKEND=mysql
MYSQL_ADDRESS=<微信云托管自动提供的内网地址>
MYSQL_USERNAME=<专用数据库账号>
MYSQL_PASSWORD=<专用数据库密码>
MYSQL_DATABASE=pinco
MYSQL_STATE_TABLE=pinco_state

PINCO_ADMIN_TOKEN=<至少32位随机值>
WECHAT_APP_ID=<小程序 AppID>
WECHAT_APP_SECRET=<小程序 AppSecret>

ASR_PROVIDER=aliyun
ALIYUN_NLS_APP_KEY=<阿里云智能语音项目 App Key>
ALIYUN_AK_ID=<最小权限 RAM AccessKey ID>
ALIYUN_AK_SECRET=<最小权限 RAM AccessKey Secret>
ALIYUN_NLS_ENDPOINT=https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr
ENABLE_LOCAL_WHISPER=false
ASR_DEVICE_VERIFIED=false

IMAGE_OCR_PROVIDER=local
IMAGE_OCR_DEVICE_VERIFIED=false
```

云托管是无状态容器。生产环境若仍使用 `PINCO_STATE_BACKEND=file`，重启或扩缩容会丢失用户、帖子、练习报告、专家订单等数据，不能开放首批用户。当前环境已经提供云托管 MySQL，优先使用 `mysql`，无需额外购买 MongoDB 或配置 VPC。程序会自动创建 `pinco` 数据库（账号具备建库权限时）和 `pinco_state` 表；生产环境建议在控制台先建库，再使用只拥有该库读写权限的专用账号，不要长期使用 root。

### 微信支付（先测试，后公开）

支付代码已经实现服务端 JSAPI 下单、小程序签名参数、异步通知验签/解密、金额核对、幂等开通、主动查询、关单，以及未交付专家服务的全额退款。它默认全部关闭，缺少任意凭证都会失败关闭，不能把密钥放进上传 zip。

先在云托管密钥或环境变量中配置：

```text
WECHAT_PAY_ENABLED=false
WECHAT_PAY_LIVE_VERIFIED=false
MEMBERSHIP_SALES_ENABLED=false
EXPERT_PAYMENTS_ENABLED=false
WECHAT_PAY_MCH_ID=<直连商户号>
WECHAT_PAY_CERT_SERIAL_NO=<商户证书序列号>
WECHAT_PAY_PRIVATE_KEY_BASE64=<完整商户私钥 PEM 的 Base64>
WECHAT_PAY_API_V3_KEY=<严格 32 字节 APIv3 密钥>
WECHAT_PAY_PUBLIC_KEY_ID=<微信支付平台 PUB_KEY_ID>
WECHAT_PAY_PUBLIC_KEY_BASE64=<微信支付平台公钥 PEM 的 Base64>
WECHAT_PAY_NOTIFY_URL=https://<公网域名>/api/v1/payments/wechat/notify
WECHAT_PAY_REFUND_NOTIFY_URL=https://<公网域名>/api/v1/payments/wechat/refund-notify
WECHAT_PAY_TEST_USER_IDS=<仅用于验收的 Pinco user_id，多个用逗号分隔>
```

验收顺序：保持两个售卖开关和 `WECHAT_PAY_LIVE_VERIFIED=false`，只填测试用户后设置 `WECHAT_PAY_ENABLED=true`；用该账号完成一笔小额实付，核对异步通知与服务端权益开通，再完成专家订单全额退款并核对退款通知。全部一致后才能设置 `WECHAT_PAY_LIVE_VERIFIED=true`，最后再单独确认是否开启会员或专家售卖。客户端收银台返回成功不能替代服务端确认。

协议依据：[小程序下单](https://pay.wechatpay.cn/doc/v3/merchant/4012791897)、[小程序调起支付](https://pay.wechatpay.cn/doc/v3/merchant/4012791898)、[支付成功通知](https://pay.wechatpay.cn/doc/v3/merchant/4012791902)、[申请退款](https://pay.wechatpay.cn/doc/v3/merchant/4012791903)、[退款结果通知](https://pay.wechatpay.cn/doc/v3/merchant/4012791906)。

## 3. 手动部署

1. 打开微信云托管控制台，进入当前环境和 `flask-jk7n` 服务。
2. 选择「新建版本 / 部署」→「本地上传」。
3. 上传最新安全 zip；目标目录留空，Dockerfile 路径使用包根目录。
4. 确认监听端口由平台注入的 `PORT` 决定，不手填 8090。
5. 保存环境变量后部署新版本，等待构建和健康检查完成。
6. 将流量切到新版本；保留上一版本以便回滚。

### 改用 GitHub 代码库

微信云托管 / CloudBase 支持在新建版本时从授权的代码库拉取并按 Dockerfile 构建。建议把 Pinco 做成独立私有 GitHub 仓库，不要直接推送当前 `/Users/bytedance/clawd` 根仓库；它包含其他工作区内容。

1. 新建私有仓库 `pinco`，将本项目根目录作为仓库根。
2. 云托管新建版本时选「代码库拉取」，授权 GitHub，选定私有仓库、分支和提交。
3. 构建上下文 / 目标目录填 `backend`，Dockerfile 填 `Dockerfile`。若控制台要求从仓库根填路径，则使用 `backend/Dockerfile`。
4. 密钥只放在云托管环境变量；`.env`、证书、日志、状态数据和历史 zip 都不得进入 GitHub。
5. 首次保留「手动触发部署」；等构建和回滚跑通后，再考虑绑定指定分支自动发版。

如果当前微信云托管控制台只显示「本地上传 / 镜像」，不要把 GitHub Actions 直接写成未验证的自动发布。先在 CloudBase 的版本创建页或持续部署流水线中查找「代码库拉取」；仍不可见时，继续用安全 zip，或改为 GitHub Actions 构建镜像、推送到腾讯云镜像仓库后再由云托管选择镜像部署。

## 4. 部署后验收

先检查：

```text
GET /health
GET /api/v1/miniapp/readiness
```

readiness 至少应满足：真实模型在线、`durable_state` 为 ready、微信身份配置完成、ASR 为 ready。只有开发者工具、iOS、Android 各连续三次真实录音通过后，才把 `ASR_DEVICE_VERIFIED` 改为 `true`。微信支付不阻塞免费内测，但未完成商户配置、实付回调和退款验收时必须保持不可购买。

然后必须从微信开发者工具用户页面完成：

1. 进入会话，发送真实问题并收到模型回复。
2. 复制回复后粘贴验证。
3. 点一次开始录音，再点一次结束并识别文字；首次会出现微信隐私和麦克风授权。
4. 上传一份文本型 PDF/DOCX 简历并得到真实模型诊断；模型故障时应明确失败，不能出现固定 50 分。
5. 选择一张含文字图片，确认本地 OCR 把文字填入输入框；核对文字后再主动发送。原图不持久化，模型仍不能读取图片中的非文字画面。
6. 在作战台保存目标、求职期限、真实证据和岗位 JD，生成材料后核对 GO/MAYBE/NO_GO、证据来源并提交一次可用性反馈。
7. 学社发布一条可选绑定岗位的干货，另一账号将内容转为练习；刷新后确认作者贡献只增加一次。
8. 分别检查“陪我热身 / 真实强度 / 压力追问”可选；练习中点击一次救场框架，确认不代答、不跳题，再完成一轮 10 分钟弱项复练，确认后两次围绕同一缺口，页面展示相邻回答与首尾回答的真实分数变化，并在证据库看到历史。
9. 提交专家申请；未经过管理员审核前不能出现在专家市场；预约时可选绑定自己的岗位。
10. 完成本周 7 天证据补缺计划的一天并刷新，确认进度仍保留；完成面试后匿名发布结构化复盘，确认学社不出现姓名、原始回答或会话全文。
11. 在情绪陪伴页选择一次“被理解”程度；24 小时回访时如实选择微行动是否完成，确认管理员指标只统计真实回答。

## 5. 专家审核

部署包含 `admin_console.html` 的版本后，打开：

`https://<公网域名>/admin`

输入 `PINCO_ADMIN_TOKEN` 可处理专家申请、学社举报并查看 PMF 指标。令牌仅保存在当前页面内存，刷新或关闭页面即清除；不要把令牌放在 URL、浏览器书签、截图或小程序代码中。

如需直接调用 API：

管理员接口必须带请求头：

`X-Pinco-Admin-Token: <PINCO_ADMIN_TOKEN>`

使用：

- `GET /api/v1/admin/expert-applications`
- `POST /api/v1/admin/expert-applications/{application_id}/review`
- `GET /api/v1/admin/community/reports`
- `POST /api/v1/admin/community/posts/{post_id}/moderate`
- `GET /api/v1/admin/metrics/pmf`

审核请求 body：

```json
{"decision":"approved","review_note":"已核验公开履历与作品"}
```

专家申请也可使用 `rejected` 或 `changes_requested`。学社帖子审核使用 `published`、`featured` 或 `hidden`；`featured` 会幂等记一笔人工精选贡献。不要把管理员令牌写进小程序。

## 6. 尚未开放或待真实验收的能力

- 微信支付：代码已接入，但当前生产仍未配置商户凭证，也没有完成小额实付、异步回调和退款真机验收；所有开关必须保持关闭，不能宣称支付可用。
- 图片能力：容器内 RapidOCR 只提取中英文文字，识别结果先回填输入框由用户确认，不会自动发给模型；原图不持久化，DeepSeek 文本模型仍不能理解图片中的非文字画面。
- 真机验收：开发者工具通过后仍要在至少一台 iOS 和一台 Android 微信上验证录音、剪贴板和文件选择。
