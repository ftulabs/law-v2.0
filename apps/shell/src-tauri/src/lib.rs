//! The shell around the web UI.
//!
//! It carries no product logic on purpose. Every platform runs the same bundle
//! from `apps/web`, and the only thing that differs between them is how the UI
//! reaches the API — which is decided in `apps/web/src/platform.ts`, not here.
//!
//! On desktop the engine is meant to run as a bundled sidecar on loopback with
//! a per-launch token. That token is injected into the webview at startup
//! rather than compiled in: a secret baked into a binary is a published secret.

use tauri::Manager;

/// Where the UI should send requests, and the token that authenticates them.
///
/// Read from the environment so a developer can point the shell at a running
/// engine without rebuilding. When no sidecar is running, the default is the
/// loopback address a locally started `uvicorn` uses.
fn api_config() -> (String, String) {
    let base = std::env::var("VERITRADE_API_BASE")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let token = std::env::var("VERITRADE_TOKEN").unwrap_or_default();
    (base, token)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let (base, token) = api_config();
            let script = format!(
                "window.__VERITRADE__ = {{ baseUrl: {}, token: {} }};",
                serde_json::to_string(&base)?,
                serde_json::to_string(&token)?,
            );
            // Injected before the bundle runs, so platform.ts sees it on first read.
            if let Some(window) = app.get_webview_window("main") {
                window.eval(&script)?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the VeriTrade shell");
}
