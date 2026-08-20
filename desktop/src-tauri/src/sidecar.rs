//! Supervises the local Duct backend ("sidecar") that ships inside the bundle.
//!
//! The sidecar is the same FastAPI app that runs on Railway, frozen by
//! PyInstaller (`backend/duct_sidecar.spec`). It binds a loopback port the OS
//! picks, persists to SQLite in the per-user data dir, and prints exactly one
//! JSON handshake line on stdout before it starts serving:
//!
//! ```text
//! {"duct_sidecar":1,"url":"http://127.0.0.1:53124","port":53124,
//!  "api_key":"…","data_dir":"…"}
//! ```
//!
//! The web app reads that through the `get_sidecar_info` command and points its
//! API base at `url`, sending `api_key` as `X-API-Key`. Nothing here is exposed
//! off the loopback interface.
//!
//! **onedir, not `externalBin`.** Tauri's `externalBin` copies a single file,
//! but the PyInstaller build has to be onedir — a onefile binary unpacks itself
//! to a temp dir at startup, which does not survive macOS signing and
//! notarization (see the spec's header). So the whole `duct-sidecar/` directory
//! ships as a bundle *resource* and we spawn the entry binary inside it.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

/// Directory name of the PyInstaller onedir output, both in `backend/dist/`
/// and inside the bundle's resource dir.
const SIDECAR_DIR: &str = "duct-sidecar";
/// Entry binary inside that directory (`EXE(name=…)` in the spec).
const SIDECAR_BIN: &str = "duct-sidecar";
/// Escape hatch for `tauri dev` runs against a sidecar built somewhere else.
const SIDECAR_BIN_ENV: &str = "DUCT_SIDECAR_BIN";

/// Google OAuth **Desktop app** client used for sign-in.
///
/// A desktop client is required rather than a web one: `local_server.py` binds
/// a port the OS picks, so the redirect URI is
/// `http://127.0.0.1:<random>/auth/signin/google/callback` and changes every
/// launch. Google validates web clients against exactly-registered redirect
/// URIs, which such a port can never satisfy; for desktop clients the loopback
/// address is accepted on **any** port.
///
/// Embedding the id (and the secret below) is sanctioned — Google documents
/// installed-app credentials as not confidential, since anyone can extract them
/// from a shipped binary. They identify the app, they do not authorise it.
const GOOGLE_CLIENT_ID: &str =
    "726839654841-fs8i0kehickma5411jepc6v4d3r26b4g.apps.googleusercontent.com";

/// Set at build time (`DUCT_GOOGLE_CLIENT_SECRET=… cargo build`) so the value
/// stays out of git. When unset, the sidecar falls back to whatever its own
/// environment or `backend/.env*` provides, which is how a source-run dev build
/// already works.
const GOOGLE_CLIENT_SECRET: Option<&str> = option_env!("DUCT_GOOGLE_CLIENT_SECRET");

/// The handshake line, verbatim. Field names mirror `local_server.py`; the
/// shell forwards them to the webview rather than interpreting them, so a new
/// field there needs no change here beyond adding it below.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SidecarInfo {
    pub url: String,
    pub port: u16,
    pub api_key: String,
    pub data_dir: String,
}

/// Spawned child plus the handshake, once it has arrived.
///
/// `info` starts `None` and is filled by the reader thread — freezing a Python
/// app takes a few seconds to boot, and blocking `setup()` on that would leave
/// the user staring at no window at all. The webview polls `get_sidecar_info`
/// instead.
#[derive(Default)]
pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub info: Mutex<Option<SidecarInfo>>,
    /// Set when startup failed, so the UI can say why instead of polling forever.
    pub error: Mutex<Option<String>>,
}

/// Locate the sidecar entry binary.
///
/// Bundled builds find it under the resource dir. `tauri dev` has no resource
/// dir populated, so fall back to the working copy at
/// `backend/dist/duct-sidecar/` that `pyinstaller duct_sidecar.spec` produces.
fn sidecar_path(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var(SIDECAR_BIN_ENV) {
        if !explicit.is_empty() {
            return Ok(PathBuf::from(explicit));
        }
    }

    if let Ok(resources) = app.path().resource_dir() {
        let bundled = resources.join(SIDECAR_DIR).join(SIDECAR_BIN);
        if bundled.exists() {
            return Ok(bundled);
        }
    }

    // Dev fallback: <repo>/backend/dist/duct-sidecar/duct-sidecar, resolved from
    // this crate's manifest dir (…/desktop/src-tauri) at compile time.
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../backend/dist")
        .join(SIDECAR_DIR)
        .join(SIDECAR_BIN);
    if dev.exists() {
        return Ok(dev);
    }

    Err(format!(
        "sidecar binary not found. Build it with `cd backend && poetry run pyinstaller \
         duct_sidecar.spec --noconfirm`, or set {SIDECAR_BIN_ENV}."
    ))
}

/// Start the sidecar and read its handshake on a background thread.
///
/// Returns as soon as the process is spawned; `get_sidecar_info` reports `null`
/// until the handshake lands. Any failure is also recorded in `SidecarState` so
/// the webview learns about it through `get_sidecar_info` rather than hanging.
pub fn spawn(app: &AppHandle) -> Result<(), String> {
    let result = try_spawn(app);
    if let Err(ref err) = result {
        *app.state::<SidecarState>().error.lock().unwrap() = Some(err.clone());
    }
    result
}

fn try_spawn(app: &AppHandle) -> Result<(), String> {
    let bin = sidecar_path(app)?;

    let mut command = Command::new(&bin);

    // The frozen bundle deliberately ships no `.env`, so sign-in credentials
    // have to arrive through the environment. Only set what we actually have —
    // an empty value would otherwise shadow a dev's `backend/.env.local`.
    command.env("GOOGLE_OAUTH_CLIENT_ID", GOOGLE_CLIENT_ID);
    if let Some(secret) = GOOGLE_CLIENT_SECRET.filter(|s| !s.is_empty()) {
        command.env("GOOGLE_OAUTH_CLIENT_SECRET", secret);
    }

    let mut child = command
        .stdout(Stdio::piped())
        // Inherit stderr so uvicorn's log goes to the shell's own stderr, where
        // `Console.app` and `tauri dev` both pick it up.
        .stderr(Stdio::inherit())
        .stdin(Stdio::null())
        .spawn()
        .map_err(|e| format!("failed to start sidecar at {}: {e}", bin.display()))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar stdout was not captured".to_string())?;

    let state = app.state::<SidecarState>();
    *state.child.lock().unwrap() = Some(child);

    let handle = app.clone();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        let state = handle.state::<SidecarState>();

        match reader.read_line(&mut line) {
            Ok(0) => {
                *state.error.lock().unwrap() =
                    Some("sidecar exited before printing its handshake".into());
                return;
            }
            Err(e) => {
                *state.error.lock().unwrap() = Some(format!("reading sidecar handshake: {e}"));
                return;
            }
            Ok(_) => {}
        }

        match serde_json::from_str::<SidecarInfo>(&line) {
            Ok(info) => *state.info.lock().unwrap() = Some(info),
            Err(e) => {
                *state.error.lock().unwrap() =
                    Some(format!("sidecar handshake was not valid JSON ({e}): {line}"))
            }
        }

        // Keep draining stdout. The pipe has a finite buffer; if the sidecar
        // ever writes past it with nobody reading, it blocks on write and the
        // whole backend wedges.
        let mut sink = String::new();
        while let Ok(n) = reader.read_line(&mut sink) {
            if n == 0 {
                break;
            }
            sink.clear();
        }
    });

    Ok(())
}

/// Stop the sidecar. Called on app exit — the sidecar's lifetime is the app's.
pub fn shutdown(app: &AppHandle) {
    let state = app.state::<SidecarState>();
    let mut guard = state.child.lock().unwrap();
    if let Some(mut child) = guard.take() {
        // SIGKILL via std; the sidecar holds only SQLite (WAL) and a listening
        // socket, both of which recover cleanly from an abrupt exit.
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Handshake for the webview: `null` while still booting.
///
/// Errors surface as a command error so the app can show the reason rather than
/// polling forever.
#[tauri::command]
pub fn get_sidecar_info(state: State<'_, SidecarState>) -> Result<Option<SidecarInfo>, String> {
    if let Some(err) = state.error.lock().unwrap().clone() {
        return Err(err);
    }
    Ok(state.info.lock().unwrap().clone())
}
