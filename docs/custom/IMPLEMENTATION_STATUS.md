# DroidDeck 定制版：基础实现与验证

日期：2026-11-04。基于上游提交 `f3650d3d379f32a0d33e7a24249ae76023eab8bc`。
用户已授权将本批源码发布到个人公开仓库并尝试 GitHub Actions 构建。历史上的本地验证结果如下；是否产出 APK 以仓库对应提交的 Actions 记录为准。

## 首次云端构建结果

2026-11-04，提交 `850f5459f46690a3b4fc63944afe7bc7b017250c` 的 [GitHub Actions 运行](https://github.com/lusu575/droiddeck-custom/actions/runs/41768860781) 已完成，结论为成功。

- APK 编译、native 库检查、定制包名/签名/内置引导包检查全部通过。
- 65 项相关主机测试通过；Android 单元测试为 447 个套件、3142 项测试，0 失败、0 错误、0 跳过。
- APK 大小：158,803,987 字节。SHA-256：`175f733ed4e7d75234df19692d5df53b86ffb8254917882c782298f7bab9897d`。
- 下载运行中的 `droiddeck-custom-test-apk` artifact 后解压即可获得 APK；artifact 保留至 2026-12-04。
- 首轮构建暴露了预加载校验脚本对旧工作流路径的硬编码，已修复为验证当前定制工作流的运行环境，并保留历史上游构建来源校验；新增回归测试覆盖替换工作流和运行环境变化。
- 没有进行真机安装、覆盖、卸载或迁移。官方包名与定制包名不同；测试签名每轮重新生成，不保证不同测试构建可覆盖升级。

以下本地历史验证记录及真机待验收边界继续适用。单元测试通过不能代替中文候选窗、长文粘贴、双屏焦点、Linux 客户端登录或 Codex 工具端到端验证。

## 已落地的源码

- Android 输入连接不再只把中文拆成虚拟按键。新增到 KDE input-method 的 UTF-8 提交/预编辑通道；每个焦点使用独立标记，拒绝过期字段的输入；长串以私有 UTF-8 临时文件和一次通知传递，读取后删除，guest 按完整 Unicode 字符分块；预编辑预览上限 700 字符，最终提交保留完整文本。保留原按键回退路径。输入法禁止个性化学习。
- Xwayland 剪贴板上限从 64 KiB 提高到 1 MiB，超过单次属性大小的文本走 ICCCM INCR 分块传输。传输使用内容快照，具备并发限制和超时回收，不把中文作为 shell 命令执行。
- 新安装默认选择简体中文，仍可在原语言设置切换其他语言或跟随系统。既有用户的明确选择不被覆盖。
- 中文字体配置增加 Noto Sans CJK SC；Ubuntu/Arch 桌面构建清单加入 Noto CJK、Fcitx5 拼音及相关前端。首次启动创建拼音配置，保留已有输入法配置。Fcitx5 的 Wayland 输入法插件关闭以避免抢占现有 Android→KDE 通道，XIM 用于传统 X11 客户端。
- `droiddeck-assistant doctor` 输出架构、现有程序、显示、D-Bus、语言、图形环境及工作目录诊断，可显式运行本地工具检查。Codex/ChatGPT 桌面入口支持已安装程序发现，默认不再关闭 Electron 沙箱、强制 X11 或禁用 GPU；既有桌面软件渲染环境仍会保留，不代表硬件加速已验证。不会下载客户端、登录或放宽 Codex 工具权限。详见 [启动与诊断说明](assistant-launcher.md)。
- 用户最新决定不内嵌环境。本轮离线打包入口、catalog 改动与打包脚本已移除，继续原版官方下载/安装/更新路径。
- 定制应用使用独立包名 `com.droiddeck.custom` 和“DroidDeck 定制版”名称，保留原源码 namespace/JNI 路径。与官方 `com.droiddeck.launcher` 可并存，私有应用数据隔离；未连接设备、覆盖、卸载或迁移原版数据。

## 重要边界

这不是“所有桌面客户端和工具已适配”的结论。Codex CLI 启动入口和诊断已经实现，但本环境没有用户的 Linux ChatGPT/Codex 桌面二进制，无法验证其登录、桌面工具、浏览器工具或 MCP。官方 Codex CLI 的存在，也不能证明其 Linux 内核沙箱在 Android PRoot 下可运行。没有使用关闭审批/关闭 Codex 沙箱的参数。

Android→KDE 新通道需要应用支持 KDE 文本输入协议。传统 X11 客户端仍依赖 Fcitx5/XIM、按键或剪贴板；不能声称所有 Electron/X11 应用已通过中文实测。Android Kotlin/JNI 集成、IME 长串提交性能、桌面与双屏焦点切换、输入法候选窗都仍需 Android 构建及 S26+ 基本实测。

长文本改善主要是系统剪贴板，**单次上限 1 MiB UTF-8**，不是无限文本；包含换行的文本粘贴到终端可能执行命令，应在编辑器测试。Wayland→Android 原有边界及 Android 剪贴板自身大小限制仍需真机验证。

中文软件包必须重新构建桌面包才真正内置。仅安装本批源码构建的 APK，不会自动把旧桌面包变成带 Fcitx5/新字体的包。环境内嵌已按用户最新指令停止，不会生成离线整包。

## 更新与体积调查

上游 runtime 只在远程版本与已安装版本不同时自动更新，同一 app/release 最多尝试 3 次、重试间隔 10 分钟。PRoot/DirectAudio 等使用摘要与完成标记；FEX catalog 有 10 分钟缓存，安装也检查现有 tag 和校验值；Proton 有独立版本比较。下载器支持断点续传。以上不等于二进制差分升级：runtime/桌面/独立兼容层的更新仍通常下载完整压缩包。Steam 管理的兼容层更新另外由 Steam 处理。未获得用户设备日志，不能确认其“经常下载”属于新版本、失败重试还是实际重复安装。

2026-11-04 查询到的官方压缩归档：

| 组件 | 压缩体积 | 说明 |
|---|---:|---|
| Ubuntu runtime | 291,531,733 B | ubuntu-r1-rc4，约 291.5 MB |
| FEX | 4,081,209 B | 2610-r7，约 4.1 MB |
| ARM64 Proton Experimental seed | 398,113,534 B | 25502785，约 398.1 MB |
| 旧 Arch KDE | 972,598,429 B | 源码固定 desktop-kde-r3；**不是当前 Ubuntu 桌面大小** |

前三项合计 693,726,476 B（约 693.7 MB）。如只用旧 Arch KDE 作容量参考，总归档约 1.67 GB，未包含 APK 本体、中文字体、输入法或其他兼容层，且旧 Arch KDE 不能直接与 Ubuntu rootfs 混装。当前 Ubuntu 桌面压缩大小未核实，不能给出最终 APK 实测大小。解压空间另算，APK 内置和安装后的展开数据也会同时占空间。

用户已决定本轮不做环境内嵌。以上仅为调查结论；原版组件下载安装更新方式完全保留。

## 许可处理

- DroidDeck 为 GPL-3.0；分发定制二进制时需按许可提供对应源码、修改与构建资料。
- FEX 主项目 MIT，保留版权和许可；其捆绑依赖另核对。
- Proton 明确是多许可证集合，不能统一当成 MIT 或单个 GPL；每个 Wine/图形/媒体依赖均需保留相关许可并履行对应源码义务。
- Fcitx5、中文插件、词库、Noto 字体和桌面发行版应按实际包生成清单，保留版权/许可证与需要的对应源码。未下载的包不能假定已完成许可审计。
- Steam 客户端、商业 ChatGPT 桌面二进制、账号/令牌不内嵌；Codex 开源 CLI 与商业桌面客户端是不同分发对象。

来源：
- [runtime catalog](https://raw.githubusercontent.com/Droid-Deck/DroidDeck-Components/main/linuxfs-ubuntu.json)
- [FEX catalog](https://raw.githubusercontent.com/Droid-Deck/DroidDeck-Components/main/fex.json)
- [Proton seed catalog](https://raw.githubusercontent.com/Droid-Deck/DroidDeck-Components/main/steam-seed.json)
- [FEX MIT](https://github.com/FEX-Emu/FEX/blob/main/LICENSE)
- [Proton 多许可证说明](https://github.com/ValveSoftware/Proton/blob/proton_10.0/LICENSE)
- [Codex CLI 官方仓库](https://github.com/openai/codex)
- [Fcitx5 许可目录](https://github.com/fcitx/fcitx5/tree/master/LICENSES)

## 验证

- 定向主机回归：41 项测试通过，覆盖原桌面语言/Chromium 包装、中文配置、UTF-8 提交/预编辑与错误焦点拒绝、1 MiB INCR 传输/并发保护/超时、定制包并存保护和助手启动参数。
- `cc -Wall -Wextra -Werror` 编译剪贴板 helper 及 INCR 测试通过。
- 修改的 shell 脚本 `bash -n` 通过；`git diff --check` 通过。
- `droiddeck-ime` 的 Wayland 协议使用 socketpair 与模拟消息验证。当前容器禁止创建 AF_UNIX datagram socket，因此真实 Android LocalSocket→guest 端到端未跑；helper 在此环境下保留焦点侦测并报告 Unicode bridge 不可用。
- 全部上游 Python 测试尝试运行，但存在容器限制（socket、依赖、非 Ubuntu 系统）导致错误/失败，长时间未结束后中止；**全套测试不是通过**。
- Gradle Android 测试没有执行：Gradle 8.10.2 尚未缓存，下载报 `Network is unreachable`。容器无 Android SDK/NDK、Docker、Rust 和 JDK 17 构建组合。没有生成可安装 APK。

## 下一步基本验收

在可用云端 Android 构建环境完成源码编译、Android 单测、native 编译、桌面包构建，再由用户在 S26+ 验证：Kate/Konsole/浏览器和实际客户端中文输入；候选词确认/取消/退格；2 万字中文和中英混合/emoji 多行复制粘贴；切换字段与双屏；Codex 读取/编辑测试目录文件、运行无害命令和测试程序；按实际工具逐项检查，不默认给全部工具授权。红警与触控未改动。
