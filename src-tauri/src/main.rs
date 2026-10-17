#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{env, fs, path::PathBuf, process::{Child, Command, Stdio}, sync::Mutex};
use tauri::{Manager, RunEvent};

struct Backend(Mutex<Option<Child>>);
fn data_dir() -> PathBuf {
    if let Ok(value) = env::var("FLOW_DATA_DIR") { return PathBuf::from(value); }
    if cfg!(target_os="windows") { PathBuf::from(env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into())).join("RustDeskClashBypass") }
    else if cfg!(target_os="macos") { PathBuf::from(env::var("HOME").unwrap_or_else(|_| ".".into())).join("Library/Application Support/RustDeskClashBypass") }
    else { PathBuf::from(env::var("XDG_DATA_HOME").unwrap_or_else(|_| format!("{}/.local/share", env::var("HOME").unwrap_or_else(|_| ".".into())))).join("rustdesk-clash-bypass") }
}
fn sidecar_name() -> String {
    let target = if cfg!(target_os="windows") { "x86_64-pc-windows-msvc" } else if cfg!(target_os="macos") {
        if cfg!(target_arch="aarch64") { "aarch64-apple-darwin" } else { "x86_64-apple-darwin" }
    } else { "x86_64-unknown-linux-gnu" };
    format!("binaries/flow-backend-{target}{}", if cfg!(target_os="windows") { ".exe" } else { "" })
}
fn launch_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let data = data_dir(); fs::create_dir_all(&data).map_err(|e| e.to_string())?;
    let sidecar = app.path().resolve(sidecar_name(), tauri::path::BaseDirectory::Resource).map_err(|e| e.to_string())?;
    let mut command = Command::new(sidecar);
    command.args(["--service", "--data-dir", data.to_string_lossy().as_ref()]).env("FLOW_TAURI", "1").stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    let child = command.spawn().map_err(|e| format!("无法启动 Flow 后台服务：{e}"))?;
    app.state::<Backend>().0.lock().unwrap().replace(child);
    Ok(())
}
fn main() {
    tauri::Builder::default().manage(Backend(Mutex::new(None))).setup(|app| { launch_backend(app.handle()).map_err(|e| Box::<dyn std::error::Error>::from(std::io::Error::other(e)))?; Ok(()) })
      .build(tauri::generate_context!()).expect("error while running Flow").run(|app, event| {
        if let RunEvent::Exit = event { if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() { let _ = child.kill(); } }
      });
}
