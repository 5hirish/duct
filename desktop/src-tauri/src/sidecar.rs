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
use tauri::{AppHandle, Manager, State, WebviewUrl};

/// Directory name of the PyInstaller onedir output, both in `backend/dist/`
/// and inside the bundle's resource dir.
const SIDECAR_DIR: &str = "duct-sidecar";
/// Entry binary inside that directory (`EXE(name=…)` in the spec).
/// PyInstaller appends `.exe` on Windows.
#[cfg(windows)]
const SIDECAR_BIN: &str = "duct-sidecar.exe";
#[cfg(not(windows))]
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
///
/// Duct's own client is the default; a build that sets
/// `GOOGLE_DESKTOP_OAUTH_CLIENT_ID` replaces it. A fork needs that, because the
/// consent screen names whoever owns the client — sign-in on someone else's
/// build should not say "Duct". The id and the secret below are halves of one
/// credential and must be overridden together: an id from one Google project
/// with a secret from another fails at the token exchange, several screens
/// after the user last had a chance to notice.
const GOOGLE_DESKTOP_CLIENT_ID: &str = match option_env!("GOOGLE_DESKTOP_OAUTH_CLIENT_ID") {
    Some(id) => id,
    None => "726839654841-fs8i0kehickma5411jepc6v4d3r26b4g.apps.googleusercontent.com",
};

/// Baked in at build time so the value stays out of git:
/// `GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET=… npm run build`.
///
/// Deliberately the same name the sidecar reads at runtime and the same one
/// `backend/.env.local` uses, so a shell set up for the backend can build a
/// working shell with no extra step. When unset, the sidecar falls back to
/// whatever its own environment provides, which is how a source-run dev build
/// already works — but a bundle launched from Finder inherits nothing, which is
/// why the release build has to compile it in.
const GOOGLE_DESKTOP_CLIENT_SECRET: Option<&str> =
    option_env!("GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET");

/// Which env file the bundled sidecar should embody, baked in at build time:
/// `DUCT_SIDECAR_ENV_FILE=/abs/path/backend/.env.local npm run build:dev`.
///
/// The sidecar reads `DUCT_ENV_FILE` at runtime and will happily run against a
/// deployment's Postgres — `db/migrate.rs`'s counterpart `_owns_database`
/// declines to migrate anything it did not create, so pointing it at staging
/// borrows the schema rather than reshaping it. What was missing was any way to
/// *say so* for an installed bundle: an app launched from Spotlight or the
/// Finder inherits no shell environment, so the only route in is at compile
/// time, exactly as for the OAuth secret above.
///
/// This is what makes "run the desktop app against staging" possible at all.
/// Without it the shell always forced its own SQLite, so the desktop build
/// could never be tested against real data — not a bug in any one place, just
/// an option nobody had built.
///
/// Unset in release builds, where the sidecar's own data directory is the
/// correct answer and a developer's absolute path would be nonsense.
const SIDECAR_ENV_FILE: Option<&str> = option_env!("DUCT_SIDECAR_ENV_FILE");

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

/// Origin (`scheme://host[:port]`) of this shell's main window.
///
/// `None` for a bundled-frontend window, which has no remote origin to hand a
/// browser — the sidecar keeps its own default in that case.
fn frontend_origin(app: &AppHandle) -> Option<String> {
    let window = app.config().app.windows.first()?;
    match &window.url {
        WebviewUrl::External(url) => Some(url.origin().ascii_serialization()),
        _ => None,
    }
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
    // Where the sidecar should send a browser after sign-in. Its own default is
    // `tauri://localhost`, which is right for CORS and useless as a redirect: the
    // OAuth callback lands in the *system browser*, which cannot follow that
    // scheme. Every consumer of FRONTEND_ORIGIN builds a URL a browser has to
    // open — the sign-in relay, invite links, the connections redirect — so it
    // has to be the origin this shell actually shows.
    if let Some(origin) = frontend_origin(app) {
        command.env("FRONTEND_ORIGIN", origin);
    }

    // Python block-buffers stdout when it is a pipe rather than a terminal, so
    // without this the log we just went to the trouble of relaying arrives in
    // 8 KB gulps — i.e. never, for the handful of lines that precede a crash.
    command.env("PYTHONUNBUFFERED", "1");

    command.env("GOOGLE_DESKTOP_OAUTH_CLIENT_ID", GOOGLE_DESKTOP_CLIENT_ID);
    if let Some(secret) = GOOGLE_DESKTOP_CLIENT_SECRET.filter(|s| !s.is_empty()) {
        command.env("GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET", secret);
    }

    // Same rule as everything else in this block: set what the bundle cannot
    // otherwise have, and never overwrite what someone chose. A developer who
    // exports DUCT_ENV_FILE for one run beats whatever was compiled in.
    if std::env::var_os("DUCT_ENV_FILE").is_none() {
        if let Some(path) = SIDECAR_ENV_FILE.filter(|s| !s.is_empty()) {
            command.env("DUCT_ENV_FILE", path);
        }
    }

    // The key the sidecar encrypts stored connector credentials with, minted
    // into the OS keychain on first run.
    //
    // Skipped when one is already exported, which is the same rule the rest of
    // this block follows: we set what the bundle cannot otherwise have, and
    // never overwrite what someone chose. It matters more here than for
    // FRONTEND_ORIGIN — shadowing the wrong key does not misconfigure a run, it
    // orphans every row already encrypted with the right one. A developer
    // pinning DUCT_ENV_FILE at an env file with its own key should export that
    // key too, for the same reason.
    //
    // Failing is not fatal. A Linux box with no Secret Service daemon loses
    // stored connector credentials for the session — everything else, including
    // provider keys held in this same absent keychain, was already degraded in
    // exactly the same way — so the app starts and says why.
    // ...and skipped entirely when an env file is pinned, which is the case the
    // comment above anticipated and the shell can now create for itself.
    //
    // Two reasons, either sufficient. The env file carries its own
    // CREDENTIALS_ENCRYPTION_KEY, so minting a machine-local one here would
    // encrypt rows into that deployment's database which the deployment itself
    // cannot decrypt — silent corruption, discovered much later by whoever
    // tries to read them back. And reading the keychain *blocks on a modal
    // password prompt* whenever the app's code identity changes, which for a
    // dev build is every rebuild: `try_spawn` then sits on that dialog and
    // never reaches `spawn()`, so the sidecar simply never starts and the only
    // symptom is a shell that says its backend stopped responding.
    let env_file_pinned =
        std::env::var_os("DUCT_ENV_FILE").is_some() || SIDECAR_ENV_FILE.is_some_and(|s| !s.is_empty());
    if !env_file_pinned && std::env::var_os("CREDENTIALS_ENCRYPTION_KEY").is_none() {
        match crate::credentials_encryption_key() {
            Ok(key) => {
                command.env("CREDENTIALS_ENCRYPTION_KEY", key);
            }
            Err(err) => {
                eprintln!(
                    "duct: no keychain for the credentials key ({err}). \
                     Connecting a data source will not persist this session."
                );
            }
        }
    }

    // Crash reporting for the bundled backend, only with consent. `local_server`
    // blanks SENTRY_DSN by default on purpose — a laptop is not a deployment —
    // so passing nothing here leaves that default intact. Passing it explicitly
    // is the only way the sidecar ever reports, which keeps the decision in one
    // place the user controls rather than spread across two processes.
    let consented = crate::telemetry::default_data_dir()
        .map(|dir| crate::telemetry::read_prefs(&dir).enabled)
        .unwrap_or(false);
    if consented {
        if let Some(dsn) = crate::telemetry::SENTRY_DSN.filter(|d| !d.is_empty()) {
            command.env("SENTRY_DSN", dsn);
            // Without this the sidecar's own localhost guard drops every event:
            // it binds 127.0.0.1, which server.py treats as "not deployed".
            command.env("SENTRY_ENABLE_LOCALHOST", "1");
        }
    }

    // The sidecar is a console binary — that is deliberate, its stdout carries
    // the handshake. On Windows, spawning a console binary from a GUI app also
    // pops a visible console window on every launch. CREATE_NO_WINDOW suppresses
    // the window while leaving the redirected pipes intact.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
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

        // Keep draining stdout, and *forward* what we read. The pipe has a
        // finite buffer; if the sidecar ever writes past it with nobody
        // reading, it blocks on write and the whole backend wedges. Dropping
        // the lines on the floor avoids that too, but it also throws away
        // uvicorn's access log — which is the only record of which request
        // failed. Relaying to our own stderr (already inherited, so it reaches
        // `Console.app` and `tauri dev`) keeps the pipe clear *and* keeps a
        // shipped build diagnosable.
        let mut relayed = String::new();
        while let Ok(n) = reader.read_line(&mut relayed) {
            if n == 0 {
                break;
            }
            eprint!("[sidecar] {relayed}");
            relayed.clear();
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
