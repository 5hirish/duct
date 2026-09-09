//! Whether to report, and what the user chose. Never how, and never to whom.
//!
//! Three processes share one decision:
//!
//! * **The shell.** A Rust panic, or a sidecar that will not start, leaves no
//!   trace anywhere otherwise — the webview's reporter only sees JavaScript.
//! * **The sidecar.** `local_server.py` deliberately blanks its own reporting
//!   destination ("a user's laptop is not a deployment — never phone home by
//!   default"), so
//!   the bundled backend reports nothing unless this module hands it the
//!   environment to do so.
//! * **The webview.** Reports on its own, tagged with the shell version.
//!
//! The preference lives in a plain JSON file in the per-user data dir rather
//! than the keychain — it is a preference, not a secret, and the sidecar's data
//! dir is already owner-only (0700).
//!
//! The builds we distribute report by default (`DUCT_TELEMETRY_DEFAULT_ON=1` at
//! build time); a self-host build does not, because we are not the ones running
//! it. Either way the switch in Preferences is the user's, and once they touch
//! it their answer is recorded and no default applies again.
//!
//! **Which reporter, and whether one exists at all, is `reporter.rs`.** This
//! file names no vendor on purpose: a fork that swaps the backend should not
//! have to touch consent, defaults, or the preference file.

mod reporter;

pub use reporter::{capture_message, init, is_available, sidecar_env, Guard};

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Filename inside the per-user data dir. Sits beside `duct.db`.
const PREFS_FILE: &str = "telemetry.json";

/// Whether a build reports when the user has expressed no preference.
///
/// Compiled in the same way the reporter's own configuration is, and set
/// only on the builds we distribute
/// ourselves. A self-host build never sets it, so it stays opt-in there: the
/// sidecar is running on somebody's own machine, and "a user's laptop is not a
/// deployment" still holds for every build we do not ship.
pub fn default_enabled() -> bool {
    matches!(
        option_env!("DUCT_TELEMETRY_DEFAULT_ON"),
        Some("1") | Some("true")
    )
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct TelemetryPrefs {
    /// `None` is "never chose", and the build default decides. An explicit
    /// `Some(false)` is a decision, and outranks any default forever.
    #[serde(default)]
    pub enabled: Option<bool>,
}

fn prefs_path(data_dir: &Path) -> PathBuf {
    data_dir.join(PREFS_FILE)
}

pub fn read_prefs(data_dir: &Path) -> TelemetryPrefs {
    // "No file" and "a file we could not read" are different answers now that a
    // default can be on. Nobody has chosen in the first case. In the second we
    // may be looking at an "off" we are one step away from overriding, so the
    // only safe way to be wrong is to stay quiet.
    let raw = match std::fs::read_to_string(prefs_path(data_dir)) {
        Ok(raw) => raw,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            return TelemetryPrefs::default()
        }
        Err(_) => return TelemetryPrefs { enabled: Some(false) },
    };
    serde_json::from_str(&raw).unwrap_or(TelemetryPrefs {
        enabled: Some(false),
    })
}

/// The effective answer: what the user chose, or the build default if they
/// never did. Every call site wants this rather than the raw preference.
pub fn is_enabled(data_dir: &Path) -> bool {
    read_prefs(data_dir).enabled.unwrap_or_else(default_enabled)
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
