# 小程序依赖安全基线

审计日期：2026-08-13。

## 已处理

- Taro `4.1.9` 的 `@tarojs/taro-loader` 要求 Webpack `5.91.0`，原项目固定为 `5.78.0`；已对齐到 `5.91.0`。
- `babel-preset-taro@4.1.9` 要求 `react-refresh ^0.14.0`，原项目使用 `^0.11.0`；已对齐到 `^0.14.0`。
- 重新生成 `package-lock.json`，并从无 `node_modules` 的目录执行 `npm ci` 成功。
- 执行了不带 `--force` 的 `npm audit fix --package-lock-only`；没有接受 npm 建议的 Taro 3.x 降级或其他破坏性主版本变更。

## 尚存风险

非破坏性修复后，`npm audit` 仍报告 86 项传递依赖告警；`npm audit --omit=dev` 报告 21 项（14 moderate、1 high、6 critical）。主要路径来自 Taro 组件/H5 依赖、`miniprogram-ci` 和历史构建工具链。告警数量不等于这些路径已在微信小程序运行包中可被利用，但也不能据此宣称“零漏洞”。

## 后续处理

1. 在独立分支把全部 Taro 包从 `4.1.9` 升到当前稳定版，并完成干净安装、生产构建、微信开发者工具、iOS 和 Android 回归。
2. 移除不再支持的支付宝、抖音、H5 构建目标及其插件，缩小依赖面。
3. 单独评估 `miniprogram-ci`；仅在受控 CI 中处理可信源码和构建产物，不向其输入第三方压缩包或不可信 Babel 源码。
4. 每次依赖升级记录 `npm audit` 前后差异；禁止为追求数字归零直接运行 `npm audit fix --force`。
