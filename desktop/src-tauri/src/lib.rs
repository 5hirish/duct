//! Duct desktop shell — a thin Tauri wrapper that loads the hosted Duct web app
//! and stores bring-your-own provider API keys in the OS keychain.
//!
//! The frontend (`app/src/lib/providerKeys.js`) calls these commands via the
//! global `window.__TAURI__.core.invoke(...)`. Keys live in the platform
//! keychain (macOS Keychain / Windows Credential Manager / Linux Secret
//! Service) — this shell never writes them to disk. No agent code, prompts, or
//! API keys ship in this bundle; everything proprietary stays on the backend.
//!
//! Every OAuth flow runs in the system browser (Google disallows OAuth in
//! embedded webviews, and a user in one has none of their browser's sessions,
//! passwords or passkeys): the web app calls `open_external` to launch the
//! authorize URL, and the backend redirects the browser back to a
//! `ai.getduct.desktop://` deep link, which lands below and is forwarded into
//! the webview. Two routes, one shape — `auth` for signing in to Duct,
//! `connector` for connecting a data source. Neither carries the credential
//! itself, only a single-use code the webview redeems against the backend.

mod sidecar;
mod telemetry;

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
            // The `connector` deep-link route exists, so connector OAuth can go
            // to the system browser too. Older shells lack the route entirely
            // and the web app keeps navigating them in-window.
            "browserConnectors": true,
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

/// Whether crash reporting is on, and whether this build can do it at all.
///
/// `available` is false when no DSN was compiled in — the settings UI shows the
/// toggle as unavailable rather than offering a switch that does nothing.
#[tauri::command]
fn get_telemetry_settings() -> serde_json::Value {
    let enabled = telemetry::default_data_dir()
        .map(|dir| telemetry::read_prefs(&dir).enabled)
        .unwrap_or(false);
    serde_json::json!({
        "enabled": enabled,
        "available": telemetry::SENTRY_DSN.filter(|d| !d.is_empty()).is_some(),
    })
}

/// Record the user's choice. Takes effect for the sidecar on next launch —
/// it reads its DSN from the environment the shell hands it at spawn, and this
/// deliberately does not restart a running backend out from under the user.
#[tauri::command]
fn set_telemetry_enabled(enabled: bool) -> Result<(), String> {
    let dir = telemetry::default_data_dir().ok_or("could not resolve the data directory")?;
    telemetry::write_prefs(&dir, telemetry::TelemetryPrefs { enabled })
}

/// Whether a deep-link value is safe to splice into a navigation URL.
///
/// Anything on this machine can hand the shell a URL on our scheme, so every
/// value out of one is untrusted input. Exchange codes and connector ids are
/// both URL-safe tokens; drop anything else rather than reasoning about
/// escaping.
fn safe_deep_link_value(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 512
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn query_param(url: &Url, key: &str) -> Option<String> {
    url.query_pairs()
        .find(|(k, _)| k == key)
        .map(|(_, value)| value.into_owned())
}

/// Navigate the main window to `path?query` on whatever origin this shell build
/// loads (hosted app or local dev server), then bring it to the front.
fn navigate_webview(app: &AppHandle, path: &str, query: &str) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Ok(current) = window.url() else {
        return;
    };
    let Ok(mut target) = current.join(path) else {
        return;
    };
    target.set_query(Some(query));
    let _ = window.navigate(target);
    let _ = window.unminimize();
    let _ = window.set_focus();
}

/// Forward `ai.getduct.desktop://auth?auth_code=...` into the webview by
/// navigating it to `/?auth_code=...`. The login page's existing
/// `/auth/exchange` path takes it from there; the code is single-use and
/// expires in seconds, so it is safe to carry in the URL.
fn handle_auth_deep_link(app: &AppHandle, url: &Url) {
    if url.host_str() != Some("auth") {
        return;
    }
    let Some(code) = query_param(url, "auth_code") else {
        return;
    };
    if !safe_deep_link_value(&code) {
        return;
    }
    navigate_webview(app, "/", &format!("auth_code={code}"));
}

/// Forward `ai.getduct.desktop://connector?connector=...&auth_code=...` into the
/// webview by navigating it to `/connections?connector=...&auth_code=...`.
///
/// The same shape as the sign-in route, for the same reason: connecting a data
/// source is Google OAuth, which will not run in an embedded webview, so it
/// happens in the system browser and has to cross back into the app. What
/// crosses is only a single-use 60-second code — a connector refresh token is
/// long-lived and never rides in a deep link, which any app claiming the scheme
/// could read. The connections page redeems it via `/auth/connectors/exchange`.
fn handle_connector_deep_link(app: &AppHandle, url: &Url) {
    if url.host_str() != Some("connector") {
        return;
    }
    let (Some(connector), Some(code)) =
        (query_param(url, "connector"), query_param(url, "auth_code"))
    else {
        return;
    };
    if !safe_deep_link_value(&connector) || !safe_deep_link_value(&code) {
        return;
    }
    navigate_webview(
        app,
        "/connections",
        &format!("connector={connector}&auth_code={code}"),
    );
}

/// Menu ids. Namespaced so a future menu can't collide with these.
#[cfg(desktop)]
const MENU_RELOAD: &str = "view:reload";
#[cfg(all(desktop, any(debug_assertions, feature = "devtools")))]
const MENU_DEVTOOLS: &str = "view:devtools";

/// A View menu with Reload — the shell has never had one.
///
/// The window loads a *remote* origin, so nothing on the page can rescue a bad
/// load, and the system webview binds no reload key of its own (Tauri's default
/// menu is App/File/Edit/Window/Help — no View, no Cmd+R). Until this, the only
/// way to pick up a change, or to recover a window that came up blank because
/// the dev server wasn't listening yet, was to quit and relaunch: a poor loop
/// when developing against `localhost:3003` (`npm run dev:local`), and a dead
/// end for a shipped user whose window failed to load once.
///
/// Inserted before Window, where macOS users expect View — located by id rather
/// than a hardcoded index, since the default menu's shape differs per platform.
#[cfg(desktop)]
fn install_view_menu(app: &tauri::AppHandle) -> tauri::Result<()> {
    use tauri::menu::{Menu, MenuItem, Submenu, WINDOW_SUBMENU_ID};

    let reload = MenuItem::with_id(app, MENU_RELOAD, "Reload", true, Some("CmdOrCtrl+R"))?;

    #[cfg(any(debug_assertions, feature = "devtools"))]
    let view = {
        let devtools = MenuItem::with_id(
            app,
            MENU_DEVTOOLS,
            "Toggle Developer Tools",
            true,
            Some("CmdOrCtrl+Shift+I"),
        )?;
        Submenu::with_items(app, "View", true, &[&reload, &devtools])?
    };
    #[cfg(not(any(debug_assertions, feature = "devtools")))]
    let view = Submenu::with_items(app, "View", true, &[&reload])?;

    let menu = Menu::default(app)?;
    let before_window = menu
        .items()?
        .iter()
        .position(|item| item.id().as_ref() == WINDOW_SUBMENU_ID);
    match before_window {
        Some(index) => menu.insert(&view, index)?,
        None => menu.append(&view)?,
    }
    app.set_menu(menu)?;
    Ok(())
}

/// Route a View-menu click to the main window.
#[cfg(desktop)]
fn handle_menu_event(app: &tauri::AppHandle, event: tauri::menu::MenuEvent) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    match event.id().as_ref() {
        MENU_RELOAD => {
            let _ = window.reload();
        }
        #[cfg(any(debug_assertions, feature = "devtools"))]
        MENU_DEVTOOLS => {
            if window.is_devtools_open() {
                window.close_devtools();
            } else {
                window.open_devtools();
            }
        }
        _ => {}
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Before the builder: a panic during setup is exactly the kind of failure
    // worth reporting, and the guard has to outlive the whole app — dropping it
    // stops the transport, so binding it to `_guard` (not `_`) matters.
    let telemetry_enabled = telemetry::default_data_dir()
        .map(|dir| telemetry::read_prefs(&dir).enabled)
        .unwrap_or(false);
    let _guard = telemetry::init(telemetry_enabled);

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
        .on_menu_event(handle_menu_event)
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

            // A window that cannot be reloaded is a window that can only be
            // quit — see `install_view_menu`. Not fatal if it fails: the app
            // is still usable, just without the menu.
            if let Err(err) = install_view_menu(app.handle()) {
                eprintln!("duct: could not install the View menu: {err}");
            }

            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    handle_auth_deep_link(&handle, &url);
                    handle_connector_deep_link(&handle, &url);
                }
            });

            // Start the local backend. A failure here is recorded in
            // SidecarState and reported through `get_sidecar_info` — the window
            // still opens so the user sees the reason rather than nothing.
            if let Err(err) = sidecar::spawn(app.handle()) {
                eprintln!("duct: sidecar failed to start: {err}");
                // The webview shows this to the user via `get_sidecar_info`,
                // but a bundle that cannot start its own backend is broken for
                // everyone on that platform, not just this person.
                telemetry::capture_message(&format!("sidecar failed to start: {err}"));
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
            install_update,
            get_telemetry_settings,
            set_telemetry_enabled
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
