# 2.0.2 跨平台适配及验证范围

| 能力 | Linux | Windows | macOS |
| --- | --- | --- | --- |
| 应用按名称/完整路径分流 | 已实现，Linux 环境测试 | 已实现，名称大小写与路径分隔符测试 | 已实现，共用分流核心测试 |
| 自动/直连/代理组选择 | 已实现 | 已实现 | 已实现 |
| 本机管理页面 | Chrome 实测 | 浏览器模拟平台交互测试 | 浏览器模拟平台交互测试 |
| RustDesk 日志学习与地址排除 | 本机运行确认 | 日志格式及目录逻辑测试 | 日志格式及目录逻辑测试 |
| Clash 控制通道 | Unix socket 实测；TCP 测试 | 本机 TCP 通道测试；不支持命名管道 | Unix socket/TCP 共用逻辑测试；socket 路径已适配 |
| 自启动 | systemd 用户服务已启用验证 | 用户启动目录脚本，未原生验证 | LaunchAgent 脚本，未原生验证 |
| 页面快捷入口 | 应用菜单 | 开始菜单 URL | 安装目录 webloc |
| 原生系统端到端验证 | 已完成当前机器验证 | 待 Windows 实机验证 | 待 macOS 实机验证 |

测试使用 Linux 上的实际核心/浏览器及隔离的协议、路径、事件输入。模拟平台逻辑通过不等于已经在 Windows 或 macOS 原生系统运行通过。

Windows：确保存在可用的 Conda 安装或普通 Python 3.10+，并启用 Clash 本机 TCP API；安装器会自动寻找 Conda 并创建 Python 3.12 和 PyYAML 独立环境。使用 install-windows.cmd 或 PowerShell 安装脚本。

2.0.1 已用 Linux PowerShell 7 进行脚本解析和 Conda 协议模拟测试，覆盖 Program Files / ProgramData、路径空格、去重、WindowsApps 占位跳过、坏 Python、指定 Conda 路径、指定 Python 版本创建及环境复用。WindowsPowerShell 5.1 的原生系统集成和实际 Conda 下载/解算仍待 Windows 实机验证。

macOS：先确保 Python 3.10+ 和 Clash 正在运行；在图形会话中使用 install-macos.sh 注册当前用户 LaunchAgent。

这三个平台均需在各自电脑运行本工具后端，不能只复制 index.html 来管理另一台电脑。工具只监听回环地址，不提供跨机器远程管理。

Linux/macOS 的“进程名”与 Windows 的 exe 名称可能不同，规则在当前电脑保存，不自动跨电脑同步。

2.0.2 增加 HTTPS 源回退、独立重试前缀和仅进程生效的超时设置。已在 PowerShell 模拟断网后切换到备用源并验证成功/失败时的环境恢复，未验证该 Windows 电脑到实际镜像站的连通性。

Windows 应用图标使用内置 Windows PowerShell / System.Drawing 提取 EXE 图标，支持完整路径、运行进程名称和 App Paths 注册项查找；不可读取时回退占位图标。原生验证测试仅在 Windows 执行。

## 2.1.0 桌面 App

- macOS：pywebview Cocoa/WebKit；源码安装创建 `~/Applications/Flow Traffic Manager.app`，打包配置输出 `Flow.app`。待 macOS 实机验证。
- Windows：pywebview WebView2；安装器创建开始菜单 `.lnk`，打包配置输出 `Flow.exe` 及依赖目录。需 WebView2 Runtime。待 Windows 实机验证。
- Linux：pywebview GTK/WebKitGTK 4.1；应用菜单启动原生窗口。已在本机验证原生窗口加载管理页面与 WebDAV 区域，支持复用现有后台服务。已构建本机 Linux 分发包；其他发行版和架构需单独验证。
- 三平台共用规则、图表、同步和内核。Python 源码环境需另装 `requirements-desktop.txt`，原后台环境依赖保持在 `requirements.txt`。

## App 内后台规则服务

App 支持无窗口 `--service` 内核和启用/停用登录启动项。Linux systemd、macOS LaunchAgent、Windows 当前用户 Startup 均提供注册适配。临时进程退出、常驻进程在 App 退出后存活、停用后的退出、本机 API 认证及 Origin 校验已在 Linux 隔离环境验证；macOS/Windows 注册内容已做隔离检查，仍需实机验证服务管理与登录启动。
