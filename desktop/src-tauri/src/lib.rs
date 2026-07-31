//! Duct desktop shell — a thin Tauri wrapper that loads the hosted Duct web app
//! and stores bring-your-own provider API keys in the OS keychain.
//!
//! The frontend (`app/src/lib/providerKeys.js`) calls these commands via the
//! global `window.__TAURI__.core.invoke(...)`. Keys live in the platform
//! keychain (macOS Keychain / Windows Credential Manager / Linux Secret
//! Service) — this shell never writes them to disk. No agent code, prompts, or
//! API keys ship in this bundle; everything proprietary stays on the backend.
//!
//! Google sign-in runs in the system browser (Google disallows OAuth in
//! embedded webviews): the web app calls `open_external` to launch the
//! authorize URL, and the backend redirects the browser to
//! `ai.getduct.desktop://auth?auth_code=...`, which lands in
//! `handle_auth_deep_link` below and is forwarded to the webview's existing
//! `/?auth_code=` exchange path.

use keyring::{Entry, Error as KeyringError};
use tauri::{AppHandle, Manager, Url};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_opener::OpenerExt;

/// Keychain service namespace. The `provider` id (e.g. "anthropic") is the account.
const KEYCHAIN_SERVICE: &str = "ai.getduct.desktop.provider-keys";

fn entry(provider: &str) -> Result<Entry, String> {
    Entry::new(KEYCHAIN_SERVICE, provider).map_err(|e| e.to_string())
}

/// Read a stored provider key. Returns "" when none is set.
#[tauri::command]
fn get_provider_key(provider: String) -> Result<String, String> {
    match entry(&provider)?.get_password() {
        Ok(secret) => Ok(secret),
        Err(KeyringError::NoEntry) => Ok(String::new()),
        Err(e) => Err(e.to_string()),
    }
}

/// Store a provider key in the OS keychain.
#[tauri::command]
fn set_provider_key(provider: String, key: String) -> Result<(), String> {
    entry(&provider)?.set_password(&key).map_err(|e| e.to_string())
}

/// Remove a stored provider key (no-op if absent).
#[tauri::command]
fn delete_provider_key(provider: String) -> Result<(), String> {
    match entry(&provider)?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// Shell version and feature flags. The hosted web app probes this so it can
/// gate shell-dependent flows on capability, not on shell version — older
/// shells where this command doesn't exist simply keep the legacy behaviour.
#[tauri::command]
fn get_shell_info() -> serde_json::Value {
    serde_json::json!({
        "version": env!("CARGO_PKG_VERSION"),
        "capabilities": { "browserAuth": true }
    })
}

/// Open a URL in the system's default browser. Restricted to http(s) so the
/// remote page can never use the shell to launch other URL-scheme handlers.
#[tauri::command]
fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    let allowed = url.starts_with("https://")
        || url.starts_with("http://localhost")
        || url.starts_with("http://127.0.0.1");
    if !allowed {
        return Err("only http(s) URLs may be opened externally".into());
    }
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| e.to_string())
}

/// Forward `ai.getduct.desktop://auth?auth_code=...` into the webview by
/// navigating it to `/?auth_code=...` on whatever origin this shell build
/// loads (hosted app or local dev server). The login page's existing
/// `/auth/exchange` path takes it from there; the code is single-use and
/// expires in seconds, so it is safe to carry in the URL.
fn handle_auth_deep_link(app: &AppHandle, url: &Url) {
    if url.host_str() != Some("auth") {
        return;
    }
    let Some(code) = url
        .query_pairs()
        .find(|(key, _)| key == "auth_code")
        .map(|(_, value)| value.into_owned())
    else {
        return;
    };
    // Exchange codes are URL-safe tokens; drop anything else rather than
    // splicing arbitrary deep-link input into a navigation URL.
    if code.is_empty()
        || !code
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return;
    }
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Ok(current) = window.url() else {
        return;
    };
    let Ok(mut target) = current.join("/") else {
        return;
    };
    target.set_query(Some(&format!("auth_code={code}")));
    let _ = window.navigate(target);
    let _ = window.unminimize();
    let _ = window.set_focus();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    handle_auth_deep_link(&handle, &url);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_provider_key,
            set_provider_key,
            delete_provider_key,
            get_shell_info,
            open_external
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
