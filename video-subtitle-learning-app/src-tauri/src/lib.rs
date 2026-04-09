use std::{
    fs::{self, OpenOptions},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::{Manager, RunEvent};

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 8000;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[derive(Default)]
struct BackendState(Mutex<Option<Child>>);

#[tauri::command]
fn copy_export_file(source_path: String, target_path: String) -> Result<String, String> {
    let source = PathBuf::from(&source_path);
    let target = PathBuf::from(&target_path);

    if !source.exists() {
        return Err(format!("Export source file not found: {}", source.display()));
    }

    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create export directory {}: {error}", parent.display()))?;
    }

    if source == target {
        return Ok(target.display().to_string());
    }

    fs::copy(&source, &target)
        .map_err(|error| format!("Failed to copy export file to {}: {error}", target.display()))?;

    Ok(target.display().to_string())
}

fn backend_address() -> SocketAddr {
    format!("{BACKEND_HOST}:{BACKEND_PORT}")
        .parse()
        .expect("invalid backend socket address")
}

fn is_backend_running() -> bool {
    TcpStream::connect_timeout(&backend_address(), Duration::from_millis(250)).is_ok()
}

fn wait_for_backend_ready() -> bool {
    for _ in 0..40 {
        if is_backend_running() {
            return true;
        }
        thread::sleep(Duration::from_millis(250));
    }
    false
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri should live inside the project root")
        .to_path_buf()
}

fn executable_root() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.to_path_buf()))
        .unwrap_or_else(project_root)
}

fn resolve_app_root() -> PathBuf {
    if cfg!(debug_assertions) {
        project_root()
    } else {
        executable_root()
    }
}

fn python_candidates(app_root: &Path) -> Vec<PathBuf> {
    let mut candidates = vec![
        app_root.join("runtime").join("python").join("python.exe"),
        app_root.join("runtime").join("python").join("bin").join("python"),
        app_root.join(".venv").join("Scripts").join("python.exe"),
        app_root.join(".venv").join("bin").join("python"),
        app_root.join("python").join("python.exe"),
    ];

    if let Ok(env_python) = std::env::var("VIDEO_SUBTITLE_PYTHON") {
        candidates.insert(0, PathBuf::from(env_python));
    }

    candidates
}

fn resolve_python_executable(app_root: &Path) -> Result<PathBuf, String> {
    python_candidates(app_root)
        .into_iter()
        .find(|candidate| candidate.exists())
        .ok_or_else(|| {
            format!(
                "No Python runtime found for the backend sidecar. Checked under {}",
                app_root.display()
            )
        })
}

fn prepare_log_file(app_root: &Path, file_name: &str) -> Option<std::fs::File> {
    let logs_dir = app_root.join("data").join("logs");
    fs::create_dir_all(&logs_dir).ok()?;
    OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(logs_dir.join(file_name))
        .ok()
}

fn spawn_backend(app_root: &Path) -> Result<Child, String> {
    let python = resolve_python_executable(app_root)?;
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("uvicorn")
        .arg("backend.app.main:app")
        .arg("--host")
        .arg(BACKEND_HOST)
        .arg("--port")
        .arg(BACKEND_PORT.to_string())
        .current_dir(app_root)
        .env("VIDEO_SUBTITLE_APP_ROOT", app_root)
        .env("VIDEO_SUBTITLE_PORTABLE_MODE", "1")
        .env("PYTHONUTF8", "1");

    if cfg!(debug_assertions) {
        command.stdout(Stdio::inherit()).stderr(Stdio::inherit());
    } else {
        if let Some(stdout_log) = prepare_log_file(app_root, "backend-sidecar.log") {
            if let Ok(stderr_log) = stdout_log.try_clone() {
                command.stdout(Stdio::from(stdout_log)).stderr(Stdio::from(stderr_log));
            } else {
                command.stdout(Stdio::from(stdout_log)).stderr(Stdio::null());
            }
        } else {
            command.stdout(Stdio::null()).stderr(Stdio::null());
        }
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
        .spawn()
        .map_err(|error| format!("Failed to spawn backend sidecar: {error}"))
}

fn ensure_backend_running(state: &BackendState, app_root: &Path) -> Result<(), String> {
    if is_backend_running() {
        return Ok(());
    }

    let child = spawn_backend(app_root)?;
    {
        let mut guard = state
            .0
            .lock()
            .map_err(|_| "Failed to lock backend process state".to_string())?;
        *guard = Some(child);
    }

    if wait_for_backend_ready() {
        return Ok(());
    }

    shutdown_backend(state);
    Err("Backend sidecar did not become ready in time.".to_string())
}

fn shutdown_backend(state: &BackendState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let backend_state = BackendState::default();
    let app_root = resolve_app_root();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![copy_export_file])
        .setup({
            let app_root = app_root.clone();
            move |app| {
                ensure_backend_running(&backend_state, &app_root)
                    .map_err(|message| -> Box<dyn std::error::Error> { message.into() })?;
                app.manage(backend_state);
                Ok(())
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            let state = app_handle.state::<BackendState>();
            shutdown_backend(&state);
        }
    });
}
