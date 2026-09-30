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
    build_flag_is_on(option_env!("DUCT_TELEMETRY_DEFAULT_ON"))
}

/// Separate from `default_enabled` only so the accepted spellings can be
/// tested: `option_env!` is fixed when the crate compiles, and no test can vary it.
fn build_flag_is_on(flag: Option<&str>) -> bool {
    matches!(flag, Some("1") | Some("true"))
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

#[cfg(test)]
mod tests {
    //! The consent rule, pinned. Every assertion about the effective answer is
    //! written against `default_enabled()` rather than a literal, so the suite
    //! holds whether or not the build that runs it sets the default flag.

    use super::*;
    use crate::test_support::scratch_dir;

    /// A data dir holding `contents` as the preference file, as an earlier
    /// launch, a hand edit or a crash mid-write might have left it.
    fn data_dir_with(name: &str, contents: &[u8]) -> PathBuf {
        let dir = scratch_dir(name);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(prefs_path(&dir), contents).unwrap();
        dir
    }

    fn record(dir: &Path, enabled: Option<bool>) -> Result<(), String> {
        write_prefs(dir, TelemetryPrefs { enabled })
    }

    fn assert_reads_as_off(dir: &Path, case: &str) {
        assert_eq!(read_prefs(dir).enabled, Some(false), "{case}");
        assert!(!is_enabled(dir), "{case}");
    }

    #[test]
    fn no_file_means_nobody_has_chosen_and_the_build_default_applies() {
        // A first launch: the sidecar has not created the data dir yet.
        let dir = scratch_dir("telemetry-absent");
        assert_eq!(read_prefs(&dir).enabled, None);
        assert_eq!(is_enabled(&dir), default_enabled());

        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(read_prefs(&dir).enabled, None, "empty data dir");
        assert_eq!(is_enabled(&dir), default_enabled());

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_recorded_yes_is_on_whatever_the_build_default() {
        let dir = data_dir_with("telemetry-yes", br#"{"enabled": true}"#);
        assert_eq!(read_prefs(&dir).enabled, Some(true));
        assert!(is_enabled(&dir));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_recorded_no_is_off_whatever_the_build_default() {
        let dir = data_dir_with("telemetry-no", br#"{"enabled": false}"#);
        assert_eq!(read_prefs(&dir).enabled, Some(false));
        assert!(!is_enabled(&dir));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_malformed_file_reads_as_off_even_when_it_seems_to_say_yes() {
        // It may be a refusal we can no longer parse; guessing "yes" from the
        // wreckage would report for someone who said no.
        let dir = scratch_dir("telemetry-malformed");
        std::fs::create_dir_all(&dir).unwrap();
        for (case, body) in [
            ("truncated", r#"{"enabled": tr"#),
            ("not json", "enabled=true"),
            ("trailing garbage", r#"{"enabled": true} x"#),
            ("string, not bool", r#"{"enabled": "yes"}"#),
            ("number, not bool", r#"{"enabled": 1}"#),
            ("top-level null", "null"),
        ] {
            std::fs::write(prefs_path(&dir), body).unwrap();
            assert_reads_as_off(&dir, case);
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn an_empty_file_reads_as_off() {
        // `write_prefs` truncates before it writes, so a crash between the two
        // leaves exactly this behind.
        let dir = scratch_dir("telemetry-empty");
        std::fs::create_dir_all(&dir).unwrap();
        for (case, body) in [("zero bytes", ""), ("whitespace only", "  \n")] {
            std::fs::write(prefs_path(&dir), body).unwrap();
            assert_reads_as_off(&dir, case);
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_file_that_exists_but_cannot_be_read_reads_as_off() {
        // Every read error except "not found" is this arm. Permission bits are
        // not used to provoke one: a test run as root reads a 0o000 file anyway.
        let garbled = data_dir_with("telemetry-not-utf8", &[0xff, 0xfe, 0x00, 0x80]);
        assert_reads_as_off(&garbled, "not UTF-8");
        let _ = std::fs::remove_dir_all(&garbled);

        let dir = scratch_dir("telemetry-is-a-dir");
        std::fs::create_dir_all(prefs_path(&dir)).unwrap();
        assert_reads_as_off(&dir, "a directory where the file should be");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_file_with_no_answer_in_it_means_nobody_has_chosen() {
        // Unlike a malformed file, these parse: `#[serde(default)]` makes a
        // missing key "never chose", and `null` is what `write_prefs` records
        // for `None`. So the build default applies, not "off".
        let dir = scratch_dir("telemetry-no-answer");
        std::fs::create_dir_all(&dir).unwrap();
        for (case, body) in [
            ("empty object", "{}"),
            ("explicit null", r#"{"enabled": null}"#),
        ] {
            std::fs::write(prefs_path(&dir), body).unwrap();
            assert_eq!(read_prefs(&dir).enabled, None, "{case}");
            assert_eq!(is_enabled(&dir), default_enabled(), "{case}");
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn fields_this_build_does_not_know_leave_the_answer_intact() {
        // A newer shell may add a field; after a downgrade, the older one must
        // still read the user's answer rather than treat the file as corrupt.
        let dir = scratch_dir("telemetry-unknown-fields");
        std::fs::create_dir_all(&dir).unwrap();
        for (body, expected) in [
            (r#"{"version": 2, "enabled": false}"#, Some(false)),
            (r#"{"enabled": true, "version": 2}"#, Some(true)),
            (r#"{"version": 2}"#, None),
        ] {
            std::fs::write(prefs_path(&dir), body).unwrap();
            assert_eq!(read_prefs(&dir).enabled, expected, "{body}");
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn every_choice_round_trips_through_a_data_dir_that_did_not_exist() {
        let root = scratch_dir("telemetry-round-trip");
        // Nested and absent: the switch can be used before the sidecar has
        // ever created its data dir, and the write must create it.
        let dir = root.join("not").join("yet");
        for enabled in [Some(true), Some(false), None] {
            record(&dir, enabled).expect("a writable data dir");
            assert_eq!(read_prefs(&dir).enabled, enabled);
            assert_eq!(is_enabled(&dir), enabled.unwrap_or_else(default_enabled));
        }
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn the_file_on_disk_keeps_the_shape_existing_installs_already_have() {
        // Every install that has touched the switch holds this file. Renaming
        // it, or the key, makes a recorded "off" read as "never chose" — which
        // on the builds we distribute is "on".
        let dir = scratch_dir("telemetry-shape");
        record(&dir, Some(false)).unwrap();
        let raw = std::fs::read_to_string(dir.join("telemetry.json")).unwrap();
        let value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(value, serde_json::json!({ "enabled": false }));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_later_choice_replaces_an_earlier_one() {
        // Yes, then no, then yes: the last write is shorter than the one before
        // it, so a write that did not truncate would leave a trailing `}` and
        // the file would read as corrupt, i.e. off.
        let dir = scratch_dir("telemetry-overwrite");
        for enabled in [Some(true), Some(false), Some(true)] {
            record(&dir, enabled).unwrap();
            assert_eq!(read_prefs(&dir).enabled, enabled);
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn touching_the_switch_repairs_a_corrupt_file() {
        // Corrupt reads as off; the switch is the user's only way back to on,
        // so a write has to replace the wreck rather than refuse it.
        let dir = data_dir_with("telemetry-repair", b"{\"enabled\": tr");
        assert_reads_as_off(&dir, "before the repair");
        record(&dir, Some(true)).unwrap();
        assert_eq!(read_prefs(&dir).enabled, Some(true));
        assert!(is_enabled(&dir));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_write_that_cannot_land_is_an_error_not_a_panic() {
        // `set_telemetry_enabled` hands this string to the settings UI.
        let blocker = scratch_dir("telemetry-blocked");
        std::fs::create_dir_all(blocker.parent().unwrap()).unwrap();
        std::fs::write(&blocker, b"not a directory").unwrap();
        let err = record(&blocker.join("data"), Some(true))
            .expect_err("a data dir under a regular file cannot be created");
        assert!(!err.is_empty());
        let _ = std::fs::remove_file(&blocker);

        let dir = scratch_dir("telemetry-write-onto-dir");
        std::fs::create_dir_all(prefs_path(&dir)).unwrap();
        let err = record(&dir, Some(true))
            .expect_err("a directory where the file should be cannot be overwritten");
        assert!(!err.is_empty());
        assert_reads_as_off(&dir, "the failed write left the answer at off");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_build_default_is_on_only_for_1_or_true() {
        // `desktop-release.yml` sets "1". Anything else stays opt-in, "0"
        // above all: a flag read as "set at all" would make `=0` report.
        assert!(build_flag_is_on(Some("1")));
        assert!(build_flag_is_on(Some("true")));
        assert!(!build_flag_is_on(None));
        for off in ["", "0", "false", "TRUE", "yes"] {
            assert!(!build_flag_is_on(Some(off)), "{off:?}");
        }
    }
}
