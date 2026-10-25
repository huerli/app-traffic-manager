# Flow 应用流量管理

## 快速运行

先启动 Clash Verge Rev。Linux 安装 DEB / RPM 包后，直接运行：

```bash
flow-traffic-manager
```

Linux / macOS 从源码运行（在项目根目录执行，首次自动创建独立环境并安装 Python 依赖）：

```bash
./run.sh
```

Windows 从源码运行：双击项目根目录的 `run.bat`，或在终端执行：

```bat
.\run.bat
```

首次自动创建独立环境并安装依赖；需先安装 Python 3.10+ 和 WebView2 Runtime，并启动 Clash Verge Rev。

基于 Clash Verge Rev / Mihomo，按应用、域名和 IP/CIDR 选择直连、代理组、具体代理节点或沿用订阅规则。支持 Windows、Linux、macOS，当前版本 **2.1.6**。

- 按进程名称或完整路径分流，查看连接、流量和代理链。
- 设置域名与 IPv4 / IPv6 CIDR 规则，优先于应用规则；IPv4 无掩码时，末位 .0 自动补 /24，其他地址补 /32。
- 选择直连的 IPv4 / IPv6 CIDR 规则会同时从 TUN 路由中排除，流量直接经过物理网卡；域名与应用规则无法按此绕过 TUN。
- 代理目标缺失时自动失能对应规则，目标恢复后自动启用。
- 关闭桌面窗口可隐藏至系统托盘，通过托盘菜单恢复或退出；Linux 源码版支持 AppIndicator 托盘。
- 从 RustDesk 日志学习远端地址，按需绕过 TUN；直连 IP/CIDR 规则复用同一套地址排除。
- 通过 WebDAV 手动同步规则，或在修改后自动上传。
- 在应用内控制后台常驻及当前用户登录自启。

## 安装与使用

从仓库 Releases 下载对应平台的安装包：Windows 使用 EXE / MSI，Linux 使用 AppImage / DEB，macOS 使用 DMG。

1. 启动 Clash Verge Rev，启用规则模式；需要接管应用流量时启用 TUN。
2. 安装并打开 Flow，首次启动自动识别 Clash 配置目录。
3. 在“应用分流”中选择应用策略，或添加应用、域名规则。

Windows 需要 WebView2 Runtime，并在 Clash 中启用本机 TCP API，例如 `external-controller: 127.0.0.1:9097`。Flow 不包含代理内核或订阅。

默认管理地址为 [http://127.0.0.1:17891/](http://127.0.0.1:17891/)，仅供本机访问。策略修改通常在新连接中生效；编辑时可选择断开该应用已有连接。应用与域名的普通 DIRECT 仍可能经过 TUN；RustDesk 地址和直连 IP/CIDR 规则使用地址排除绕过 TUN，流量直接经过物理网卡。域名规则无法排除，因为 TUN 路由只识别目的 IP。

**从旧版升级：**先关闭旧后台并停用旧自启，再打开新版。否则 App 可能复用旧后台，显示旧版页面。保留数据目录即可沿用配置。

选择代理组时沿用 Clash 当前选择的节点；选择具体节点时，该规则固定使用该节点。规则对所有订阅生效，订阅缺少目标组或节点时会跳过对应规则，页面会提示缺失目标。WebDAV 下载时可将缺失目标映射到本机代理组。

## 代码结构

- `script/`：Python 后端、源码桌面入口和打包脚本。
- `src-tauri/`：Rust 桌面程序与安装包配置。
- `web/`：管理页面。
- `desktop/`：源码桌面入口使用的图标和启动页面。

## 本地构建

### 一键编译

在对应平台的项目根目录执行，无需手动激活 Python 环境：

| 平台 | 命令 | 产物 |
| --- | --- | --- |
| Windows | `.\build-windows.bat`（也可双击） | EXE / MSI |
| Linux | `./build-linux.sh` | DEB / RPM / AppImage |
| macOS | `./build-macos.sh` | APP / DMG |

脚本会自动创建构建环境、安装 Python 和 npm 项目依赖、重新打包后端并编译桌面程序。macOS 自动识别 Intel / Apple Silicon；Python 与 Rust 架构需一致。首次构建需要联网。

预先安装 Python 3.10+、Node.js（含 npm）及 Rust（Cargo）。Windows 还需 Visual Studio C++ Build Tools（桌面 C++ 工作负载）和 Windows SDK；macOS 执行 `xcode-select --install` 安装命令行工具；Linux 的系统依赖见下方命令，并需 `pkg-config` 和 `python3-venv`。

可追加 `--check` 仅检查平台、工具及部分系统依赖。此检查不替代完整编译及平台 SDK 检查。安装包输出在 `src-tauri/target/<target>/release/bundle/`。

### 手动编译

桌面程序使用 Tauri v2 + Rust，Python 后端通过 PyInstaller 打包。需安装 Node.js、Rust 和 Python 3.10+，在目标操作系统及对应 CPU 架构上构建。

```bash
python -m venv .build-venv
```

激活环境：Windows PowerShell 执行 `.\.build-venv\Scripts\Activate.ps1`；Linux / macOS 执行 `source .build-venv/bin/activate`。

```bash
python -m pip install -r requirements.txt pyinstaller==6.22.3
npm install --no-package-lock
python script/build-sidecar.py
npm run tauri:build
```

Windows 需要 Visual Studio C++ Build Tools 和 Windows SDK；macOS 需要 Xcode Command Line Tools。Ubuntu / Debian 的系统依赖：

```bash
sudo apt install build-essential libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf libgtk-3-dev
```

安装包输出到 `src-tauri/target/release/bundle/`。指定 `--target` 时输出到 `src-tauri/target/<target>/release/bundle/`，例如 Windows x64：

```bash
npm run tauri:build -- --target x86_64-pc-windows-msvc --bundles nsis,msi
```

## 源码运行

Linux / macOS 一键启动，自动安装 Python 依赖，不需要激活 Conda：

```bash
./run.sh
```

需要 Python 3 和 venv；Ubuntu / Debian 若缺少 venv，先执行 `sudo apt install python3-venv`。Linux 脚本使用系统 Python 并启用系统包访问，以加载 GTK。

Windows 推荐双击 `run.bat` 自动准备环境；也可在已安装 Python 的终端中手动执行：

```bash
python -m pip install -r requirements-desktop.txt
python script/open-manager.py
```

Linux Python 桌面入口另需 `python3-gi`、`python3-gi-cairo`、`gir1.2-gtk-3.0`、`gir1.2-webkit2-4.1`，虚拟环境需能访问系统包。

安装和卸载均使用各平台的安装包或系统应用管理功能。

## 数据与排错

| 系统    | 数据目录                                              |
| ------- | ----------------------------------------------------- |
| Windows | `%LOCALAPPDATA%\RustDeskClashBypass`                |
| Linux   | `~/.local/share/rustdesk-clash-bypass`              |
| macOS   | `~/Library/Application Support/RustDeskClashBypass` |

目录名沿用旧版以兼容配置。`settings.json` 保存 Clash 路径，`policies.json` 保存规则，`webdav.json` 保存同步设置和凭据，`desktop.json` 保存窗口关闭行为。启动问题查看 `tauri.log`、`desktop.log`；源码后台还可查看 `bypass.log`。

- 页面版本不符或端口被占用：检查旧版后台和登录自启。
- Clash 连接失败：检查运行状态、规则模式及本机 API；401 通常表示 API 密钥不匹配。
- 首次识别失败：检查 Clash 配置目录是否包含 `clash-verge.yaml` 和 `profiles/Script.js`，在 `settings.json` 中指定 `clash_dir` 后重启。
- WebDAV 同步应用和域名规则，不同步 Clash 密钥、学习到的 IP 或连接记录。下载会替换本机规则并生成 `policies-before-sync.json` 备份；建议使用 HTTPS 和应用专用密码。

### macOS 提示“已损坏，无法打开”

浏览器下载的应用会带有隔离标记，旧构建还可能缺少整个 `.app` 的完整签名。新构建默认使用 ad-hoc 本地签名，CI 会校验应用及后端的签名；该签名没有 Apple 开发者身份，也未经过公证，首次打开仍可能需要在“系统设置 → 隐私与安全性”中允许。

已安装的旧版若出现“已损坏”，确认应用来自本项目可信构建后，可在终端执行以下命令，仅修复这一份应用：

```bash
codesign --force --sign - "/Applications/Flow Traffic Manager.app"
codesign --verify --deep --strict --verbose=2 "/Applications/Flow Traffic Manager.app"
xattr -dr com.apple.quarantine "/Applications/Flow Traffic Manager.app"
```

构建配置未启用 hardened runtime，以便 ad-hoc 签名的 PyInstaller 后端加载打包的 Python 动态库。正式签名与公证发布时，需配置 Developer ID、重新启用 hardened runtime，并为 Python 后端配置匹配的签名及动态库加载权限。

## 自动构建

`.github/workflows/desktop.yml` 构建 Windows x64、Linux x64、macOS Intel / Apple Silicon。仅推送 `v*` 版本标签时自动构建并发布，普通分支推送和 PR 不触发。保留手动运行入口，可通过 `publish_release` 控制是否发布。

版本号更新并提交后，执行 `git tag v<版本号>` 和 `git push origin v<版本号>` 触发发布，标签必须与代码版本一致。

仅发布各平台安装包及 SHA-256 校验文件。流水线检查版本一致性和标签对应提交，先上传至草稿，再正式发布；已发布版本禁止覆盖，更新时需提升版本号。

发布前保持 `script/runtime_paths.py`、`package.json`、`src-tauri/Cargo.toml` 和 `src-tauri/tauri.conf.json` 中的版本一致。macOS 分发包使用 ad-hoc 签名，暂未配置 Developer ID 签名和公证；Windows 分发包暂未配置代码签名。跨平台构建成功不代表各系统功能均已实机验证。
