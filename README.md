# DroidDeck 个人定制版

基于 [DroidDeck](https://github.com/Droid-Deck/DroidDeck) 的个人定制项目，当前优先解决 Linux 桌面的中文使用与 Codex／ChatGPT 兼容问题。本仓库不是 DroidDeck 或 OpenAI 官方产品。

## 当前状态

已导入适用的上游源码和定制修改，处于基础验证阶段。没有把“能启动客户端”当成“所有工具调用均可用”。APK 是否构建成功，请以 [定制构建记录](https://github.com/lusu575/droiddeck-custom/actions/workflows/custom-build.yml) 中对应提交的结果为准。

源码基线：Droid-Deck/DroidDeck `f3650d3d379f32a0d33e7a24249ae76023eab8bc`。

- 默认简体中文，保留原语言切换功能。
- 改进 Android 输入法到 KDE 的中文提交与预编辑通道，保护焦点切换，避免长串输入在传输时被截断。
- Xwayland 剪贴板增加 INCR 分块传输，单次上限 1 MiB UTF-8，补充长中文及 emoji 测试。
- 增加中文字体与 Fcitx5 拼音的桌面构建配置。依赖安装、候选窗和各客户端实际行为仍需构建及真机验证。
- 增加 Codex CLI、Codex 桌面、ChatGPT 的已有客户端启动入口和环境诊断。不会自动登录、上传账户资料或关闭 Codex 的授权／沙箱。
- 定制包名为 `com.droiddeck.custom`，官方原版为 `com.droiddeck.launcher`，两者并存，不要求覆盖或卸载原版。

本轮**不内嵌整个 Linux 环境、桌面或 Wine／Proton／FEX 兼容层**，继续使用原项目的下载安装更新流程。红警与触控专项适配暂不开展。

## 验证范围与限制

已通过 41 项定向主机测试，以及修改涉及的 C 编译、Shell 语法、XML 和脚本部署检查。完整上游测试及 Android/KWin 端到端尚未全部通过，不应将此版本视为稳定版。

Codex 的登录、内核沙箱、文件操作、终端命令、浏览器和 MCP 必须逐项验证。PRoot 共享 Android 内核，Linux 客户端打开窗口不代表全部功能可用。传统 X11 客户端与 Wayland 客户端的输入机制不同，也需要分别测试。

详情见 [实现与验证报告](docs/custom/IMPLEMENTATION_STATUS.md)。

## 云端构建

使用 [custom-build.yml](.github/workflows/custom-build.yml)，以 GitHub 托管环境准备上游要求的构建组件，再进行 APK 编译和基础测试。成功时在 Actions 中提供测试 APK artifact，不向源码仓库提交编译输出。

测试签名密钥只在临时构建环境生成，不提交仓库或作为 artifact 上传。不同构建的测试签名可能不同，因此不保证测试版之间可直接覆盖升级；这不会影响使用不同包名的官方原版。正式稳定签名方案尚未设置。

上游原有工作流保存为文档参考，避免此定制仓库意外触发上游发布、签名或通知流程。需要 Docker、Java 17、Android SDK/NDK、Rust 等的本机构建说明可参考 [上游 README](README.upstream.md)。

## 原项目与许可

- 原仓库：[Droid-Deck/DroidDeck](https://github.com/Droid-Deck/DroidDeck)
- 原项目说明和完整致谢：[README.upstream.md](README.upstream.md)
- 主项目许可：[GPL-3.0](LICENSE)

保留上游版权、第三方许可及对应源码。为避免无关大文件，旧版本演示 GIF／宣传截图保留在上游仓库，通过链接访问，不属于构建输入。随二进制分发时仍需履行实际各组件的许可要求。商业客户端、账户、令牌、用户数据和私有签名密钥均不包含在本仓库。
