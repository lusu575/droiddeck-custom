# Codex / ChatGPT 已安装应用启动与基础诊断

此启动器只连接**已经安装且可信**的 Linux 程序。不会下载商业客户端、创建账号、代登录，也不会修改 Codex 配置、审批或工具沙箱。发现程序不代表确认其发行商、架构兼容性或运行能力。

## 默认行为

- `droiddeck-assistant codex` 启动 PATH 中的 Codex CLI；模式后的参数保持原样。
- `codex-desktop`、`chatgpt` 是桌面启动模式，不承诺客户端一定使用这些二进制名称。
- 默认继承当前目录、DISPLAY、WAYLAND_DISPLAY、显示后端和应用自己的 GPU / Electron sandbox 设置。
- 不再默认添加 `--no-sandbox`、`--disable-gpu` 或强制 X11；不添加其他降低隔离的兼容开关。
- 已存在的 locale、IME 及 Codex 环境保持不变。只在缺失时补 LANG、TERM 默认值。仅有效消息 locale 为 zh_CN 且 LANGUAGE 未设置时补中文 LANGUAGE，尊重 LC_ALL/LC_MESSAGES 和显式空值；不会把英文用户的翻译语言强制改成中文。
- 应用原有的配置、脚本和桌面入口仍由应用负责，启动器不审计或保证它们的沙箱设置。启动器不提供关闭沙箱的快捷选项。

Electron 的进程 sandbox 与 Codex 执行工具时的 sandbox 是两层独立机制。PRoot 共享 Android 内核，不能因此视为已获得 namespace、seccomp 或其他内核隔离能力。如果客户端或 Codex 工具沙箱在设备上失败，保留错误并诊断，不自动降级成无沙箱运行。

## KDE 菜单（无需输入命令）

桌面初始化运行 `/usr/local/bin/droiddeck-assistant-menu setup`，会在用户 XDG applications 目录生成三个入口：**Codex 桌面**、**ChatGPT**、**AI 助手环境检查**。仅首次创建，重复启动不会覆盖任何已有文件，包括用户修改和 Hidden 设置；不会改系统应用入口或自动安装软件。自身入口带专用标记并从发现结果中排除，避免递归启动。

应用入口优先用 kdialog 对话框列出已安装的匹配客户端，由用户选择；缺少 kdialog 时在 Konsole 中列出编号，输入序号并回车即可确认，空白回车取消，不需要输入任何命令。即使只有一个候选也需要明确选择；不会自动执行歧义候选。找不到客户端或启动返回错误时显示中文说明，不静默失败，也不尝试关闭沙箱重启。菜单启动默认从用户主目录开始，原应用桌面入口的 Path 仍生效；项目可在客户端中选择。菜单中的环境检查运行六项本地 smoke，并用可滚动窗口显示报告；临时报告关闭后删除。若 kdialog 缺失，检查结果退回 Konsole 窗口，不需要输入命令。

不同桌面包可能只提供部分组件：选择应用需要 kdialog 或 konsole 至少一个；缺少两者时不启动应用，并尝试桌面通知。不能假定所有 KDE 安装都有 kdialog。桌面入口委派依赖 gio。测试验证了生成/保留文件、排除自身、取消选择、中文缺失提示、默认安全参数与临时报告清理；没有对真实 KDE 窗口做设备交互测试。

## 使用

启动器选项必须写在模式之前；模式后所有参数都属于应用：

```sh
droiddeck-assistant --workspace "$HOME/projects/中文项目" codex --sandbox workspace-write
droiddeck-assistant apps
droiddeck-assistant --desktop-file vendor-codex.desktop codex-desktop
droiddeck-assistant --executable "/opt/Assistant App/client" codex-desktop
droiddeck-assistant --executable "/opt/Assistant App/client" --display x11 --graphics software codex-desktop
```

`apps` 从 XDG 用户/系统 applications 目录发现名称或桌面 ID 含 Codex/ChatGPT 的入口，显示路径和原始 Exec，支持任意实际二进制名称与带空格的路径。遵守同 ID 的用户覆盖与 Hidden 屏蔽。不会仅因搜到一个名字就自动执行。名称不含这两个关键字的程序可使用 `--executable` 指定。

`--desktop-file` 接受列表中的 ID 或绝对路径，使用 `gio launch` 处理桌面规范中的引号、字段代码、包装器和工作目录。它不改写入口，所以不支持额外应用参数或显示/GPU覆盖；需要这些参数时改用 `--executable`。若桌面入口的 Path 与显式 `--workspace` 不同，拒绝启动，避免把工作交给错误目录。GIO 返回成功只说明发起启动，不证明应用窗口正常或其最终退出成功。

`--display auto` 与 `--graphics auto` 都不加参数，并保留当前桌面渲染配置。上游嵌套 KDE 可设置 `LIBGL_ALWAYS_SOFTWARE=1`、`GALLIUM_DRIVER=llvmpipe`、`QT_QUICK_BACKEND=software`；启动器不清除这些变量，所以移除 `--disable-gpu` **不意味着已获得硬件加速**。显式 `x11` / `wayland` 需要相应会话变量，只对当前子进程生效；`software` 添加 `--disable-gpu`，实际软件渲染能力仍由应用决定。这些选项面向支持 Chromium/Electron 参数的客户端；其他工具保留 auto。不会开启远程调试端口。本次没有接入实验性的 `droiddeck-gpu` gamescope/Zink 窗口包装器，也没有更改桌面全局渲染设置。

## 诊断与基础检查

```sh
droiddeck-assistant --workspace "$HOME/projects/中文项目" doctor
droiddeck-assistant --workspace "$HOME/projects/中文项目" --check-tools doctor
```

普通 doctor 只读：报告架构、已发现的工具、桌面入口、显示/D-Bus/IME 环境、`graphicsEnvironment` 中的 Mesa/Vulkan/Qt 渲染变量，以及工作目录可写性。存在路径或环境变量并不证明对应功能可用；不会启动客户端、联网、读取登录凭据或发送项目内容。

显式 `--check-tools` 才执行本地 bash、git、python3、node、npm、rg 的短 smoke 检查，每项最多 5 秒，输出截断到 2000 字符。缺失、执行失败、架构错误与超时分别报告；任何一项未通过返回 1，参数或启动错误返回 2。普通 doctor 返回 0 表示报告已生成，不代表全部能力通过。

这些检查**不在 Codex 工具沙箱内**，不验证联网、浏览器或 MCP。GUI 启动成功也不能代替在目标设备上验证 Codex 的授权交互及实际受限工具调用。当前单元/集成测试只验证启动器行为，没有 Android/PRoot 实机或真实商业客户端测试结果。

## 回归测试

```sh
python3 -m unittest discover -s tools/tests -p test_assistant_launcher.py -v
```

覆盖默认安全参数、X11/Wayland 显式选择、Unicode/空格参数、shell 元字符不解释、桌面入口发现/隐藏/错误、GIO 委派、工作目录冲突、进程错误与退出状态、只读诊断、基础检查失败/超时。实际子进程回环使用本机 Python，不替代真实客户端测试。

## 实现依据

- [Electron process sandboxing](https://www.electronjs.org/docs/latest/tutorial/sandbox)：`--no-sandbox` 禁用 Chromium 的全部进程沙箱，官方不建议生产使用。
- [Desktop Entry Exec 规范](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html)：Exec 有独立的引号和字段展开规则，不能作为 shell 命令直接解释。
- [GLib 的 gio launch 实现说明](https://mail.gnome.org/archives/commits-list/2020-December/msg02950.html)：使用桌面文件发起应用启动。
- [Codex Linux sandbox 实现](https://github.com/openai/codex/blob/main/codex-rs/linux-sandbox/README.md)：Linux 隔离依赖具体内核能力。设备支持情况必须结合所安装版本实际验证。
