# Flow 应用流量管理

基于 Clash Verge Rev / Mihomo，按应用和域名选择直连、代理组或沿用订阅规则。支持 Windows、Linux、macOS，当前版本 **2.1.1**。

- 按进程名称或完整路径分流，查看连接、流量和代理链。
- 设置域名规则，优先于应用规则。
- 从 RustDesk 日志学习远端地址，按需绕过 TUN。
- 通过 WebDAV 手动同步规则，或在修改后自动上传。
- 在应用内控制后台常驻及当前用户登录自启。

## 安装与使用

从仓库 Releases 下载对应平台的安装包：Windows 使用 EXE / MSI，Linux 使用 AppImage / DEB，macOS 使用 DMG。

1. 启动 Clash Verge Rev，启用规则模式；需要接管应用流量时启用 TUN。
2. 安装并打开 Flow，首次启动自动识别 Clash 配置目录。
3. 在“应用分流”中选择应用策略，或添加应用、域名规则。

Windows 需要 WebView2 Runtime，并在 Clash 中启用本机 TCP API，例如 `external-controller: 127.0.0.1:9097`。Flow 不包含代理内核或订阅。

默认管理地址为 [http://127.0.0.1:17891/](http://127.0.0.1:17891/)，仅供本机访问。策略修改通常在新连接中生效；编辑时可选择断开该应用已有连接。普通 DIRECT 仍可能经过 TUN；RustDesk 地址排除才是绕过 TUN。

**从旧版升级：**先关闭旧后台并停用旧自启，再打开新版。否则 App 可能复用旧后台，显示旧版页面。保留数据目录即可沿用配置。

## 代码结构

- `script/`：Python 后端、源码桌面入口和打包脚本。
- `src-tauri/`：Rust 桌面程序与安装包配置。
- `web/`：管理页面。
- `desktop/`：源码桌面入口使用的图标和启动页面。

## 本地构建

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

保留 Python 桌面入口，便于调试：

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

## 自动构建

`.github/workflows/desktop.yml` 构建 Windows x64、Linux x64、macOS Intel / Apple Silicon。推送 `main` / `master` 或版本标签后构建并发布；PR 仅保存产物。手动运行可通过 `publish_release` 控制是否发布。

仅发布各平台安装包及 SHA-256 校验文件。流水线检查版本一致性和标签对应提交，先上传至草稿，再正式发布；已发布版本禁止覆盖，更新时需提升版本号。

发布前保持 `script/runtime_paths.py`、`package.json`、`src-tauri/Cargo.toml` 和 `src-tauri/tauri.conf.json` 中的版本一致。分发包暂未配置代码签名或 macOS 公证；跨平台构建成功不代表各系统功能均已实机验证。
