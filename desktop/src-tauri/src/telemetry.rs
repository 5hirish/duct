//! Crash reporting for the shell, and the user's switch for the sidecar's.
//!
//! Two separate things that share one consent decision:
//!
//! * **The shell.** A Rust panic, or a sidecar that will not start, currently
//!   leaves no trace anywhere — the webview's Sentry only sees JavaScript. This
//!   initialises `sentry` in-process so those reach the same project.
//! * **The sidecar.** `local_server.py` deliberately blanks `SENTRY_DSN`
//!   ("a user's laptop is not a deployment — never phone home by default"), so
//!   the bundled backend reports nothing. That default stays. What changes is
//!   that a user can now turn it on, and the shell passes the DSN through only
//!   when they have.
//!
//! Consent lives in a plain JSON file in the per-user data dir rather than the
//! keychain — it is a preference, not a secret, and the sidecar's data dir is
//! already owner-only (0700).
//!
//! The DSN is compiled in (`SENTRY_DSN=… npm run build`) so it stays out of git.
//! Deliberately the same name the backend reads at runtime and the same one
//! `backend/.env.local` already defines — a shell set up for the backend builds
//! a reporting shell with no extra step, and there is one spelling to remember.
//! With no DSN the whole thing is inert: nothing initialises, and the toggle
//! still records a preference that simply has no effect.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Filename inside the per-user data dir. Sits beside `duct.db`.
const PREFS_FILE: &str = "telemetry.json";

/// Set at build time so the value is not in the repository. Read by `option_env!`
/// while rustc compiles, NOT at runtime — see the note in `build.rs`.
pub const SENTRY_DSN: Option<&str> = option_env!("SENTRY_DSN");

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct TelemetryPrefs {
    /// Opt-IN. Absent file, unreadable file, or malformed JSON all mean `false`
    /// — consent is never inferred from a failure to read it.
    #[serde(default)]
    pub enabled: bool,
}

fn prefs_path(data_dir: &Path) -> PathBuf {
    data_dir.join(PREFS_FILE)
}

pub fn read_prefs(data_dir: &Path) -> TelemetryPrefs {
    std::fs::read_to_string(prefs_path(data_dir))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

pub fn write_prefs(data_dir: &Path, prefs: TelemetryPrefs) -> Result<(), String> {
    std::fs::create_dir_all(data_dir).map_err(|e| e.to_string())?;
    let body = serde_json::to_string_pretty(&prefs).map_err(|e| e.to_string())?;
    std::fs::write(prefs_path(data_dir), body).map_err(|e| e.to_string())
}

/// The data dir the sidecar will use, resolved the same way `utils/appdirs.py`
/// does so both halves agree on one folder before the sidecar has started.
///
/// Kept in sync by hand with that module; there is no shared source, because
/// the shell has to know the path *before* it can ask the sidecar anything.
pub fn default_data_dir() -> Option<PathBuf> {
    if let Ok(explicit) = std::env::var("DUCT_DATA_DIR") {
        if !explicit.is_empty() {
            return Some(PathBuf::from(explicit));
        }
    }
    let home = dirs_home()?;
    #[cfg(target_os = "macos")]
    return Some(home.join("Library/Application Support/ai.getduct.desktop"));
    #[cfg(windows)]
    return Some(
        std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| home.join("AppData/Roaming"))
            .join("Duct"),
    );
    #[cfg(all(not(target_os = "macos"), not(windows)))]
    return Some(
        std::env::var("XDG_DATA_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| home.join(".local/share"))
            .join("duct"),
    );
}

fn dirs_home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

/// Start crash reporting for the shell process.
///
/// The returned guard must be held for the life of the app — dropping it stops
/// the background transport, so an unheld guard silently reports nothing.
/// Returns `None` when there is no DSN or the user has not opted in.
#[cfg(feature = "crash-reporting")]
pub fn init(enabled: bool) -> Option<sentry::ClientInitGuard> {
    let dsn = SENTRY_DSN.filter(|d| !d.is_empty())?;
    if !enabled {
        return None;
    }
    // Built by mutation, not a struct literal: `ClientOptions` is
    // `#[non_exhaustive]` as of sentry 0.49, so `..Default::default()` does not
    // compile from outside the crate.
    let mut options = sentry::ClientOptions::default();
    options.release = sentry::release_name!();
    // The shell handles the user's provider API keys and OAuth codes. Nothing
    // here should ever carry them, but the default is off regardless — this is
    // a crash reporter, not an analytics pipe.
    options.send_default_pii = false;
    Some(sentry::init((dsn, options)))
}

#[cfg(not(feature = "crash-reporting"))]
pub fn init(_enabled: bool) -> Option<()> {
    None
}

/// Report a non-panic failure worth knowing about (e.g. the sidecar refusing to
/// start). A no-op when reporting is off, so call sites need no `cfg`.
#[cfg(feature = "crash-reporting")]
pub fn capture_message(message: &str) {
    sentry::capture_message(message, sentry::Level::Error);
}

#[cfg(not(feature = "crash-reporting"))]
pub fn capture_message(_message: &str) {}
