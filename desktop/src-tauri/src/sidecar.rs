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
//! The shell's keychain copies travel the other way as exactly one JSON line
//! on the sidecar's stdin, written right after spawn and before the handshake
//! is read:
//!
//! ```text
//! {"duct_secrets":1,"DUCT_LOCAL_API_KEY":"…","DUCT_LOCAL_JWT_SECRET":"…",
//!  "CREDENTIALS_ENCRYPTION_KEY":"…","GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET":"…"}
//! ```
//!
//! Stdin rather than the environment, because a process environment is
//! readable by every other process the same user runs and is inherited by
//! every subprocess the backend starts; the pipe is read once by the sidecar
//! and by nothing else. The same pipe then stays open as the EOF watchdog.
//!
//! **onedir, not `externalBin`.** Tauri's `externalBin` copies a single file,
//! but the PyInstaller build has to be onedir — a onefile binary unpacks itself
//! to a temp dir at startup, which does not survive macOS signing and
//! notarization (see the spec's header). So the whole `duct-sidecar/` directory
//! ships as a bundle *resource* and we spawn the entry binary inside it.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

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
/// Tells the sidecar to exit when its stdin closes, which happens when this
/// process ends however it ends (`local_server.py` owns the flag).
const SIDECAR_EXIT_ON_STDIN_EOF: &str = "--exit-on-stdin-eof";
/// Tells the sidecar the first line on that same stdin is the secrets line
/// (`local_server.py` owns this flag too). A sidecar started without it reads
/// nothing from stdin, which is what a headless `--data-dir` run wants.
const SIDECAR_SECRETS_ON_STDIN: &str = "--secrets-on-stdin";
/// Marker field on the secrets line, the counterpart of `duct_sidecar` on the
/// handshake: the sidecar rejects a first line without it.
const SECRETS_LINE_MARKER: &str = "duct_secrets";
/// How long a closed stdin may take to stop the sidecar before it is killed.
/// The sidecar's own fallback fires at the same two seconds; this is the
/// shell's, for a sidecar too wedged to run even that.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(2);
const SHUTDOWN_POLL: Duration = Duration::from_millis(50);

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

/// The first stdout line, as the shell reads it.
///
/// Anything but the documented JSON object is a failed start, and the raw
/// line rides in the error on purpose: a traceback or "Address already in
/// use" from the frozen Python is the only clue the user (or Sentry) gets.
fn parse_handshake(line: &str) -> Result<SidecarInfo, String> {
    serde_json::from_str::<SidecarInfo>(line)
        .map_err(|e| format!("sidecar handshake was not valid JSON ({e}): {line}"))
}

/// The secrets line, as the sidecar reads it: one compact JSON object, one
/// trailing newline, no entry for a value we do not have.
///
/// Empty values are dropped rather than sent, for the same reason the old
/// environment path never set an empty variable: an empty string would shadow
/// whatever the sidecar's own environment or env file provides, and for the
/// encryption key that means orphaning every row encrypted with the right one.
/// `serde_json` escapes any newline inside a value, so the result is always
/// exactly one line however the keychain was filled.
fn secrets_line(pairs: &[(&str, String)]) -> String {
    let mut object = serde_json::Map::new();
    object.insert(SECRETS_LINE_MARKER.to_string(), serde_json::Value::from(1));
    for (name, value) in pairs {
        if !value.is_empty() {
            object.insert((*name).to_string(), serde_json::Value::String(value.clone()));
        }
    }
    let mut line = serde_json::Value::Object(object).to_string();
    line.push('\n');
    line
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

/// Lock one of the state's mutexes, poisoned or not.
///
/// A thread that panicked while holding one of these leaves a value that is
/// still a plain `Option`; refusing to read it would turn one crash into a
/// second, in whichever command asked next. Same pattern as `chatgpt.rs`.
fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
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

/// Whether this build has a sidecar to run at all.
///
/// The official build ships without one and talks to the hosted API; the
/// self-host build adds `bundle.resources` back and runs everything locally.
/// Both come from the same binary, so this is a runtime probe rather than a
/// cargo feature — a feature would mean two binaries, two capability sets and
/// two things to keep honest, and the answer is already sitting on disk.
///
/// `sidecar_path` also accepts the dev fallback under `backend/dist/`, which is
/// what makes `npm run dev` exercise the local path on a machine that has
/// frozen one. On a user's machine that path does not exist.
pub fn is_available(app: &AppHandle) -> bool {
    sidecar_path(app).is_ok()
}

/// Origin (`scheme://host[:port]`) of this shell's main window.
///
/// `None` for a bundled-frontend window, which has no remote origin to hand a
/// browser — the sidecar keeps its own default in that case. Read from the
/// same place as the deep-link destination and the navigation guard, so the
/// three can never disagree about where the app lives.
fn frontend_origin(app: &AppHandle) -> Option<String> {
    crate::configured_app_url(app).map(|url| url.origin().ascii_serialization())
}

/// Start the sidecar and read its handshake on a background thread.
///
/// Returns as soon as the process is spawned; `get_sidecar_info` reports `null`
/// until the handshake lands. Any failure is also recorded in `SidecarState` so
/// the webview learns about it through `get_sidecar_info` rather than hanging.
pub fn spawn(app: &AppHandle) -> Result<(), String> {
    let result = try_spawn(app);
    if let Err(ref err) = result {
        *lock(&app.state::<SidecarState>().error) = Some(err.clone());
    }
    result
}

fn try_spawn(app: &AppHandle) -> Result<(), String> {
    let bin = sidecar_path(app)?;

    let mut command = Command::new(&bin);
    // Both pair with the stdin pipe below: the sidecar's lifetime is tied to
    // this process's by a pipe rather than by a signal nobody may be left to
    // send, and the same pipe carries the secrets in before it falls silent.
    command.args([SIDECAR_EXIT_ON_STDIN_EOF, SIDECAR_SECRETS_ON_STDIN]);

    // What goes on the secrets line rather than in the environment. Collected
    // here and written once the child exists; the decisions about *which*
    // secret to send are unchanged from when each was an `env()` call.
    let mut secrets: Vec<(&str, String)> = Vec::new();

    // The frozen bundle deliberately ships no `.env`, so what the bundle cannot
    // otherwise know arrives from here. Only set what we actually have — an
    // empty value would otherwise shadow a dev's `backend/.env.local`.
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

    // The id identifies the app and stays in the environment; the secret is a
    // secret, so it rides the stdin line with the rest.
    command.env("GOOGLE_DESKTOP_OAUTH_CLIENT_ID", GOOGLE_DESKTOP_CLIENT_ID);
    if let Some(secret) = GOOGLE_DESKTOP_CLIENT_SECRET.filter(|s| !s.is_empty()) {
        secrets.push(("GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET", secret.to_string()));
    }

    // Same rule as everything else in this block: set what the bundle cannot
    // otherwise have, and never overwrite what someone chose. A developer who
    // exports DUCT_ENV_FILE for one run beats whatever was compiled in.
    if std::env::var_os("DUCT_ENV_FILE").is_none() {
        if let Some(path) = SIDECAR_ENV_FILE.filter(|s| !s.is_empty()) {
            command.env("DUCT_ENV_FILE", path);
        }
    }

    // The two secrets the sidecar used to mint into `0600` files beside its own
    // database. A file at `0600` is private to this *account*, not to this
    // *app*, so anything running as the user could read the key that drives the
    // loopback API and the one that signs its session tokens. They live in the
    // keychain now and travel on the stdin line; the sidecar prefers what it is
    // given and retires the file it finds, which is the whole migration. A
    // keychain that will not answer is not fatal — the sidecar falls back to
    // its file and a headless `--data-dir` run keeps working with no shell at
    // all.
    for (var, read) in [
        ("DUCT_LOCAL_API_KEY", crate::local_api_key as fn() -> Result<String, String>),
        ("DUCT_LOCAL_JWT_SECRET", crate::local_jwt_secret),
    ] {
        match read() {
            Ok(secret) => secrets.push((var, secret)),
            Err(err) => {
                eprintln!("duct: no keychain for {var} ({err}). Falling back to the data directory.");
            }
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
    // Skipped entirely when an env file is pinned, for two reasons, either
    // sufficient. The env file carries its own CREDENTIALS_ENCRYPTION_KEY, so
    // minting a machine-local one here would encrypt rows into that
    // deployment's database which the deployment itself cannot decrypt —
    // silent corruption, discovered much later by whoever tries to read them
    // back. And reading the keychain *blocks on a modal password prompt*
    // whenever the app's code identity changes, which for a dev build is every
    // rebuild: `try_spawn` then sits on that dialog and never reaches
    // `spawn()`, so the sidecar simply never starts and the only symptom is a
    // shell that says its backend stopped responding.
    //
    // Failing is not fatal. A Linux box with no Secret Service daemon loses
    // stored connector credentials for the session — everything else, including
    // provider keys held in this same absent keychain, was already degraded in
    // exactly the same way — so the app starts and says why.
    let env_file_pinned =
        std::env::var_os("DUCT_ENV_FILE").is_some() || SIDECAR_ENV_FILE.is_some_and(|s| !s.is_empty());
    if !env_file_pinned && std::env::var_os("CREDENTIALS_ENCRYPTION_KEY").is_none() {
        match crate::credentials_encryption_key() {
            Ok(key) => secrets.push(("CREDENTIALS_ENCRYPTION_KEY", key)),
            Err(err) => {
                eprintln!(
                    "duct: no keychain for the credentials key ({err}). \
                     Connecting a data source will not persist this session."
                );
            }
        }
    }

    // Crash reporting for the bundled backend, only with consent. `local_server`
    // blanks its own DSN by default on purpose — a laptop is not a deployment —
    // so passing nothing here leaves that default intact. Passing it explicitly
    // is the only way the sidecar ever reports, which keeps the decision in one
    // place the user controls rather than spread across two processes.
    //
    // Which variables that takes is the reporter's business, not this file's: a
    // build with no reporter compiled in returns none and the loop does nothing.
    let consented = crate::telemetry::default_data_dir()
        .map(|dir| crate::telemetry::is_enabled(&dir))
        .unwrap_or(false);
    for (key, value) in crate::telemetry::sidecar_env(consented) {
        command.env(key, value);
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
        // A pipe the sidecar reads for exactly two things: the secrets line,
        // then EOF. The write end lives in this process and nowhere else, so
        // it closes when this process ends — a clean quit, a crash, a
        // `kill -9`, a relaunch for an update — and `--exit-on-stdin-eof`
        // makes the sidecar exit on that. Until this the sidecar outlived all
        // but the clean quit, holding the SQLite file and the port. One
        // mechanism covers every platform and needs no dependency:
        // `PR_SET_PDEATHSIG` would cover Linux alone and a Job Object Windows
        // alone, and both want crates this one does not carry. The `Child` in
        // `SidecarState` holds the write end, so nothing may take `stdin` out
        // of it before `shutdown` does.
        .stdin(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to start sidecar at {}: {e}", bin.display()))?;

    // The sidecar blocks on this line before it does anything else, so it goes
    // out before the handshake reader starts. One line fits the pipe buffer
    // many times over, so the write cannot block on a sidecar that is slow to
    // read. A failed write is a failed start: the sidecar would otherwise boot
    // on freshly minted files and every request from the webview would 401.
    // Returning early drops `child`, which closes this write end, and the
    // sidecar exits on the EOF rather than lingering.
    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| "sidecar stdin was not captured".to_string())?;
        stdin
            .write_all(secrets_line(&secrets).as_bytes())
            .and_then(|()| stdin.flush())
            .map_err(|e| format!("sending the sidecar its secrets: {e}"))?;
    }

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar stdout was not captured".to_string())?;

    let state = app.state::<SidecarState>();
    *lock(&state.child) = Some(child);

    let handle = app.clone();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        let state = handle.state::<SidecarState>();

        match reader.read_line(&mut line) {
            Ok(0) => {
                *lock(&state.error) = Some("sidecar exited before printing its handshake".into());
                return;
            }
            Err(e) => {
                *lock(&state.error) = Some(format!("reading sidecar handshake: {e}"));
                return;
            }
            Ok(_) => {}
        }

        match parse_handshake(&line) {
            Ok(info) => *lock(&state.info) = Some(info),
            Err(e) => *lock(&state.error) = Some(e),
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
///
/// Closing its stdin is the request: the sidecar's watchdog turns the EOF into
/// the stop a SIGTERM would be, so in-flight requests finish and SQLite is left
/// tidy. The kill behind it is for a sidecar that does not get there in time;
/// an abrupt exit is what WAL recovers from, and what every exit used to be.
pub fn shutdown(app: &AppHandle) {
    let state = app.state::<SidecarState>();
    let Some(mut child) = lock(&state.child).take() else {
        return;
    };
    drop(child.stdin.take());
    let deadline = Instant::now() + SHUTDOWN_GRACE;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => std::thread::sleep(SHUTDOWN_POLL),
            Err(_) => break,
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

/// Handshake for the webview: `null` while still booting.
///
/// Errors surface as a command error so the app can show the reason rather than
/// polling forever.
#[tauri::command]
pub fn get_sidecar_info(state: State<'_, SidecarState>) -> Result<Option<SidecarInfo>, String> {
    if let Some(err) = lock(&state.error).clone() {
        return Err(err);
    }
    Ok(lock(&state.info).clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_documented_handshake_line_parses() {
        let line = r#"{"duct_sidecar":1,"url":"http://127.0.0.1:53124","port":53124,"api_key":"k","data_dir":"/tmp/d"}"#;
        let info = parse_handshake(line).expect("the shape local_server.py prints");
        assert_eq!(info.url, "http://127.0.0.1:53124");
        assert_eq!(info.port, 53124);
        assert_eq!(info.api_key, "k");
        assert_eq!(info.data_dir, "/tmp/d");
    }

    #[test]
    fn a_python_traceback_on_stdout_is_reported_verbatim() {
        // What the user sees when the frozen backend dies before serving: the
        // line itself, so "Address already in use" is not hidden behind
        // "invalid JSON".
        let err = parse_handshake("OSError: [Errno 48] Address already in use").unwrap_err();
        assert!(err.contains("not valid JSON"), "{err}");
        assert!(err.contains("Address already in use"), "{err}");
    }

    #[test]
    fn a_handshake_missing_a_field_the_webview_needs_is_rejected() {
        // `port` gone: the webview could not build its API base from this.
        let err = parse_handshake(r#"{"duct_sidecar":1,"url":"http://127.0.0.1:1","api_key":"k","data_dir":"d"}"#)
            .unwrap_err();
        assert!(err.contains("port"), "{err}");
    }

    #[test]
    fn the_secrets_line_is_the_object_local_server_reads() {
        let line = secrets_line(&[
            ("DUCT_LOCAL_API_KEY", "k".to_string()),
            ("CREDENTIALS_ENCRYPTION_KEY", "f".to_string()),
        ]);
        let parsed: serde_json::Value = serde_json::from_str(line.trim_end()).expect("one JSON object");
        assert_eq!(parsed[SECRETS_LINE_MARKER], 1);
        assert_eq!(parsed["DUCT_LOCAL_API_KEY"], "k");
        assert_eq!(parsed["CREDENTIALS_ENCRYPTION_KEY"], "f");
        assert_eq!(parsed.as_object().map(|o| o.len()), Some(3));
    }

    #[test]
    fn an_empty_value_is_not_sent() {
        // An empty variable used to be the bug: it shadowed the env file's key
        // and orphaned every row encrypted with it. Same rule on the line.
        let line = secrets_line(&[
            ("DUCT_LOCAL_API_KEY", "k".to_string()),
            ("CREDENTIALS_ENCRYPTION_KEY", String::new()),
        ]);
        let parsed: serde_json::Value = serde_json::from_str(line.trim_end()).unwrap();
        assert!(parsed.get("CREDENTIALS_ENCRYPTION_KEY").is_none(), "{line}");
        assert_eq!(parsed["DUCT_LOCAL_API_KEY"], "k");
    }

    #[test]
    fn the_line_is_exactly_one_line_whatever_the_values_hold() {
        // The sidecar reads one line and hands the rest of the stream to its
        // watchdog; a raw newline inside a value would split the object.
        let line = secrets_line(&[("DUCT_LOCAL_JWT_SECRET", "two\nlines".to_string())]);
        assert!(line.ends_with('\n'));
        assert_eq!(line.matches('\n').count(), 1, "{line:?}");
        let parsed: serde_json::Value = serde_json::from_str(line.trim_end()).unwrap();
        assert_eq!(parsed["DUCT_LOCAL_JWT_SECRET"], "two\nlines");
    }

    #[test]
    fn with_nothing_to_send_the_line_still_carries_the_marker() {
        // A keychain that answers nothing still gets a well-formed line, so the
        // sidecar falls back to its files instead of failing the start.
        assert_eq!(secrets_line(&[]), format!("{{\"{SECRETS_LINE_MARKER}\":1}}\n"));
    }
}
