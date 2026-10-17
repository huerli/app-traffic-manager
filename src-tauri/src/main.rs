#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{env, fs::{self, OpenOptions}, io::{BufRead, BufReader, Write}, path::PathBuf, process::{Child, Command, Stdio}, sync::Mutex};
use tauri::Manager;

struct Backend(Mutex<Option<Child>>);
fn data_dir() -> PathBuf {
    if let Ok(value) = env::var("FLOW_DATA_DIR") { return PathBuf::from(value); }
    if cfg!(target_os="windows") { PathBuf::from(env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into())).join("RustDeskClashBypass") }
    else if cfg!(target_os="macos") { PathBuf::from(env::var("HOME").unwrap_or_else(|_| ".".into())).join("Library/Application Support/RustDeskClashBypass") }
    else { PathBuf::from(env::var("XDG_DATA_HOME").unwrap_or_else(|_| format!("{}/.local/share", env::var("HOME").unwrap_or_else(|_| ".".into())))).join("rustdesk-clash-bypass") }
}
fn minimize_on_close() -> bool {
    let path = data_dir().join("desktop.json");
    fs::read_to_string(path).ok()
        .and_then(|contents| serde_json::from_str::<serde_json::Value>(&contents).ok())
        .and_then(|value| value["close_action"].as_str().map(str::to_owned))
        .as_deref() == Some("minimize")
}
fn launch_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let data = data_dir();
    fs::create_dir_all(&data).map_err(|e| e.to_string())?;
    // Tauri removes the target suffix and installs external binaries beside the app.
    let name = format!("flow-backend{}", env::consts::EXE_SUFFIX);
    let sidecar = env::current_exe().map_err(|e| e.to_string())?.with_file_name(&name);
    let sidecar = if sidecar.is_file() { sidecar } else {
        app.path().resolve(&name, tauri::path::BaseDirectory::Resource).map_err(|e| e.to_string())?
    };
    let log = OpenOptions::new().create(true).append(true).open(data.join("tauri.log")).map_err(|e| e.to_string())?;
    let mut command = Command::new(&sidecar);
    command.args(["--service", "--data-dir", data.to_string_lossy().as_ref(), "--parent-pid", &std::process::id().to_string()])
        .env("FLOW_TAURI", "1").stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::from(log));
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let mut child = command.spawn().map_err(|e| format!("无法启动后台服务 {}：{e}", sidecar.display()))?;
    let stdout = child.stdout.take().ok_or("无法读取后台启动状态")?;
    app.state::<Backend>().0.lock().unwrap().replace(child);
    let mut line = String::new();
    BufReader::new(stdout).read_line(&mut line).map_err(|e| e.to_string())?;
    let ready: serde_json::Value = serde_json::from_str(&line).map_err(|_| "后台服务启动失败，请查看数据目录中的 tauri.log 和 desktop.log。")?;
    let url = ready["url"].as_str().ok_or("后台未返回页面地址")?;
    let url: tauri::Url = url.parse().map_err(|_| "后台页面地址无效")?;
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") { return Err("后台页面必须使用本机地址".into()); }
    app.get_webview_window("main").ok_or("找不到主窗口")?.navigate(url).map_err(|e| e.to_string())
}
fn main() {
    let result = tauri::Builder::default().manage(Backend(Mutex::new(None)))
    .on_window_event(|window, event| {
        if window.label() == "main" && minimize_on_close() {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.minimize();
            }
        }
    }).setup(|app| {
        let handle = app.handle().clone();
        std::thread::spawn(move || {
            if let Err(error) = launch_backend(&handle) {
                if let Ok(mut log) = OpenOptions::new().create(true).append(true).open(data_dir().join("tauri.log")) { let _ = writeln!(log, "{error}"); }
                if let Some(window) = handle.get_webview_window("main") {
                    let message = serde_json::to_string(&format!("Flow 启动失败\n\n{error}")).unwrap();
                    let _ = window.eval(format!("document.body.textContent={message}"));
                }
            }
        });
        Ok(())
    }).build(tauri::generate_context!());
    match result {
        Ok(app) => app.run(|_, _| {}),
        Err(error) => {
            let data = data_dir(); let _ = fs::create_dir_all(&data);
            if let Ok(mut log) = OpenOptions::new().create(true).append(true).open(data.join("tauri.log")) { let _ = writeln!(log, "{error}"); }
        }
    }
}
