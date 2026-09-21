//! Sidecar lifecycle manager for the DeepTutor Python backend.
//!
//! Spawns the backend process, polls the health endpoint until ready,
//! provides the resolved backend URL to the frontend via Tauri IPC,
//! and cleanly terminates the process when the application exits.

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

pub const DEFAULT_PORT: u16 = 8001;
pub const HEALTH_CHECK_TIMEOUT_SECS: u64 = 30;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendInfo {
    pub url: String,
    pub port: u16,
    pub is_ready: bool,
    pub error: Option<String>,
}

pub struct SidecarManager {
    child: Arc<Mutex<Option<Child>>>,
    info: Arc<Mutex<BackendInfo>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
            info: Arc::new(Mutex::new(BackendInfo {
                url: format!("http://127.0.0.1:{}", DEFAULT_PORT),
                port: DEFAULT_PORT,
                is_ready: false,
                error: None,
            })),
        }
    }

    /// Resolve path to the backend executable or script.
    fn resolve_backend_executable(app_handle: &AppHandle) -> Option<PathBuf> {
        // 1. Check packaged sidecar location in resources
        if let Ok(resource_dir) = app_handle.path().resource_dir() {
            let bundled_exe = resource_dir.join("bin").join("deeptutor-backend.exe");
            if bundled_exe.exists() {
                return Some(bundled_exe);
            }
        }

        // 2. Check current working directory / dev environment
        let dev_exe = PathBuf::from("dist").join("deeptutor-backend").join("deeptutor-backend.exe");
        if dev_exe.exists() {
            return Some(dev_exe);
        }

        None
    }

    /// Start the Python backend process and begin health check polling.
    pub fn start(&self, app_handle: AppHandle) {
        let child_arc = Arc::clone(&self.child);
        let info_arc = Arc::clone(&self.info);

        tokio::spawn(async move {
            let port = DEFAULT_PORT;
            let backend_exe = Self::resolve_backend_executable(&app_handle);

            let spawn_result = if let Some(exe) = backend_exe {
                Command::new(exe)
                    .arg("serve")
                    .arg("--port")
                    .arg(port.to_string())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped())
                    .spawn()
            } else {
                // Fallback to local python in dev mode
                Command::new("python")
                    .arg("-m")
                    .arg("deeptutor")
                    .arg("serve")
                    .arg("--port")
                    .arg(port.to_string())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped())
                    .spawn()
            };

            match spawn_result {
                Ok(child) => {
                    {
                        let mut lock = child_arc.lock().unwrap();
                        *lock = Some(child);
                    }

                    // Poll health endpoint
                    let health_url = format!("http://127.0.0.1:{}/api/health", port);
                    let client = reqwest::Client::builder()
                        .timeout(Duration::from_secs(2))
                        .build()
                        .unwrap_or_default();

                    let start_time = std::time::Instant::now();
                    let mut ready = false;

                    while start_time.elapsed() < Duration::from_secs(HEALTH_CHECK_TIMEOUT_SECS) {
                        tokio::time::sleep(Duration::from_millis(500)).await;
                        if let Ok(resp) = client.get(&health_url).send().await {
                            if resp.status().is_success() {
                                ready = true;
                                break;
                            }
                        }
                    }

                    let mut info = info_arc.lock().unwrap();
                    if ready {
                        info.is_ready = true;
                        info.url = format!("http://127.0.0.1:{}", port);
                        info.port = port;
                        info.error = None;
                    } else {
                        info.is_ready = false;
                        info.error = Some("Backend health check timed out".to_string());
                    }
                }
                Err(err) => {
                    let mut info = info_arc.lock().unwrap();
                    info.is_ready = false;
                    info.error = Some(format!("Failed to spawn backend process: {}", err));
                }
            }
        });
    }

    /// Retrieve the current backend status and URL.
    pub fn get_info(&self) -> BackendInfo {
        let lock = self.info.lock().unwrap();
        lock.clone()
    }

    /// Terminate the backend child process cleanly.
    pub fn stop(&self) {
        let mut lock = self.child.lock().unwrap();
        if let Some(mut child) = lock.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sidecar_initial_state() {
        let manager = SidecarManager::new();
        let info = manager.get_info();
        assert_eq!(info.port, DEFAULT_PORT);
        assert!(!info.is_ready);
        assert_eq!(info.url, format!("http://127.0.0.1:{}", DEFAULT_PORT));
        assert!(info.error.is_none());
    }

    #[test]
    fn test_backend_info_serialization() {
        let info = BackendInfo {
            url: "http://127.0.0.1:8001".to_string(),
            port: 8001,
            is_ready: true,
            error: None,
        };
        let json = serde_json::to_string(&info).unwrap();
        assert!(json.contains("8001"));
        assert!(json.contains("\"is_ready\":true"));
    }
}

