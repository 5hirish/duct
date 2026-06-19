//! Duct desktop shell — a thin Tauri wrapper that loads the hosted Duct web app
//! and stores bring-your-own provider API keys in the OS keychain.
//!
//! The frontend (`app/src/lib/providerKeys.js`) calls these commands via the
//! global `window.__TAURI__.core.invoke(...)`. Keys live in the platform
//! keychain (macOS Keychain / Windows Credential Manager / Linux Secret
//! Service) — this shell never writes them to disk. No agent code, prompts, or
//! API keys ship in this bundle; everything proprietary stays on the backend.

use keyring::{Entry, Error as KeyringError};

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            get_provider_key,
            set_provider_key,
            delete_provider_key
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
