# 分发与官方市场状态

核对日期：2026-10-02。当前 0.4 Windows 本地插件尚未上传、送审或公开发布。

## 已具备的能力

便携插件包含 plugin.json、mcp.json、skills 和 bin/ScreenEyes.exe。程序使用相对路径，状态使用 PLUGIN_DATA。已完成隔离本地 marketplace 安装和真实原生语音测试。可以通过本地或仓库 marketplace 分享，尚未公开托管仓库。

干净包 screen-eyes-0.4-auto-voice-plugin.zip 包含使用说明与第三方许可，不含代理、状态、会话、截图或诊断资料。双击 使用说明.html，或阅读 使用说明.txt。

## 不能直接按标准公共流程上架的原因

官方打包文档要求公共 MCP 提交使用公开 HTTPS 端点。本地 MCP 无法这样部署时，需要联系 OpenAI 获取 local MCP support。当前服务在用户电脑上运行 EXE，通过 stdio 提供工具，没有公开 HTTPS 端点。

截图采集必须在用户电脑上运行，单纯搬到云端无法读取各用户的屏幕。远端桥接属于新架构和服务部署工作。已核对的官方页面没有承诺接受本地二进制方案，不能把当前 ZIP 描述为符合标准公共提交条件。

## 后续正式提交

先确认 OpenAI 是否支持该本地 MCP / Windows 二进制分发方案。取得支持后，再补齐已验证发布者身份、真实支持及隐私与条款页面、展示素材、演示和审核案例；不得用虚构发布者或占位网址提交。

标准流程为上传 ZIP、处理自动检查、完成 MCP 连接与审核资料、送审，获批后再发布。发布者需组织所有者权限或 Apps Management Write，并完成身份验证。本次没有执行上传或发布。

官方依据：
- [插件打包与本地 MCP 限制](https://developers.openai.com/plugins/build/plugins)
- [上传、审核与发布](https://developers.openai.com/plugins/deploy/submission)
- [远端 MCP 审核要求](https://developers.openai.com/plugins/deploy/app-review)
