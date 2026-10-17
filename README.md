# Flow 应用流量流向管理（Linux / Windows / macOS）

按应用管理流量流向，可选择沿用订阅规则、直连或指定代理组，支持进程名称和完整路径匹配，提供本机管理页面。

RustDesk 自动识别远端 IP、绕过 TUN 是其中的一项专用功能。

适用：Clash Verge Rev + Mihomo TUN。不是所有 VPN 客户端通用的配置工具。

源码目录：`app-traffic-manager`。已有安装的数据目录与服务名保留旧名称，以兼容现有配置。

**版本：2.1.0。新增 macOS、Linux、Windows 独立桌面 App，复用现有规则、域名分流和 WebDAV 同步。**

| 系统    | 安装入口                     | 自动启动           | 页面入口                               |
| ------- | ---------------------------- | ------------------ | -------------------------------------- |
| Linux   | `bash install-linux.sh`    | systemd 用户服务   | 应用菜单的 Flow Traffic Manager        |
| Windows | 双击 `install-windows.cmd` | 当前用户登录启动项 | 开始菜单的 Flow Traffic Manager        |
| macOS   | `bash install-macos.sh`    | 用户 LaunchAgent   | ~/Applications 中的 Flow Traffic Manager.app |

三个平台的默认管理地址都是 **http://127.0.0.1:17891/**。每台电脑管理自己的 Clash；把代码复制到另一台电脑后，需要在那台电脑安装。

共同前提：Clash Verge Rev/Mihomo，应用分流使用规则模式。运行环境为 Python 3.10+；Windows 安装器可通过已安装的 Conda 自动创建 Python 3.12 环境。Windows 还需启用 Clash 的本机 TCP API（见 Windows 安装步骤）。仅安装本工具不会安装或替代 Clash。浏览器页面不是独立的代理引擎。

Linux 已在当前机器安装验证；Windows/macOS 已实现平台适配和安装脚本，并完成跨平台逻辑测试，尚未在这两个系统实机安装验证。细项见 `COMPATIBILITY.md`。

## 桌面 App

安装后从应用菜单、开始菜单或 `~/Applications/Flow Traffic Manager.app` 启动。界面运行于独立原生窗口，不需要打开浏览器。原有浏览器地址仍可作为备用入口。

- 桌面入口为 `desktop_app.py` / `open-manager.py`，使用 pywebview：macOS 使用系统 WebKit，Windows 使用 WebView2，Linux 使用 GTK / WebKitGTK。
- App 会复用已有后台服务，或启动独立的无界面内核进程。应用分流页新增“后台规则服务”开关：启用后，关闭窗口仍持续维护规则，并随当前用户登录启动；未启用时，内核跟随 App，最后一个窗口退出后自动停止。已应用的 Clash 规则不会因窗口关闭被移除。
- 首次运行自动识别 Clash Verge 配置目录；识别失败时，可在启动窗口中选择配置目录。已有 `settings.json`、`policies.json` 和 `webdav.json` 保持在原用户数据目录。
- 只在首次设置窗口启用目录选择桥接。管理窗口不暴露 Python 桥接，继续使用原有本机认证和 CSP。

源码运行：

```bash
python -m pip install -r requirements-desktop.txt
python open-manager.py
```

Linux 需先安装系统 GUI 依赖，运行环境应能导入系统的 `gi` 与 `cairo`（安装器使用 `--system-site-packages` 的 venv）：

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

Windows 需安装 Microsoft Edge WebView2 Runtime；macOS 使用系统 WebKit。三平台源码安装入口保持不变，安装器会安装桌面依赖并创建本机 App 入口。

### 构建独立分发包

在**目标操作系统**上执行（不跨系统编译）：

```bash
python -m pip install -r requirements-desktop.txt "pyinstaller>=6.10,<7"
python build-desktop.py
```

输出：Windows `dist/Flow/Flow.exe`、Linux `dist/Flow/Flow`、macOS `dist/Flow.app`。Windows/Linux 请分发整个 Flow 目录，不能只复制可执行文件。Linux 解压后可运行包内 `bash install-app.sh` 注册应用菜单和任务栏图标；注册后不要移动该目录。分发包包含 Python 和应用依赖；Linux 仍依赖目标系统的 GTK/WebKitGTK、图形会话及兼容的系统库。macOS 构建须另行签名、公证以正式分发；Windows 正式分发可补充代码签名。仓库中的 `.github/workflows/desktop.yml` 提供三平台构建与压缩归档流程，可手动触发或通过版本标签触发。不同 CPU 架构需要对应构建机。

### GitHub Actions 构建与发布

工作流：`.github/workflows/desktop.yml`，名称 **Build Flow Desktop**。将此项目上传到 GitHub 后即可使用，无需配置额外 Secret。

- 手动构建：仓库 **Actions → Build Flow Desktop → Run workflow**。工作流文件需先进入仓库默认分支。
- 自动构建：向 `main` / `master` 推送代码，或提交到这些分支的 Pull Request 时构建（仅修改 Markdown 文档会跳过）。
- 版本发布：先确认 `runtime_paths.py` 中 `VERSION`，再推送相同版本标签。例如当前版本 `2.1.0`：

```bash
git tag v2.1.0
git push origin v2.1.0
```

标签必须为 `v` 加代码版本号，否则构建会报错。四个目标全部成功后，自动创建 GitHub Release 并上传应用包和校验文件；手动/分支/PR 构建只保存 Artifacts，不发布 Release。预发布版本需同时将代码版本和标签设为例如 `2.2.0-beta.1` / `v2.2.0-beta.1`，Release 会标记为预发布。

| 构建目标 | Runner | 产物示例 |
| --- | --- | --- |
| Linux x86_64 | ubuntu-24.04 | `Flow-2.1.0-linux-x86_64.tar.gz` |
| Windows x86_64 | windows-2022 | `Flow-2.1.0-windows-x86_64.zip` |
| macOS Intel | macos-15-intel | `Flow-2.1.0-macos-x86_64.zip` |
| macOS Apple Silicon | macos-15 | `Flow-2.1.0-macos-arm64.zip` |

在运行详情页 **Artifacts** 下载，构建产物保留 14 天；失败时提供 PyInstaller 诊断文件，保留 7 天。每个包附带 `.sha256` 文件。版本 Release 下的附件可长期下载。构建使用普通只读权限，仅标签发布 Job 请求 `contents: write`；如组织策略禁用 Release 写入，需在仓库/组织 Actions 设置中放行。分发包暂未加入 Apple 签名/公证或 Windows 代码签名。Linux 包仍需系统 GTK/WebKitGTK 和兼容的系统库。

参考：[GitHub 托管 Runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)、[GitHub CLI Release 发布](https://cli.github.com/manual/gh_release_create)。

当前已在 Linux 原生 GTK 窗口验证页面与同步区域加载，并构建 Linux 分发目录。macOS/Windows 已补齐 App 入口、安装脚本与构建流程，仍需在各自系统上构建和实机验证。

### 在 App 中管理后台服务

“应用分流”页面顶部提供 **后台规则服务** 开关。可直接在 App 中启用或停用，无需再次运行安装脚本，也无需管理员权限。启用时注册当前用户的登录启动项：Linux 为 systemd 用户服务、macOS 为 LaunchAgent、Windows 为用户 Startup 登录项。服务复用原规则和 WebDAV 数据，后台持续执行应用分流规则维护、RustDesk 地址学习，以及用户已开启的 WebDAV 自动上传。

未启用时关闭 App 会结束临时内核；启用时后台内核继续运行。停用后，本次 App 会话仍可使用内核，最后一个 App 窗口关闭后结束；仅用浏览器连接且没有 App 会话时，新的后台内核会在停用后退出。规则仍保留在 Clash 中，不会自动恢复为订阅默认值。设置保存在运行数据目录 `background-service.json`，不同步到 WebDAV。服务依赖 App/Python 安装路径，启用后不要移动或删除安装目录。重新运行安装脚本会保留开关状态。升级或卸载前，请先停用后台常驻并关闭 App，避免后台进程占用文件或规则锁。

源码和打包程序均支持 `--service --data-dir <目录>` 无界面启动模式；此模式不导入桌面 WebView，也不要求图形显示器。多个 App 会话共享一个内核，通过会话存活检测清理临时进程。

桌面及服务日志为运行数据目录的 `desktop.log`。可执行 `python desktop_app.py --check` 检查桌面 Python 依赖。

参考：[pywebview 安装与系统依赖](https://pywebview.flowrl.com/guide/installation)、[分发打包](https://pywebview.flowrl.com/guide/freezing)。

## 应用流量管理页面

侧栏分为三个页面：“应用分流”包含网络概览、应用与连接、网站域名分流及各应用流量；“TUN 直连地址”包含 RustDesk 完全绕过 TUN；“WebDAV 规则同步”包含同步设置与操作。窄窗口使用顶部下拉菜单切换。页面链接支持刷新和前进/后退。

安装或更新后，打开 **http://127.0.0.1:17891/**。服务只监听本机回环地址，与原有的自动学习服务一同随用户会话启动。

页面支持：

- 显示 Clash 当前能识别的应用、进程路径、连接数量、累计上传/下载和实际代理链。
- 从应用行直接选择“自动”“直连”或一个现有 Clash 代理组。
- 手动添加尚未联网的应用，按进程名称或完整路径匹配。
- 编辑或移除规则；“自动”会移除该匹配项的手动规则，恢复已有订阅逻辑。RustDesk 仍有本工具的默认直连规则。
- 可选择断开该应用已有连接，让重连使用新策略。不会主动断开其他应用连接。
- 查看 RustDesk 学习到的远端/服务器地址，开关 RustDesk 完全绕过 TUN。

应用规则要求 Clash 处于**规则模式**。代理组中当前使用哪个节点，仍在 Clash Verge 中管理。

**直连和绕过 TUN 的区别：**普通应用的 DIRECT 不使用代理节点，但仍可能经过 TUN。RustDesk 的地址排除可完全绕过 TUN，适合点对点打洞。为 rustdesk / rustdesk.exe 指定代理组时，本工具会自动关闭 RustDesk 的地址排除，避免排除项使代理规则失效。移除代理规则后，可按需重新开启 TUN 排除。

页面通过现有本机 Mihomo API 读写配置；支持 Linux、Windows 和 macOS。完全绕过 TUN 的连接无法在 Clash 连接列表中显示，可手动添加对应进程。

手动规则保存在安装目录的 `policies.json`，与自动学习到的地址分开维护。网页没有加载外部脚本、字体或统计服务，不把 Clash 密钥发送到浏览器。写入接口校验本机 Host、同源 Origin 及会话 Cookie。

如默认端口被占用，可在 `settings.json` 添加 `"web_port": 17892`，重启服务，然后访问该端口。安装脚本打印的是默认地址；自定义端口以 settings.json 和 bypass.log 为准。

从旧版本升级：解压新包后重新运行对应平台的安装脚本。原 settings.json、学习状态及既有脚本保留。卸载时，页面和后台学习服务会一并停止，并清理本工具维护的规则。

## 自动处理什么

- 默认每 5 秒读取 RustDesk 当前日志的新增内容，兼容主控端和被控端日志。
- 只读取明确的打洞/连接事件，忽略局域网、回环和保留地址。
- 动态识别 RustDesk2.toml 中配置的自定义服务器，服务器域名每 5 分钟重新解析。
- 远端 IP 默认保留 7 天，最多 64 个；服务器地址另外保留。
- 在全局 Script.js 中维护带 BEGIN/END 标记的独立代码段，保留已有 main 函数。
- 修改持久配置，并通过本机 Mihomo API 应用；订阅更新和客户端重启后也能继续使用。
- 地址列表没变化时不会反复加载内核。日志轮换、后台异常和 Clash 晚于脚本启动时会继续重试。
- 卸载仅移除本工具维护的代码段和配置项，保留安装前已有规则。

首次遇到新远端时，可能先走中转。后台学习地址后，断开并重新连接 RustDesk，重新尝试点对点打洞。应用 TUN 配置可能使当前连接短暂断开。绕过 TUN 后是否能点对点连接仍取决于两端网络。

注意：排除规则按目标 IP 生效，因此其他应用访问同一目标 IP 时，也会绕过 TUN。

## Linux 安装

需要 Python 3.10+、venv、systemd 用户服务。先打开 Clash Verge 和 RustDesk，再执行：

```bash
bash install-linux.sh
```

程序安装在 `~/.local/share/rustdesk-clash-bypass/`（设置了 XDG_DATA_HOME 时使用相应数据目录），通过 systemd 用户服务随用户会话启动。不需要 sudo。使用已有 PyYAML；如果环境没有，会在专用 venv 内安装 PyYAML。

自定义位置：

```bash
bash install-linux.sh --clash-dir /path/to/clash-verge-data --log-dir /path/to/RustDesk/log
```

检查：

```bash
systemctl --user status rustdesk-clash-bypass.service
journalctl --user -u rustdesk-clash-bypass.service -n 30
cat ~/.local/share/rustdesk-clash-bypass/bypass.log
```

如果配置了文件日志，详细错误以 bypass.log 为准。确认路由：

```bash
ip route get 远端公网IP
```

应显示物理网卡，而非 Meta/TUN 网卡。直接 TCP 连接也可以用 `ss -tnp` 检查。

卸载（保持 Clash Verge 运行）：

```bash
bash uninstall-linux.sh
```

## macOS 安装

先安装 Python 3.10+，运行 Clash Verge Rev、RustDesk。在解压目录打开终端：

```bash
bash install-macos.sh
```

安装在 `~/Library/Application Support/RustDeskClashBypass/`。脚本安装专用 venv 和 PyYAML，并注册 `~/Library/LaunchAgents/local.flow.traffic-manager.plist`，登录后自动启动完整后台和页面。

打开页面可使用浏览器访问默认地址，或双击安装目录内的 `Flow Traffic Manager.webloc`。

使用特定的 Python 或自定义 Clash / RustDesk 日志目录：

```bash
PYTHON_BIN=/opt/homebrew/bin/python3 bash install-macos.sh \
  --clash-dir "$HOME/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev" \
  --log-dir "$HOME/Library/Logs/RustDesk"
```

自动识别 macOS 的 Clash 数据目录、当前用户及可访问的 RustDesk 服务日志与配置。默认使用当前用户 Clash Unix socket；如果接口不可访问，可启用本机 TCP API，设置方式与 Windows 部分相同。

检查及重启：

```bash
launchctl print "gui/$(id -u)/local.flow.traffic-manager"
launchctl kickstart -k "gui/$(id -u)/local.flow.traffic-manager"
tail -n 30 "$HOME/Library/Application Support/RustDeskClashBypass/bypass.log"
```

卸载（保持 Clash Verge 运行）：

```bash
bash uninstall-macos.sh
```

脚本需要在已登录的图形用户会话中运行，不使用 sudo。Apple Silicon 和 Intel 均使用本机已安装的 Python；没有内置架构专用二进制。

## Windows 安装

运行 Clash Verge Rev 和 RustDesk。安装器会优先复用本工具已创建的有效环境，然后自动发现 Miniconda/Anaconda/Miniforge/Mambaforge；未找到 Conda 时再尝试普通 Python 3.10+。不要求先把 Conda 或 Python 加入 PATH。

脚本自动识别 `%APPDATA%` / `%LOCALAPPDATA%` 中常见的 Clash Verge 数据目录，读取当前用户和服务账户下可访问的 RustDesk 日志。默认不需要管理员权限；如果服务日志不允许当前用户读取，设置可读日志目录，或在你自己的管理员会话里运行并验证权限。

### 1. 确认本机 Clash API 可用

Linux / macOS 默认优先使用现有 Unix socket，并在连接阶段不可用时尝试配置中的本机 TCP API。Windows 版使用本机 TCP API，**不使用 Windows 命名管道**。

如果尚未启用 TCP API，在 Clash Verge 的全局扩展配置中合并下面一项，保存并重新应用订阅：

```yaml
external-controller: 127.0.0.1:9097
```

保留已有的 `secret`；工具会从本机配置读取，不需要把密钥填进安装脚本。不要把 API 绑定到公网网卡。如果此项被客户端设置覆盖，请在 Clash Verge 的设置中配置外部控制器，并检查最终生成的 `clash-verge.yaml` 中该项确实生效。

如果你的 API 已在其他本机端口监听，可以保留现有端口。工具会读取配置中的地址。

### 2. 安装

在解压目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-windows.ps1
```

安装脚本会创建专用运行环境、安装 PyYAML，并在当前用户启动目录创建 VBS 启动项，立即启动后台进程，下次登录自动启动。`ExecutionPolicy Bypass` 仅用于此次 PowerShell 进程，不修改系统执行策略。

自定义路径：

```powershell
.\install-windows.ps1 -ClashDir 'D:\ClashData' -LogDir 'D:\RustDeskLogs'
```

安装位置：`%LOCALAPPDATA%\RustDeskClashBypass`。

### 自动查找 Conda 和创建依赖

2.0.1 起支持自动查找：

- `ProgramFiles`、`Program Files`、`Program Files (x86)`、`ProgramData`、`LOCALAPPDATA`、用户主目录及 `LOCALAPPDATA/Programs`。
- PATH、CONDA_EXE / CONDA_PREFIX / CONDA_PYTHON_EXE 和 Conda 相关卸载注册表项。
- 其他就绪固定磁盘根目录及其 `Program Files`、`ProgramData`、`Apps`、`Tools`、`Software`、`Development` 目录。
- 上述位置内名称包含 Miniconda、Anaconda、Miniforge、Mambaforge、Continuum 的常见安装目录。搜索有范围限制，不会递归扫描整块磁盘。

发现 Conda 后，在 `%LOCALAPPDATA%\RustDeskClashBypass\conda-env-py312` 创建 **Python 3.12 + PyYAML >=6.0.2,<7** 的独立环境。不会改动 Conda 的 base 或你已有的其他环境，也不需要 `conda init` 或手动 `conda activate`。2.0.2 默认在本次安装中使用清华 conda-forge HTTPS 镜像，失败后尝试 conda-forge 官方 HTTPS 源，不使用全局 `.condarc` 中的旧 HTTP 默认镜像。

WindowsApps 的 Python 占位入口会被跳过；低于 3.10 或不能运行的 Python 不会再直接阻止后续探测。Conda 自己的 base Python 版本低于 3.10 也不影响查找，应用使用新创建环境的 Python。

自定义安装位置或版本：

```powershell
# 指定 Conda 安装目录（也可传 conda.exe / conda.bat 完整路径）
.\install-windows.ps1 -Runtime conda -CondaPath 'D:\Program Files\Miniconda3'

# 增加搜索目录，指定新环境的 Python 主次版本
.\install-windows.ps1 -SearchRoot 'D:\DeveloperTools' -PythonVersion '3.12'

# 强制使用普通 Python 创建 venv
.\install-windows.ps1 -Runtime python -PythonPath 'C:\Python312\python.exe'

# 指定可访问的 HTTPS 频道（仅本次安装）
.\install-windows.ps1 -CondaChannel 'https://conda.anaconda.org/conda-forge'

# 需要沿用公司或自定义 .condarc 时，明确选择原有渠道
.\install-windows.ps1 -UseConfiguredChannels

```

找到普通 Python 时仍使用安装目录下的 `venv`。环境信息写入 `runtime.json`，安装、登录启动及卸载都会使用同一解释器。卸载保留这些独立环境供排错；不会删除 Conda 本身。

如果 Conda 下载或解算失败，安装器保留原始输出并尝试下一个下载源；所有源都失败时会明确报错。重试会使用新的独立环境路径，不混用不同渠道的包，也不删除上次未完成的环境。不会修改全局渠道、关闭 TLS 校验或自动接受额外协议。



检查运行日志：

```powershell
Get-Content "$env:LOCALAPPDATA\RustDeskClashBypass\bypass.log" -Tail 30
```

确认直连（把 IP 改为远端公网 IP）：

```powershell
Get-NetTCPConnection -RemoteAddress 117.176.166.41 -State Established
```

结合 RustDesk 会话里的连接类型确认是否点对点。单独看到 Clash 的 DIRECT 标记不足以确认。

卸载（保持 Clash Verge 运行）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall-windows.ps1
```

卸载脚本删除启动项、停止该工具的 Python 进程，并清理工具维护的 Clash 配置。安装目录、日志和原脚本备份会保留，以便排查。

## 配置文件

安装目录的 `settings.json` 支持：

```json
{
  "clash_dir": "/path/to/clash-verge-data",
  "log_dirs": ["/path/to/RustDesk/log"],
  "interval_seconds": 5,
  "peer_ttl_days": 7,
  "max_peers": 64,
  "controller": null
}
```

Windows 路径在 JSON 中要使用 `\\`，或者直接使用 `/`。`controller` 默认读取 Clash 配置，可覆盖为 `127.0.0.1:9097`；只允许本机回环地址。

更改 settings.json 后，Linux 执行：

```bash
systemctl --user restart rustdesk-clash-bypass.service
```

Windows 可重新运行安装脚本来重启，既有 settings.json 会保留。需要重新自动探测路径时，先备份再删除 settings.json，然后重新安装。

`state.json` 保存学习到的 IP 及清理所需的归属信息，避免运行过程中手工修改。`Script.js.original` 保存首次安装时的全局脚本，不含订阅或代理节点信息。默认不会上传日志或配置。

## 诊断与通用启动

源码和管理页面完全相同，平台区别由 `runtime_paths.py` 和各自安装脚本处理。

诊断（使用安装目录内 venv 的 Python）：

```bash
# Linux
~/.local/share/rustdesk-clash-bypass/venv/bin/python \
  ~/.local/share/rustdesk-clash-bypass/bypass.py doctor

# macOS
"$HOME/Library/Application Support/RustDeskClashBypass/venv/bin/python" \
  "$HOME/Library/Application Support/RustDeskClashBypass/bypass.py" doctor
```

```powershell
# Windows
$app = "$env:LOCALAPPDATA\RustDeskClashBypass"
$runtime = Get-Content "$app\runtime.json" -Raw -Encoding UTF8 | ConvertFrom-Json
& $runtime.python "$app\windows-bootstrap.py" "$app\bypass.py" doctor
```

诊断输出当前平台、版本、目录、可读日志及 API 连接状态，不输出订阅、节点或 API 密钥。`open-manager.py` 使用标准库打开当前配置的管理页面。

不需要自动启动时，也可以在源码目录用自己创建的 Python 3.10+ venv 安装 `requirements.txt`，执行 `python bypass.py init`，再执行 `python bypass.py watch`；它会前台运行完整后台与页面。已安装的服务应先停止，避免同一配置被两个实例修改。

## 排错和限制

- `No readable RustDesk CURRENT logs`：查找名称包含 CURRENT 的 `.log` 文件，调整 log_dirs。日志内必须有打洞或连接事件；某些日志级别或定制客户端可能不记录这些内容。
- `Clash API returned HTTP 401`：确认最终配置文件里的 secret 与当前内核一致，再重新应用订阅。
- API 连接失败：确保 Clash 正在运行。Windows 确认 TCP external-controller 已启用；Linux 默认检查当前用户的 Clash Verge 服务 socket。
- 能学习到 IP 但仍中转：应用后重新连接；已经建立的中转会话不会自动变成点对点会话。
- 工具识别到的远端 IP 与当前实际网络不一致：检查最新打洞日志。切换网络后通常要重新尝试一次连接，才能学习新地址。
- 排除所有远端应用流量需要按进程的系统级路由方案；本工具实现的是从 RustDesk 日志学习目标地址后按 IP 绕过 TUN。
- 适配当前日志格式；RustDesk 未来改变格式时，可能需要更新解析规则。

## 验证情况

Linux：已在当前 Ubuntu + Clash Verge Rev/Mihomo 环境安装运行，验证远端路由走物理网卡，并观察到到远端公网 IP 的 RustDesk TCP 连接。

跨平台核心：测试覆盖主控/被控端事件、IPv4/IPv6、公私网过滤、过期事件、日志轮换和半行读取、自定义脚本保留、无变化不重载、订阅重建后的恢复、API 失败回滚和卸载。

Windows / macOS：提供完整功能、安装/卸载和登录启动脚本；当前没有这两个系统的实机环境，尚未验证原生系统集成。

页面：已用本机 Chrome 验证桌面与窄屏布局，验证添加、行内切换、删除、搜索和帮助交互。修改交互使用模拟接口，避免测试期间更改用户应用路由；真实接口的规则写入、回滚和连接断开范围另有隔离测试。

实现依据：

- [Mihomo TUN 排除路由配置](https://wiki.metacubex.one/config/inbound/tun/#route-exclude-address)
- [RustDesk 主控端日志源码](https://github.com/rustdesk/rustdesk/blob/master/src/client.rs)
- [RustDesk 被控端打洞日志源码](https://github.com/rustdesk/rustdesk/blob/master/src/rendezvous_mediator.rs)
- [Clash Verge 平台数据目录和 socket 实现](https://github.com/clash-verge-rev/clash-verge-rev/blob/dev/src-tauri/src/utils/dirs.rs)
- [RustDesk 各平台日志位置](https://github.com/rustdesk/rustdesk/wiki/FAQ)


2.0.1 安装器测试：已用 Linux 上的 PowerShell 7 解析脚本，并以临时目录和模拟 Conda 可执行文件验证发现路径、包含空格的参数、独立环境创建参数、Python/PyYAML 校验和环境复用；不等于 Windows 原生端到端测试。

- [Conda 指定路径和 Python 版本创建环境](https://docs.conda.io/projects/conda/en/stable/commands/create.html)


### 2.0.2：Conda 下载源失败的处理

若安装输出已经找到 `conda.exe`，但出现 `CondaHTTPError` / `WinError 10051`，表示依赖下载链路失败，通常无需重装 Anaconda。旧版本直接沿用 `.condarc` 的镜像；2.0.2 使用独立的 HTTPS 频道参数并自动重试备用源。

每次尝试临时设置较短连接超时和较少的下载重试，结束后恢复原进程环境。全局 Conda 配置保持不变。该机制只能更换下载源；如果所有目标都网络不可达，仍需检查 Windows 网络或代理设置。

默认重试顺序：

1. `https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge`
2. `https://conda.anaconda.org/conda-forge`

支持 `-CondaChannel` 自定义 HTTPS 源，或 `-UseConfiguredChannels` 只使用原有配置。二者不能同时指定。已创建且通过校验的运行环境直接复用，不会每次安装都重新下载。

参考：[清华 Conda 镜像帮助](https://mirrors.tuna.tsinghua.edu.cn/help/anaconda/)、[Conda create 的频道参数](https://docs.conda.io/projects/conda/en/stable/commands/create.html)。

### 网站域名分流

管理页的“网站域名分流”支持精确域名与域名及子域名匹配，可选择 DIRECT 或当前代理组。可以粘贴网址，页面会提取域名。域名规则优先于应用规则，对所有应用生效；同类规则从上到下匹配，新规则置顶。它不按 URL 路径或标签页区分流量，第三方资源域名需要单独设置。修改后重新建立网站连接生效。

### Windows 应用图标

Windows 管理页通过系统自带的 Windows PowerShell 和 System.Drawing 从 EXE 提取图标，不执行目标应用，也无需额外 Python 依赖。优先使用 Clash 提供的进程完整路径；手动添加的进程名称会尝试匹配运行进程或系统 App Paths 注册项。按路径匹配可区分同名 EXE。结果缓存约一分钟；文件不可访问、没有图标或查找失败时保留占位图标。


### WebDAV 规则同步

管理页提供 WebDAV 地址、账号、应用专用密码、远程目录与配置档设置，支持坚果云预设及 Nextcloud、群晖、自定义服务。先保存设置，再测试连接。多台设备填写相同目录和配置档，即可上传或下载规则。快照文件位于 `<WebDAV 服务地址>/<远程目录>/<配置档>/policies-v1.json`，默认目录为 `flow-sync/default`。使用独立 Flow 格式，不读取或覆盖 CC Switch 的数据库。

- 同步应用规则和域名规则。Clash 路径、控制器密钥、RustDesk TUN 绕过开关、学习到的 IP、应用图标、流量与连接记录不上传。规则中已有的应用完整路径会随规则上传；跨操作系统时需自行调整进程名称或路径。
- 上传与下载前展示远程摘要；下载会替换本机规则，原配置备份到运行数据目录的 `policies-before-sync.json`。缺少同名代理组时，下载弹窗可将远程代理组映射为本机已有代理组；所有缺失项均选择后才允许下载。映射同时作用于应用和域名规则，不修改远程文件。若本机无代理组，需先加载 Clash 订阅或配置。远程 RustDesk 代理规则会按既有校验关闭冲突的本机 TUN 绕过。已有连接不自动断开。
- 可选“规则修改后自动上传”，每 10 秒检查一次，不自动下载。新配置档可直接上传；远程已有不同内容或其他设备修改远程后，自动上传停止覆盖并显示冲突，需要手动查看摘要后下载或确认上传。
- 使用 ETag 与条件 PUT 防止覆盖并发修改。无强 ETag 的服务器允许创建新配置档和下载，但拒绝覆盖已有不同规则。
- 账号密码保存在运行数据目录 `webdav.json`，密码不返回浏览器、不随规则上传。POSIX 文件权限为 0600；Windows 使用用户数据目录的继承权限。留空密码保留原密码。使用 HTTPS 和服务商应用专用密码；HTTP 会明文传输凭据。

此交互参考 [CC Switch WebDAV 设置](https://github.com/farion1231/cc-switch/blob/main/src/components/settings/WebdavSyncSection.tsx)，数据格式独立。
