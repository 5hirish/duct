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

/// Keychain service for the shell's *own* secrets, kept apart from
/// `KEYCHAIN_SERVICE` so a secret can never collide with a provider named the
/// same thing.
const KEYCHAIN_SIDECAR_SERVICE: &str = "ai.getduct.desktop.sidecar";
const CREDENTIALS_KEY_ACCOUNT: &str = "credentials-encryption-key";

/// The Fernet key the sidecar encrypts stored connector credentials with,
/// minted on first run and kept in the OS keychain.
///
/// Desktop had no way to get one at all: `CREDENTIALS_ENCRYPTION_KEY` is a
/// server setting, and the frozen bundle deliberately ships no `.env`, so
/// `service/credentials.py` raised on every encrypt — connecting Google Ads
/// could complete its OAuth and then fail to persist the refresh token.
///
/// The keychain rather than a file beside the database: a key sitting next to
/// its own ciphertext stops someone reading the file and nobody holding the
/// disk, and this machine already has a credential store the provider keys use.
///
/// **Losing this key makes existing stored credentials undecryptable.** That is
/// survivable by design — `connector_access` and `service/provider_keys.py`
/// both treat a failed decrypt as "absent" and degrade to reconnecting — but it
/// does mean a user who wipes their keychain reconnects their sources.
pub(crate) fn credentials_encryption_key() -> Result<String, String> {
    let entry = Entry::new(KEYCHAIN_SIDECAR_SERVICE, CREDENTIALS_KEY_ACCOUNT)
        .map_err(describe_keyring_error)?;

    match entry.get_password() {
        Ok(existing) if !existing.trim().is_empty() => return Ok(existing),
        // An empty stored value is treated as absent and re-minted: it can only
        // come from a half-finished write, and returning it would hand the
        // sidecar a key Fernet rejects.
        Ok(_) | Err(KeyringError::NoEntry) => {}
        Err(e) => return Err(describe_keyring_error(e)),
    }

    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| format!("could not gather randomness: {e}"))?;
    // Fernet keys are url-safe base64 of exactly 32 bytes, padding included.
    let key = base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE, bytes);
    entry.set_password(&key).map_err(describe_keyring_error)?;
    Ok(key)
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
fn get_shell_info(app: AppHandle) -> serde_json::Value {
    serde_json::json!({
        "version": env!("CARGO_PKG_VERSION"),
        "capabilities": {
            "browserAuth": true,
            // The `connector` deep-link route exists, so connector OAuth can go
            // to the system browser too. Older shells lack the route entirely
            // and the web app keeps navigating them in-window.
            "browserConnectors": true,
            // Whether this build ships a local backend. True means the web app
            // should resolve its API base from `get_sidecar_info` instead of the
            // build-time NEXT_PUBLIC_API_BASE; false means keep talking to the
            // hosted API, which is also what older shells without the flag do.
            //
            // Probed rather than hardcoded, so the answer cannot disagree with
            // what `bundle.resources` actually put in the bundle. The official
            // build ships no sidecar; the self-host build adds it back.
            "localSidecar": sidecar::is_available(&app),
            // `tauri-plugin-updater` is wired and permitted in this build, so
            // the web app may check for updates and offer to install one. Kept
            // as a probe rather than a literal `true` so a build that compiles
            // the plugin out cannot advertise an update path it does not have —
            // no shipping build does that today (see the `updater` feature in
            // Cargo.toml), which is why the flag is worth a second look.
            "autoUpdate": cfg!(feature = "updater"),
            // The `notify` command exists, so the web app may hand "done" and
            // "needs you" notices to the OS instead of the webview's missing
            // Notification API. Older shells lack it and stay silent.
            "notifications": true
        }
    })
}

/// Show a system notification. The web app decides *when* (only while the
/// window is not focused — `app/src/lib/notify.js`); this only decides *how*,
/// which on a remote origin cannot be the plugin's JS bindings for the same
/// reason as the updater. Title and body are plain text from our own page.
#[tauri::command]
fn notify(app: AppHandle, title: String, body: Option<String>) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;
    let mut builder = app.notification().builder().title(title);
    if let Some(body) = body.filter(|b| !b.trim().is_empty()) {
        builder = builder.body(body);
    }
    builder.show().map_err(|e| e.to_string())
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

/// Build without the `updater` feature: the commands still exist so the
/// capability files and `build.rs` manifest stay identical across builds, but
/// they report the feature as unavailable. No shipping channel takes this path
/// since the App Store one was retired — see the `updater` feature in
/// `Cargo.toml` before assuming it is exercised.
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
/// `available` is false when no reporter was compiled in, or one was but has no
/// destination configured — the settings UI hides the toggle rather than
/// offering a switch that changes nothing.
#[tauri::command]
fn get_telemetry_settings() -> serde_json::Value {
    let enabled = telemetry::default_data_dir()
        .map(|dir| telemetry::is_enabled(&dir))
        .unwrap_or(false);
    serde_json::json!({
        "enabled": enabled,
        "available": telemetry::is_available(),
        // So the settings copy can say "on by default" or "off by default" and
        // be telling the truth about the build in front of the user.
        "default_on": telemetry::default_enabled(),
    })
}

/// Record the user's choice. Takes effect for the sidecar on next launch —
/// it reads its DSN from the environment the shell hands it at spawn, and this
/// deliberately does not restart a running backend out from under the user.
#[tauri::command]
fn set_telemetry_enabled(enabled: bool) -> Result<(), String> {
    let dir = telemetry::default_data_dir().ok_or("could not resolve the data directory")?;
    telemetry::write_prefs(
        &dir,
        telemetry::TelemetryPrefs {
            enabled: Some(enabled),
        },
    )
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
#[cfg(desktop)]
const MENU_HOME: &str = "help:home";
#[cfg(desktop)]
const MENU_CHANGELOG: &str = "help:changelog";
#[cfg(desktop)]
const MENU_REPORT_BUG: &str = "help:report-bug";
#[cfg(desktop)]
const MENU_SUGGEST: &str = "help:suggest";
#[cfg(desktop)]
const MENU_PRIVACY: &str = "help:privacy";

/// Where the Help menu points. The same two destinations the in-app account
/// drawer offers, for the same reason: an issue is a defect with a repro, a
/// discussion is an idea that has not earned a tracker row. Kept in sync with
/// `app/src/components/AppSidebar.jsx` by hand — two surfaces, one policy.
#[cfg(desktop)]
const HELP_LINKS: &[(&str, &str)] = &[
    (MENU_HOME, "https://getduct.ai"),
    (MENU_CHANGELOG, "https://getduct.ai/changelog/"),
    (
        MENU_REPORT_BUG,
        "https://github.com/5hirish/duct/issues/new?template=bug_report.yml",
    ),
    (
        MENU_SUGGEST,
        "https://github.com/5hirish/duct/discussions/new?category=ideas",
    ),
    (MENU_PRIVACY, "https://getduct.ai/privacy"),
];

/// One line saying what this app is, for the About panel.
///
/// macOS and the others read different fields — `credits` there, `comments` on
/// Windows and Linux — so it is set twice from one constant rather than
/// written twice and left to drift.
#[cfg(desktop)]
const ABOUT_BLURB: &str =
    "Duct connects your product and marketing stack and turns what it finds into briefs, \
alerts and answers you can act on.";

/// What the About panel shows, beyond the name and version Tauri fills in.
///
/// `Menu::default` builds this from `bundle.copyright` and `bundle.publisher`
/// alone, and `publisher` lands in `authors`, which macOS does not render — so
/// the panel was the app name, a version, and nothing else. Built by hand here
/// so there is a sentence in it.
#[cfg(desktop)]
fn about_metadata(app: &tauri::AppHandle) -> tauri::menu::AboutMetadata<'static> {
    let package = app.package_info();
    tauri::menu::AboutMetadata {
        name: Some(package.name.clone()),
        version: Some(package.version.to_string()),
        copyright: app.config().bundle.copyright.clone(),
        // macOS renders `credits` and ignores `comments`; Windows and Linux do
        // the opposite. Both are set, so neither platform gets a blank panel.
        credits: Some(ABOUT_BLURB.into()),
        comments: Some(ABOUT_BLURB.into()),
        website: Some("https://getduct.ai".into()),
        website_label: Some("getduct.ai".into()),
        ..Default::default()
    }
}

/// The application menu: a View menu with Reload, and a Help menu with anything
/// in it at all.
///
/// The window loads a *remote* origin, so nothing on the page can rescue a bad
/// load, and the system webview binds no reload key of its own (Tauri's default
/// menu is App/File/Edit/Window/Help — no View, no Cmd+R). Until this, the only
/// way to pick up a change, or to recover a window that came up blank because
/// the dev server wasn't listening yet, was to quit and relaunch: a poor loop
/// when developing against `localhost:3003` (`npm run dev:local`), and a dead
/// end for a shipped user whose window failed to load once.
///
/// View is inserted before Window, where macOS users expect it — located by id
/// rather than a hardcoded index, since the default menu's shape differs per
/// platform.
///
/// Help is *replaced*, not extended. `Menu::default` builds its Help submenu
/// with a single About item carrying `#[cfg(not(target_os = "macos"))]`, which
/// leaves macOS a Help menu containing nothing: it opens onto an empty box and
/// swallows the click. Apple's guidelines expect Help to work, and an empty one
/// is a documented App Store rejection (tauri-apps/tauri#9371) — which matters
/// here, because this app is headed for TestFlight.
///
/// The items are links rather than a bundled help book. A help book would be a
/// second copy of the site to keep current, and the answers people want from
/// this menu — what changed, where do I report this — live on a site that is
/// already updated when the thing itself changes.
#[cfg(desktop)]
fn install_app_menu(app: &tauri::AppHandle) -> tauri::Result<()> {
    use tauri::menu::{
        Menu, MenuItem, PredefinedMenuItem, Submenu, HELP_SUBMENU_ID, WINDOW_SUBMENU_ID,
    };

    let reload = MenuItem::with_id(app, MENU_RELOAD, "Reload", true, Some("CmdOrCtrl+R"))?;

    // Toggle Full Screen is the one item the default View carries on macOS, and
    // ours replaces that submenu rather than sitting beside it — so it has to be
    // carried over, or the menu quietly loses it.
    let mut view_items: Vec<Box<dyn tauri::menu::IsMenuItem<_>>> = Vec::new();
    #[cfg(target_os = "macos")]
    view_items.push(Box::new(PredefinedMenuItem::fullscreen(app, None)?));
    view_items.push(Box::new(reload));
    #[cfg(any(debug_assertions, feature = "devtools"))]
    view_items.push(Box::new(MenuItem::with_id(
        app,
        MENU_DEVTOOLS,
        "Toggle Developer Tools",
        true,
        Some("CmdOrCtrl+Shift+I"),
    )?));
    let view_refs: Vec<&dyn tauri::menu::IsMenuItem<_>> =
        view_items.iter().map(|item| item.as_ref()).collect();
    let view = Submenu::with_items(app, "View", true, &view_refs)?;

    // Ordered by how often a person needs them, with the two that produce work
    // for us grouped away from the two that only read.
    let home = MenuItem::with_id(app, MENU_HOME, "Duct Home Page", true, None::<&str>)?;
    let changelog = MenuItem::with_id(app, MENU_CHANGELOG, "What\u{2019}s New", true, None::<&str>)?;
    let report_bug = MenuItem::with_id(app, MENU_REPORT_BUG, "Report a Bug\u{2026}", true, None::<&str>)?;
    let suggest = MenuItem::with_id(
        app,
        MENU_SUGGEST,
        "Suggest an Improvement\u{2026}",
        true,
        None::<&str>,
    )?;
    let privacy = MenuItem::with_id(app, MENU_PRIVACY, "Privacy Policy", true, None::<&str>)?;

    let help = Submenu::with_id_and_items(
        app,
        HELP_SUBMENU_ID,
        "Help",
        true,
        &[
            &home,
            &changelog,
            &PredefinedMenuItem::separator(app)?,
            &report_bug,
            &suggest,
            &PredefinedMenuItem::separator(app)?,
            &privacy,
        ],
    )?;

    let menu = Menu::default(app)?;

    // The About item the default menu built has no description in it, and
    // AboutMetadata is only settable at construction — so the whole app submenu
    // is rebuilt rather than patched. macOS only; elsewhere About lives under
    // Help, which is built above.
    #[cfg(target_os = "macos")]
    {
        let package = app.package_info();
        let app_menu = Submenu::with_items(
            app,
            package.name.clone(),
            true,
            &[
                &PredefinedMenuItem::about(
                    app,
                    Some(&format!("About {}", package.name)),
                    Some(about_metadata(app)),
                )?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::services(app, None)?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::hide(app, None)?,
                &PredefinedMenuItem::hide_others(app, None)?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::quit(app, None)?,
            ],
        )?;
        // The app submenu is always first on macOS; replacing in place keeps it
        // there, where the OS draws it in bold next to the Apple menu.
        menu.remove_at(0)?;
        menu.insert(&app_menu, 0)?;
    }

    // Tauri's default menu grew a View submenu of its own (one item, Toggle
    // Full Screen) after this code was written, and nothing failed — the app
    // simply shipped *two* menus called View, ours second. Take the existing one
    // out before adding ours. Matched on the title because that submenu has no
    // id constant to match on; if a future Tauri renames it, the fallback is the
    // old behaviour rather than a crash.
    if let Some(existing_view) = menu
        .items()?
        .into_iter()
        .find(|item| {
            item.as_submenu()
                .and_then(|s| s.text().ok())
                .is_some_and(|title| title == "View")
        })
    {
        menu.remove(&existing_view)?;
    }

    let items = menu.items()?;
    match items
        .iter()
        .position(|item| item.id().as_ref() == WINDOW_SUBMENU_ID)
    {
        Some(index) => menu.insert(&view, index)?,
        None => menu.append(&view)?,
    }

    // Drop the default's Help before appending ours, or macOS shows two.
    if let Some(existing) = menu
        .items()?
        .into_iter()
        .find(|item| item.id().as_ref() == HELP_SUBMENU_ID)
    {
        menu.remove(&existing)?;
    }
    menu.append(&help)?;

    app.set_menu(menu)?;

    // Tells AppKit which submenu is *the* Help menu, which is what puts the
    // search field at its top. Best-effort: a missing search field is cosmetic,
    // an install that failed here would not be.
    #[cfg(target_os = "macos")]
    let _ = help.set_as_help_menu_for_nsapp();

    Ok(())
}

/// Route a menu click: Help opens a page in the system browser, View acts on
/// the window.
#[cfg(desktop)]
fn handle_menu_event(app: &tauri::AppHandle, event: tauri::menu::MenuEvent) {
    let id = event.id().as_ref();

    // Help items go to the real browser, never the app's own webview: this
    // window is the product, and navigating it to a privacy policy strands the
    // user with no back button and no tabs.
    if let Some((_, url)) = HELP_LINKS.iter().find(|(menu_id, _)| *menu_id == id) {
        let _ = app.opener().open_url(*url, None::<&str>);
        return;
    }

    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    match id {
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
        .map(|dir| telemetry::is_enabled(&dir))
        .unwrap_or(false);
    // Named, not inferred: the type is the contract — whatever the compiled-in
    // reporter needs held for the process's life. Dropping it stops the
    // transport, so binding to `_guard` (not `_`) is load-bearing.
    let _guard: telemetry::Guard = telemetry::init(telemetry_enabled);

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
        .plugin(tauri_plugin_notification::init())
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
            // quit, and an empty Help menu fails App Store review — see
            // `install_app_menu`. Not fatal if it fails: the app is still
            // usable, just with the default menu.
            if let Err(err) = install_app_menu(app.handle()) {
                eprintln!("duct: could not install the application menu: {err}");
            }

            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    handle_auth_deep_link(&handle, &url);
                    handle_connector_deep_link(&handle, &url);
                }
            });

            // Start the local backend, if this build shipped one. The official
            // build does not — it talks to the hosted API, and a missing
            // sidecar there is the design rather than a fault, so it must not
            // reach the error path below.
            if sidecar::is_available(app.handle()) {
                // A failure now is recorded in SidecarState and reported through
                // `get_sidecar_info` — the window still opens so the user sees
                // the reason rather than nothing.
                if let Err(err) = sidecar::spawn(app.handle()) {
                    eprintln!("duct: sidecar failed to start: {err}");
                    // A bundle that ships a backend and then cannot start it is
                    // broken for everyone on that platform, not just this person.
                    telemetry::capture_message(&format!("sidecar failed to start: {err}"));
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_provider_key,
            set_provider_key,
            delete_provider_key,
            get_shell_info,
            notify,
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
