# Codex 屏幕眼睛 / Screen Eyes

为 Windows 上的 Codex 原生语音提供按需屏幕观察。发布者：**Bitforest**。

## 快速安装

1. 先安装并运行过官方 Codex / ChatGPT 桌面应用。
2. 从 [Releases](https://github.com/BTS-BitForest/codex-screen-eyes/releases) 下载 **ScreenEyesSetup-0.4-Windows-x64.exe**。
3. 双击安装器，点击“安装屏幕眼睛”。无需管理员权限或 Python，不创建桌面快捷方式。
4. 新建 Codex 聊天，说“打开 screen-eyes 共享设置”，选择来源并勾选“跟随语音自动共享”。
5. 再开始新的原生语音，说“用 screen-eyes 看看我的屏幕”。结束语音后停止共享。

安装器只负责安装。日常通过插件工具打开设置，不用独立启动伴侣应用。插件内部的本地截图程序与后台仍然必需，不会因为没有快捷方式就消失。

## 已有 Codex CLI

```powershell
codex plugin marketplace add BTS-BitForest/codex-screen-eyes
codex plugin add screen-eyes@bitforest-screen-eyes
```

安装后开始新聊天；若工具未加载，自行完整退出并重新打开桌面应用。安装器不会强制关闭应用或修改代理。

## 功能与限制

- 一次选择一个显示器或可见窗口；支持多屏选择，不自动跟随鼠标切屏。
- 按请求获取截图，不持续上传视频，不控制鼠标键盘。
- 自动模式可关闭设置窗口；手动“开始共享”需保持设置窗口打开。
- 暂停后同一次语音不会自动重开；下一次新语音可恢复。取消自动模式可禁止后续自动开启。
- 自动共享最长 4 小时，依赖本地 Codex 会话记录，**仍为实验功能**，可能受客户端更新影响。
- 仅验证 Windows 本地 Codex 语音。普通 Chat、macOS、Linux 和纯网页端兼容性没有验证。
- GitHub 分发不等于官方公共插件市场上架；无需 OpenAI 开发者市场验证才能使用此仓库分发。
- 现有旧的直接 MCP 注册可能覆盖插件；安装器会提示，不能擅自删除用户配置。同名插件只保留需要的来源启用。

完整说明：[使用说明](plugins/screen-eyes/使用说明.txt)。其中桌面快捷方式是旧本机安装的可选入口，新快速安装器不创建快捷方式。

## 画面与隐私

截图和来源/时间/指针等元数据通过 Codex 工具通道提供给模型。窗口遮挡内容可能进入截图。请仅选择愿意共享的来源。

本地后台从 Codex 会话记录提取语音生命周期字段，不另行保存音频或转写，不将会话日志发给其他服务。Codex 自身的数据处理与记录适用其政策。网络设置仅在用户主动保存时修改 Codex 配置，可能保留本地备份。

## 验证

已完成生命周期与打包进程测试、隔离插件安装，并在本机真实原生语音中验证两次新截图及结束后停止。快速安装器另做隔离首次安装与重复安装检查。不是所有机器或所有模式的兼容承诺。

## 开发与支持

运行时源文件位于 src；可分发插件位于 plugins/screen-eyes，第三方运行时许可随插件附带。安装器的源文件为 src/quick_installer.py。

问题请提交 [Issues](https://github.com/BTS-BitForest/codex-screen-eyes/issues) 或联系 **1484805878@qq.com**。不要提交密码、代理凭据、私人截图或完整会话日志。
