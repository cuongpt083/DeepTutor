pub mod sidecar;

use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, State,
};

use crate::sidecar::{BackendInfo, SidecarManager};

#[tauri::command]
fn get_backend_url(sidecar: State<'_, Arc<SidecarManager>>) -> Result<String, String> {
    let info = sidecar.get_info();
    Ok(info.url)
}

#[tauri::command]
fn get_backend_status(sidecar: State<'_, Arc<SidecarManager>>) -> Result<BackendInfo, String> {
    Ok(sidecar.get_info())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let sidecar_manager = Arc::new(SidecarManager::new());
    let sidecar_clone = Arc::clone(&sidecar_manager);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(sidecar_manager)
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_backend_status,
        ])
        .setup(move |app| {
            // Start the Python sidecar backend
            let app_handle = app.handle().clone();
            sidecar_clone.start(app_handle.clone());

            // Build Tray Menu
            let quit_i = MenuItem::with_id(app, "quit", "Quit DeepTutor", true, None::<&str>)?;
            let show_i = MenuItem::with_id(app, "show", "Open Window", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

            // Setup System Tray
            let _tray = TrayIconBuilder::new()
                .tooltip("DeepTutor")
                .menu(&menu)
                .on_menu_event(move |app_h, event| match event.id.as_ref() {
                    "quit" => {
                        app_h.exit(0);
                    }
                    "show" => {
                        if let Some(window) = app_h.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app_h = tray.app_handle();
                        if let Some(window) = app_h.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Minimize to tray on close if user wants to keep running, or handle exit
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // If closing main window, hide to tray rather than killing immediately
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DeepTutor desktop application");
}
