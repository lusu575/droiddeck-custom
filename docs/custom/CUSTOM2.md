# custom2 中文与助手改进

版本：0.6.9-custom2，独立应用 ID `com.droiddeck.custom`。官方版 `com.droiddeck.launcher` 保留；本轮不内嵌完整 Linux、KDE 或兼容环境。

## 已验证的构建

2026-11-04，源码 `061ca49555e53ab994acc51d36b7a1d736f80779` 的 [GitHub Actions 构建](https://github.com/lusu575/droiddeck-custom/actions/runs/41779301176) 全部通过。125 项相关主机测试、3159 项 Android 单元测试（448 个套件）均无失败；Android 测试无错误、无跳过。APK 包名、签名、原生库及六个引导包校验通过。

登录 GitHub 后下载该运行的 `droiddeck-custom-test-apk` artifact，解压得到 `app-debug.apk`。下载有效期至 2026-12-04。已实际下载并校验 ZIP 摘要与 GitHub 记录一致，APK 为 158,821,316 字节，SHA-256：`c4f64eaf7995df5c402edbc6604b7918dedfc0b87f7eeac66d77700c7415c1dc`。

首轮 custom2 回归测试捕获了 Android KeyCharacterMap 将 supplementary 字符拆成 UTF-16 单元的问题。现已修复并保留原断言，另加混合 Unicode 回归；相关 15 项 KeyboardHost 测试全部通过。这里验证的是发送端与逻辑，不是全部客户端的真机输入兼容性。

## 系统中文与粘贴

- 新安装默认简体中文，系统会话设置 GTK/Qt/XIM 输入环境；应用语言变化时同步 KDE，之后保留用户在 KDE 中选择的语言与输入法设置。
- KDE 菜单“中文支持检查与安装”检查旧下载环境的中文字体、locale 和 Fcitx。默认启动不联网；用户明确确认后通过已配置的发行版软件源补装并保留包管理器原生确认。Arch 会提示需要完整系统更新。完成后退出并重进桌面。
- Android 输入在发送端按完整 Unicode code point 处理，避免把 emoji 和扩展汉字拆成两个 surrogate；长文按批发送，避免一次循环阻塞界面。确认、取消、合成退格、连接关闭及切焦点均有针对性保护。
- 这不代表所有窗口都能直接接收 Android IME 中文。Android→KDE 输入依赖有效的 desktop IME bridge 和目标应用的文本输入支持；主 SessionActivity 在没有 bridge 时只剩 evdev 按键路径，不能保证传递任意中文或 emoji。系统中文还依赖正确配置的 Fcitx、GTK/Qt/XIM 前端与字体环境。遇到不兼容窗口，可使用 Linux 内的 Fcitx 输入或系统剪贴板粘贴，并按应用实际验证。详见[输入测试与能力边界](../testing/custom2-text-input.md)。
- 系统剪贴板统一上限为 1 MiB UTF-8；修复 Wayland 恰好达到上限时被误拒绝的边界，X11 支持 INCR 长文传输和 text/plain 请求。不静默截断；超限提示分段。Android 系统自身可能有更小的 IPC 限制，拒收时提示而不使会话崩溃，Linux 内部粘贴不因此失效。

## ChatGPT / Codex

KDE 菜单新增“Codex 桌面”“ChatGPT”“AI 助手环境检查”，用于选择并启动已经安装的可信 Linux 客户端。不会下载商业程序、登录账号或修改工具授权。支持 XDG 桌面入口和 GIO，避免假定程序必须使用固定文件名。

默认不再添加 `--no-sandbox`、`--disable-gpu` 或强制 X11。保留客户端及桌面本来的配置；移除启动参数并不代表获得硬件 GPU 加速，尤其当前上游 KDE 可能使用软件渲染。可从环境检查中查看实际图形变量。

六项本地工具检查覆盖 bash/git/python3/node/npm/rg 的基本执行，不在 Codex 自己的工具沙箱内，不等同于浏览器、MCP、登录或所有工具调用已经适配。PRoot 仍共享 Android 内核。客户端需要的内核 sandbox 如果不受支持，会保留错误，不自动绕过。详见 [助手说明](assistant-launcher.md)。

## 安装与体验边界

测试签名每次构建重新生成，custom2 不保证能覆盖 custom1；若 Android 报签名冲突，先备份定制版所需数据再考虑处理，切勿卸载官方原版。尚未建立稳定更新签名。

建议用户在 S26+ 先用测试文档验证：中文候选词确认/取消/退格，emoji，中英混合多行长文，切换字段与窗口；再在自己的客户端测试登录、文件读写、终端与各项实际工具。复制包含换行的文本到终端可能直接执行命令，应优先在文本编辑器验证。现阶段没有真机通过结论，也不保证每个第三方客户端都有中文翻译或兼容输入模块。
