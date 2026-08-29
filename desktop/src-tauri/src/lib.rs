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

mod sidecar;

use keyring::{Entry, Error as KeyringError};
use tauri::{AppHandle, Manager, Url};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_opener::OpenerExt;

use sidecar::{get_sidecar_info, SidecarState};

/// Keychain service namespace. The `provider` id (e.g. "anthropic") is the account.
const KEYCHAIN_SERVICE: &str = "ai.getduct.desktop.provider-keys";

fn entry(provider: &str) -> Result<Entry, String> {
    Entry::new(KEYCHAIN_SERVICE, provider).map_err(describe_keyring_error)
}

/// Turn a keyring failure into something a user can act on.
///
/// macOS and Windows always have a credential store. Linux does not: the
/// `secret-service` backend talks to a D-Bus daemon (gnome-keyring, KWallet,
/// KeePassXC) that a minimal, headless, or tiling-WM install may simply not run.
/// The raw error for that is a D-Bus transport message with no hint about the
/// cause, and the web app used to swallow it entirely — a saved key just
/// silently didn't persist. Name the actual problem instead.
fn describe_keyring_error(err: KeyringError) -> String {
    let generic = err.to_string();
    if !cfg!(target_os = "linux") {
        return generic;
    }
    match err {
        KeyringError::NoStorageAccess(_) | KeyringError::PlatformFailure(_) => format!(
            "no OS keyring available ({generic}). Duct stores provider keys in the \
             freedesktop Secret Service; install and start a keyring daemon such as \
             gnome-keyring or KeePassXC, then try again."
        ),
        other => other.to_string(),
    }
}

/// Read a stored provider key. Returns "" when none is set.
#[tauri::command]
fn get_provider_key(provider: String) -> Result<String, String> {
    match entry(&provider)?.get_password() {
        Ok(secret) => Ok(secret),
        Err(KeyringError::NoEntry) => Ok(String::new()),
        Err(e) => Err(describe_keyring_error(e)),
    }
}

/// Store a provider key in the OS keychain.
#[tauri::command]
fn set_provider_key(provider: String, key: String) -> Result<(), String> {
    entry(&provider)?
        .set_password(&key)
        .map_err(describe_keyring_error)
}

/// Remove a stored provider key (no-op if absent).
#[tauri::command]
fn delete_provider_key(provider: String) -> Result<(), String> {
    match entry(&provider)?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(e) => Err(describe_keyring_error(e)),
    }
}

/// Shell version and feature flags. The hosted web app probes this so it can
/// gate shell-dependent flows on capability, not on shell version — older
/// shells where this command doesn't exist simply keep the legacy behaviour.
#[tauri::command]
fn get_shell_info() -> serde_json::Value {
    serde_json::json!({
        "version": env!("CARGO_PKG_VERSION"),
        "capabilities": {
            "browserAuth": true,
            // This shell ships and supervises a local backend; the web app should
            // resolve its API base from `get_sidecar_info` instead of the
            // build-time NEXT_PUBLIC_API_BASE. Older shells lack the flag and
            // keep talking to the hosted API.
            "localSidecar": true,
            // `tauri-plugin-updater` is wired and permitted in this build, so
            // the web app may check for updates and offer to install one. The
            // App Store variant must never report this true — self-update is
            // grounds for rejection there.
            "autoUpdate": cfg!(feature = "updater")
        }
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

/// Whether a newer release is available, and what it is.
///
/// Returns `null` when the app is current. Exposed as a command rather than
/// letting the page use `@tauri-apps/plugin-updater` directly: the window loads
/// a *remote* origin, which cannot import the plugin's JS guest bindings the way
/// a bundled frontend would. Same reason `providerKeys.js` goes through invoke.
#[cfg(feature = "updater")]
#[tauri::command]
async fn check_for_update(app: AppHandle) -> Result<Option<serde_json::Value>, String> {
    use tauri_plugin_updater::UpdaterExt;

    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater.check().await.map_err(|e| e.to_string())?;
    Ok(update.map(|u| {
        serde_json::json!({
            "version": u.version,
            "currentVersion": u.current_version,
            "notes": u.body,
            "date": u.date.map(|d| d.to_string()),
        })
    }))
}

/// Download and install the pending update, then relaunch into it.
///
/// Re-checks rather than caching the `Update` from `check_for_update`: holding
/// it across two commands would mean parking a non-`Send` handle in app state
/// for the sake of one request to a static JSON manifest.
#[cfg(feature = "updater")]
#[tauri::command]
async fn install_update(app: AppHandle) -> Result<(), String> {
    use tauri_plugin_updater::UpdaterExt;

    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater
        .check()
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "no update available".to_string())?;

    update
        .download_and_install(|_downloaded, _total| {}, || {})
        .await
        .map_err(|e| e.to_string())?;

    // Replaces the running process. The sidecar is killed by the Exit handler
    // in `run()` first, so the new instance gets a free port and an unlocked DB.
    app.restart();
}

/// Build without the `updater` feature (the App Store variant): the commands
/// still exist so the capability files and `build.rs` manifest stay identical
/// across builds, but they report the feature as unavailable.
#[cfg(not(feature = "updater"))]
#[tauri::command]
async fn check_for_update(_app: AppHandle) -> Result<Option<serde_json::Value>, String> {
    Ok(None)
}

#[cfg(not(feature = "updater"))]
#[tauri::command]
async fn install_update(_app: AppHandle) -> Result<(), String> {
    Err("this build does not support self-update".into())
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
    let builder = tauri::Builder::default();

    // MUST be the first plugin registered (Tauri's own requirement). It only
    // matters off macOS: there, the OS hands a deep link to the running app,
    // whereas Windows and Linux start a new process with the URL in argv. The
    // `deep-link` feature makes this plugin forward that argv to the running
    // instance's deep-link handler, so `handle_auth_deep_link` below sees the
    // auth code no matter which platform delivered it. Without this, a Windows
    // or Linux sign-in would open a second window with a second sidecar and
    // leave the original one still logged out.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
        // The deep link itself is forwarded for us; all that is left is to put
        // the existing window in front of the user.
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
    }));

    #[cfg(feature = "updater")]
    let builder = builder.plugin(tauri_plugin_updater::Builder::new().build());

    builder
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_deep_link::init())
        .manage(SidecarState::default())
        .setup(|app| {
            // macOS registers the scheme from the bundle's Info.plist. Linux and
            // Windows register it from the *installer*, so a build that was run
            // rather than installed — `tauri dev`, a CI smoke test, an
            // extracted AppImage — never receives one. Registering at runtime
            // covers that; it is a no-op where the installer already did it,
            // and unsupported on macOS, so the error is deliberately ignored.
            #[cfg(any(target_os = "linux", windows))]
            {
                use tauri_plugin_deep_link::DeepLinkExt as _;
                if let Err(err) = app.deep_link().register_all() {
                    eprintln!("duct: could not register deep link scheme: {err}");
                }
            }

            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    handle_auth_deep_link(&handle, &url);
                }
            });

            // Start the local backend. A failure here is recorded in
            // SidecarState and reported through `get_sidecar_info` — the window
            // still opens so the user sees the reason rather than nothing.
            if let Err(err) = sidecar::spawn(app.handle()) {
                eprintln!("duct: sidecar failed to start: {err}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_provider_key,
            set_provider_key,
            delete_provider_key,
            get_shell_info,
            get_sidecar_info,
            open_external,
            check_for_update,
            install_update
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // The sidecar's lifetime is the app window's: no orphaned Python
            // process holding a loopback port after the user quits.
            if matches!(event, tauri::RunEvent::Exit) {
                sidecar::shutdown(app);
            }
        });
}
