// AgentTrace Desktop — Tauri 入口
// 轻量模式：Rust 只负责窗口管理和 Python sidecar 进程

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Stdio;
use std::sync::{Arc, Mutex};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, RunEvent,
};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};

#[derive(serde::Serialize, Clone)]
struct PythonLog {
    level: String,
    message: String,
    timestamp: String,
}

struct AppState {
    python_child: Arc<tokio::sync::Mutex<Option<Child>>>,
    logs: Arc<Mutex<Vec<PythonLog>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            python_child: Arc::new(tokio::sync::Mutex::new(None)),
            logs: Arc::new(Mutex::new(Vec::with_capacity(500))),
        }
    }
}

// ─── Tauri Commands ──────────────────────────────────────────────────────────

#[tauri::command]
fn get_python_logs(state: tauri::State<'_, AppState>) -> Vec<PythonLog> {
    state.logs.lock().unwrap().clone()
}

#[tauri::command]
async fn restart_python_server(app: tauri::AppHandle) -> Result<(), String> {
    stop_python_server(&app).await;
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        start_python_server(handle).await;
    });
    Ok(())
}

#[tauri::command]
fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

// ─── Python Sidecar Management ───────────────────────────────────────────────

async fn stop_python_server(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        let mut guard = state.python_child.lock().await;
        if let Some(mut child) = guard.take() {
            drop(guard);
            #[cfg(unix)]
            {
                if let Some(id) = child.id() {
                    unsafe {
                        libc::kill(id as i32, libc::SIGTERM);
                    }
                }
            }
            #[cfg(windows)]
            {
                let _ = child.kill().await;
            }
            let _ = tokio::time::timeout(
                tokio::time::Duration::from_secs(5),
                child.wait(),
            )
            .await;
        }
    }
}

/// 自动检测项目根目录，用于设置 PYTHONPATH
fn detect_project_root() -> Option<std::path::PathBuf> {
    // 1. 尝试从可执行文件路径推断（开发模式）
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent()?;
        // 向上遍历最多 5 层
        for _ in 0..5 {
            // 检查是否包含 pyproject.toml 和 src/agent_trace
            if dir.join("pyproject.toml").exists()
                && dir.join("src").join("agent_trace").exists()
            {
                return Some(dir.to_path_buf());
            }
            dir = dir.parent()?;
        }
    }
    // 2. 尝试从 CARGO_MANIFEST_DIR 推断
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let dir = std::path::PathBuf::from(manifest);
        let root = dir.parent()?;
        if root.join("pyproject.toml").exists() {
            return Some(root.to_path_buf());
        }
    }
    None
}

async fn start_python_server(handle: tauri::AppHandle) {
    let python = which_python().await;

    // 自动检测 PYTHONPATH
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "agent_trace.web.server"])
        .env("AGENTTRACE_WEB_PORT", "18765")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(root) = detect_project_root() {
        let src_dir = root.join("src");
        let pythonpath = format!("{}:{}", src_dir.display(), root.display());
        cmd.env("PYTHONPATH", &pythonpath);
        println!("[AgentTrace] Auto-detected project root: {}", root.display());
        println!("[AgentTrace] PYTHONPATH set to: {}", pythonpath);
    }

    let mut child = match cmd.spawn()
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to start Python server: {e}");
            return;
        }
    };

    let stdout = child.stdout.take().expect("Failed to capture stdout");
    let stderr = child.stderr.take().expect("Failed to capture stderr");

    {
        let state = handle.state::<AppState>();
        let mut guard = state.python_child.lock().await;
        *guard = Some(child);
    }

    let stdout_reader = BufReader::new(stdout);
    let stderr_reader = BufReader::new(stderr);

    let handle_stdout = handle.clone();
    let stdout_task = tauri::async_runtime::spawn(async move {
        let state = handle_stdout.state::<AppState>();
        let mut lines = stdout_reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            println!("[Python] {}", line);
            let log = PythonLog {
                level: "INFO".to_string(),
                message: line,
                timestamp: chrono::Local::now().format("%H:%M:%S").to_string(),
            };
            let _ = handle_stdout.emit("python-log", log.clone());
            let mut logs = state.logs.lock().unwrap();
            if logs.len() >= 500 {
                logs.remove(0);
            }
            logs.push(log);
        }
    });

    let handle_stderr = handle.clone();
    let stderr_task = tauri::async_runtime::spawn(async move {
        let state = handle_stderr.state::<AppState>();
        let mut lines = stderr_reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            eprintln!("[Python] {}", line);
            let log = PythonLog {
                level: "ERROR".to_string(),
                message: line,
                timestamp: chrono::Local::now().format("%H:%M:%S").to_string(),
            };
            let _ = handle_stderr.emit("python-log", log.clone());
            let mut logs = state.logs.lock().unwrap();
            if logs.len() >= 500 {
                logs.remove(0);
            }
            logs.push(log);
        }
    });

    let _ = tokio::join!(stdout_task, stderr_task);
}

async fn which_python() -> String {
    for cmd in ["python3", "python", "py"] {
        if Command::new(cmd).arg("--version").output().await.is_ok() {
            return cmd.to_string();
        }
    }
    "python3".to_string()
}

// ─── Tray Helpers ────────────────────────────────────────────────────────────

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "windows")]
        {
            let _ = window.set_skip_taskbar(false);
        }
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
        #[cfg(target_os = "windows")]
        {
            let _ = window.set_skip_taskbar(true);
        }
    }
}

// ─── Main ────────────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .build(),
        )
        .manage(AppState::default())
        .setup(|app| {
            // 启动 Python FastAPI sidecar
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                start_python_server(handle).await;
            });

            // 创建托盘菜单
            let show_item = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
            let hide_item = MenuItem::with_id(app, "hide", "隐藏窗口", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &hide_item, &quit_item])?;

            let _tray = TrayIconBuilder::new()
                .tooltip("AgentTrace")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_tray_icon_event(|_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        ..
                    } = event
                    {
                        // 左键点击时如果窗口未显示则显示窗口
                        // macOS 上系统会同时弹出菜单，两者并存
                    }
                })
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "show" => show_main_window(app),
                        "hide" => hide_main_window(app),
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // 点击关闭时最小化到托盘，不退出
                api.prevent_close();
                let _ = window.hide();
                #[cfg(target_os = "windows")]
                {
                    let _ = window.set_skip_taskbar(true);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_python_logs,
            restart_python_server,
            get_app_version,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                tauri::async_runtime::block_on(async {
                    stop_python_server(app_handle).await;
                });
            }
        });
}
