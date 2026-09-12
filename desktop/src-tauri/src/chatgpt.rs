//! "Continue with ChatGPT" — sign in to the user's own ChatGPT plan and run
//! Duct's OpenAI slot on it, no API key and no extra bill.
//!
//! The shell owns this flow because nobody else can. The hosted backend runs
//! on Railway and cannot bind the user's `localhost:1455`, which is the only
//! redirect the ChatGPT OAuth client accepts; the web page cannot hold a
//! refresh token anywhere safer than `localStorage`. So the shell runs the
//! PKCE flow in the system browser, catches the callback on the loopback
//! port, exchanges the code, and keeps the whole token bundle in the OS
//! keychain beside the provider keys.
//!
//! **The refresh token never leaves this machine.** It is the user's ChatGPT
//! account — history, workspace, everything — not a key they pasted. What the
//! web app gets from `chatgpt_credential` is the hour-long *access* token and
//! the account id, which it sends as request headers exactly the way an API
//! key travels (`app/src/lib/chatgpt.js`, `backend/agents/core/codex.py`).
//! The backend can spend that token for an hour and can never mint another.
//!
//! The endpoints, client id and redirect are the ones `langchain-openai`'s
//! `chatgpt_oauth.py` documents; the token bundle is stored under its own
//! keychain service so a stray `set_provider_key("openai", …)` can never
//! overwrite it, and it is deliberately *not* `~/.codex/auth.json` — rotating
//! a refresh token there signs the user out of the Codex CLI.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine as _;
use keyring::{Entry, Error as KeyringError};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager, Url};
use tauri_plugin_opener::OpenerExt;

use crate::describe_keyring_error;

const CLIENT_ID: &str = "app_EMoamEEZ73f0CkXaXp7hrann";
const AUTHORIZE_URL: &str = "https://auth.openai.com/oauth/authorize";
const TOKEN_URL: &str = "https://auth.openai.com/oauth/token";
const SCOPE: &str = "openid profile email offline_access";
/// The one redirect the client is registered for. Port and path are fixed by
/// OpenAI, not chosen here; `localhost` rather than `127.0.0.1` for the same
/// reason.
const REDIRECT_HOST: &str = "localhost";
const REDIRECT_PORT: u16 = 1455;
const REDIRECT_PATH: &str = "/auth/callback";
/// Where OpenAI puts the ChatGPT account inside the id_token's claims.
const AUTH_CLAIMS: &str = "https://api.openai.com/auth";

/// How long the browser tab may sit open before the sign-in is abandoned.
const LOGIN_TIMEOUT: Duration = Duration::from_secs(300);
/// Refresh this far ahead of expiry so a token handed to the web app is never
/// already dead by the time the request lands.
const REFRESH_SKEW_SECS: u64 = 300;
const HTTP_TIMEOUT: Duration = Duration::from_secs(30);
/// What a pending login resolves with when it is abandoned on purpose. The
/// web app treats it as nothing to show, the way it treats `"revoked"`.
const CANCELLED: &str = "cancelled";
/// How often the listener looks for a connection or a cancellation.
const ACCEPT_POLL: Duration = Duration::from_millis(50);
/// How long a new sign-in waits for the one it replaced to let go of the
/// port. That one polls at `ACCEPT_POLL`, so this is generous.
const PORT_HANDOVER: Duration = Duration::from_secs(2);

/// Its own service, not `KEYCHAIN_SERVICE`: a provider key is one string
/// keyed by provider id, and this is a bundle that must not be readable or
/// clobberable through that door.
const KEYCHAIN_SERVICE: &str = "ai.getduct.desktop.chatgpt";
const KEYCHAIN_ACCOUNT: &str = "session";

/// The token bundle, serialised as JSON into one keychain item.
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Session {
    access_token: String,
    refresh_token: String,
    /// Unix seconds.
    expires_at: u64,
    #[serde(default)]
    account_id: String,
    #[serde(default)]
    plan_type: String,
    #[serde(default)]
    email: String,
}

/// What the web app may know. Never a token.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Status {
    pub connected: bool,
    pub plan_type: String,
    pub email: String,
    pub account_id: String,
}

/// The two request headers, and nothing else.
#[derive(Clone, Debug, Serialize)]
pub struct Credential {
    pub access_token: String,
    pub account_id: String,
}

impl Session {
    fn status(&self) -> Status {
        Status {
            connected: true,
            plan_type: self.plan_type.clone(),
            email: self.email.clone(),
            account_id: self.account_id.clone(),
        }
    }

    fn needs_refresh(&self) -> bool {
        now_secs() + REFRESH_SKEW_SECS >= self.expires_at
    }
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// Keychain
// ---------------------------------------------------------------------------

fn entry() -> Result<Entry, String> {
    Entry::new(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT).map_err(describe_keyring_error)
}

fn load() -> Result<Option<Session>, String> {
    match entry()?.get_password() {
        Ok(raw) => match serde_json::from_str::<Session>(&raw) {
            Ok(session) => Ok(Some(session)),
            // A bundle this build cannot read is treated as absent: the fix
            // is a fresh sign-in, and telling the user to "repair" a keychain
            // item is not a thing they can do.
            Err(_) => Ok(None),
        },
        Err(KeyringError::NoEntry) => Ok(None),
        Err(e) => Err(describe_keyring_error(e)),
    }
}

fn store(session: &Session) -> Result<(), String> {
    let raw = serde_json::to_string(session).map_err(|e| e.to_string())?;
    entry()?.set_password(&raw).map_err(describe_keyring_error)
}

fn clear() -> Result<(), String> {
    match entry()?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(e) => Err(describe_keyring_error(e)),
    }
}

// ---------------------------------------------------------------------------
// PKCE
// ---------------------------------------------------------------------------

fn random_urlsafe(bytes: usize) -> Result<String, String> {
    let mut buf = vec![0u8; bytes];
    getrandom::fill(&mut buf).map_err(|e| format!("could not gather randomness: {e}"))?;
    Ok(URL_SAFE_NO_PAD.encode(buf))
}

fn pkce_pair() -> Result<(String, String), String> {
    let verifier = random_urlsafe(64)?;
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    Ok((verifier, challenge))
}

fn redirect_uri() -> String {
    format!("http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}")
}

fn authorize_url(state: &str, challenge: &str) -> Result<Url, String> {
    let mut url = Url::parse(AUTHORIZE_URL).map_err(|e| e.to_string())?;
    url.query_pairs_mut()
        .append_pair("client_id", CLIENT_ID)
        .append_pair("response_type", "code")
        .append_pair("redirect_uri", &redirect_uri())
        .append_pair("scope", SCOPE)
        .append_pair("code_challenge", challenge)
        .append_pair("code_challenge_method", "S256")
        .append_pair("state", state);
    Ok(url)
}

// ---------------------------------------------------------------------------
// The loopback callback
// ---------------------------------------------------------------------------

/// The sign-in currently waiting on the loopback port, if any.
///
/// One at a time, because the port is fixed by OpenAI: a second attempt can
/// only ever fail to bind behind the first. By the time anyone clicks again,
/// the first is a browser tab they closed — a closed tab tells this process
/// nothing, and the listener would otherwise sit on the port for the rest of
/// `LOGIN_TIMEOUT` reporting "address in use" to every retry. So a new sign-in
/// replaces the pending one, and `chatgpt_login_cancel` ends it on demand.
static PENDING: Mutex<Option<Arc<AtomicBool>>> = Mutex::new(None);

fn pending() -> std::sync::MutexGuard<'static, Option<Arc<AtomicBool>>> {
    // A poisoned lock holds an `Option` that is valid either way.
    PENDING.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// Tell the pending sign-in, if any, to stop. Returns at once; the listener
/// notices within one poll and releases the port as it returns.
fn cancel_pending() {
    if let Some(flag) = pending().take() {
        flag.store(true, Ordering::Relaxed);
    }
}

fn register_pending() -> Arc<AtomicBool> {
    let flag = Arc::new(AtomicBool::new(false));
    *pending() = Some(flag.clone());
    flag
}

/// Forget `flag` once its sign-in has ended — unless a newer sign-in has
/// registered since, in which case the slot is theirs.
fn clear_pending(flag: &Arc<AtomicBool>) {
    let mut slot = pending();
    if slot.as_ref().is_some_and(|current| Arc::ptr_eq(current, flag)) {
        *slot = None;
    }
}

/// What the browser brought back: an authorization code, or OpenAI's error.
/// The `state` has already been checked — a callback carrying someone else's
/// never gets this far.
#[derive(Debug)]
struct Callback {
    code: Option<String>,
    error: Option<String>,
}

/// Take the registered port, giving a sign-in this one replaced a moment to
/// release it.
fn bind_listener() -> Result<TcpListener, String> {
    let give_up = Instant::now() + PORT_HANDOVER;
    loop {
        match TcpListener::bind((REDIRECT_HOST, REDIRECT_PORT)) {
            Ok(listener) => {
                listener
                    .set_nonblocking(true)
                    .map_err(|e| format!("could not configure the sign-in listener: {e}"))?;
                return Ok(listener);
            }
            Err(e) if e.kind() == std::io::ErrorKind::AddrInUse && Instant::now() < give_up => {
                std::thread::sleep(ACCEPT_POLL);
            }
            Err(e) => {
                return Err(format!(
                    "could not listen on {REDIRECT_HOST}:{REDIRECT_PORT} for the ChatGPT sign-in ({e}). \
                     Another app is using the port — most likely the Codex CLI signing in. Finish or \
                     close that, then try again."
                ))
            }
        }
    }
}

/// Serve callbacks on the bound port until ours arrives, the deadline passes,
/// or `cancel` is raised; the port is released as this returns.
///
/// Hand-rolled on `TcpListener` rather than pulling in an HTTP server crate:
/// one GET, one response, and the request line is the only thing parsed. The
/// query string carries the auth code, so nothing here ever logs a request.
fn wait_for_callback(
    listener: TcpListener,
    deadline: Instant,
    cancel: Arc<AtomicBool>,
    expected_state: &str,
) -> Result<Callback, String> {
    while Instant::now() < deadline {
        if cancel.load(Ordering::Relaxed) {
            return Err(CANCELLED.into());
        }
        match listener.accept() {
            Ok((stream, _)) => {
                if let Some(callback) = handle_request(stream, expected_state) {
                    return Ok(callback);
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(ACCEPT_POLL);
            }
            Err(e) => return Err(format!("sign-in listener failed: {e}")),
        }
    }
    Err("Timed out waiting for the ChatGPT sign-in to finish in your browser.".into())
}

/// Parse one request; answer it; return the callback if it was ours.
///
/// Browsers also fetch `/favicon.ico` and the like while the tab is open —
/// those get a 404 and `None`, and the listener keeps waiting. So does a
/// callback whose `state` is not the one this sign-in minted: anything on
/// this machine can hit the port, and a stray hit must not end the wait for
/// the tab we actually opened.
fn handle_request(mut stream: TcpStream, expected_state: &str) -> Option<Callback> {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let mut buf = [0u8; 8192];
    let n = stream.read(&mut buf).ok()?;
    let head = String::from_utf8_lossy(&buf[..n]);
    let target = head.lines().next()?.split_whitespace().nth(1)?.to_string();
    let url = Url::parse(&format!("http://{REDIRECT_HOST}{target}")).ok()?;
    if url.path() != REDIRECT_PATH {
        respond(&mut stream, 404, "Not found");
        return None;
    }
    let param = |key: &str| url.query_pairs().find(|(k, _)| k == key).map(|(_, v)| v.into_owned());
    if param("state").as_deref() != Some(expected_state) {
        let body = page(
            "Sign-in failed",
            "This sign-in was not started by the Duct that is open now. Go back to Duct and try again.",
        );
        respond(&mut stream, 200, &body);
        return None;
    }
    let callback = Callback { code: param("code"), error: param("error").or_else(|| param("error_description")) };
    let body = if callback.error.is_some() {
        page("Sign-in failed", "ChatGPT did not complete the sign-in. Go back to Duct and try again.")
    } else {
        page("You're signed in", "Duct will run on your ChatGPT plan. You can close this tab.")
    };
    respond(&mut stream, 200, &body);
    Some(callback)
}

fn respond(stream: &mut TcpStream, status: u16, body: &str) {
    let reason = if status == 200 { "OK" } else { "Not Found" };
    let response = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: text/html; charset=utf-8\r\n\
         Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes());
    let _ = stream.flush();
}

/// The page the browser tab is left on. Plain and self-contained: it is served
/// from the user's own machine with no assets to fetch.
fn page(heading: &str, message: &str) -> String {
    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\
         <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\
         <title>{heading} · Duct</title>\
         <style>body{{margin:0;min-height:100vh;display:grid;place-items:center;\
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f7f6;color:#0d0f1a}}\
         main{{width:min(420px,calc(100vw - 40px));padding:32px;border:1px solid #e6e6e3;border-radius:16px;background:#fff}}\
         .mark{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff5c00;margin-bottom:18px}}\
         h1{{font-size:22px;margin:0 0 8px}}p{{margin:0;color:#5c6174;line-height:1.5}}</style></head>\
         <body><main><span class=\"mark\"></span><h1>{heading}</h1><p>{message}</p></main></body></html>"
    )
}

// ---------------------------------------------------------------------------
// Token endpoint
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: Option<String>,
    #[serde(default)]
    expires_in: Option<u64>,
    #[serde(default)]
    id_token: Option<String>,
}

#[derive(Deserialize, Default)]
struct OAuthError {
    #[serde(default)]
    error: String,
    #[serde(default)]
    error_description: String,
}

async fn post_form(form: &[(&str, &str)]) -> Result<TokenResponse, String> {
    let client = reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .map_err(|e| e.to_string())?;
    let response = client
        .post(TOKEN_URL)
        .form(form)
        .header("Accept", "application/json")
        .send()
        .await
        .map_err(|e| format!("could not reach auth.openai.com: {e}"))?;
    let status = response.status();
    if !status.is_success() {
        let err = response.json::<OAuthError>().await.unwrap_or_default();
        if err.error == "invalid_grant" {
            return Err("revoked".into());
        }
        let detail = if err.error_description.is_empty() { err.error } else { err.error_description };
        return Err(format!("auth.openai.com answered {status}: {detail}"));
    }
    response
        .json::<TokenResponse>()
        .await
        .map_err(|e| format!("unexpected token response: {e}"))
}

/// Decode a JWT's payload without verifying it. Local claim extraction only —
/// the account id and plan for a status line; never an authorisation decision.
fn jwt_claims(token: &str) -> serde_json::Value {
    let Some(payload) = token.split('.').nth(1) else {
        return serde_json::Value::Null;
    };
    URL_SAFE_NO_PAD
        .decode(payload)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or(serde_json::Value::Null)
}

fn session_from(response: TokenResponse, previous_refresh: Option<String>) -> Result<Session, String> {
    let refresh_token = response
        .refresh_token
        .or(previous_refresh)
        .ok_or("the sign-in returned no refresh token; try again")?;
    let expires_in = response.expires_in.filter(|s| *s > 0).ok_or("the sign-in returned no expiry")?;
    let claims = response.id_token.as_deref().map(jwt_claims).unwrap_or(serde_json::Value::Null);
    let auth = &claims[AUTH_CLAIMS];
    let text = |v: &serde_json::Value| v.as_str().unwrap_or("").to_string();
    Ok(Session {
        access_token: response.access_token,
        refresh_token,
        expires_at: now_secs() + expires_in,
        account_id: text(&auth["chatgpt_account_id"]),
        plan_type: text(&auth["chatgpt_plan_type"]),
        email: text(&claims["email"]),
    })
}

async fn refresh(existing: Session) -> Result<Session, String> {
    let response = post_form(&[
        ("grant_type", "refresh_token"),
        ("refresh_token", &existing.refresh_token),
        ("client_id", CLIENT_ID),
    ])
    .await;
    match response {
        Ok(fresh) => {
            let mut session = session_from(fresh, Some(existing.refresh_token))?;
            // A refresh carries no id_token; keep what the login learned.
            if session.account_id.is_empty() {
                session.account_id = existing.account_id;
            }
            if session.plan_type.is_empty() {
                session.plan_type = existing.plan_type;
            }
            if session.email.is_empty() {
                session.email = existing.email;
            }
            store(&session)?;
            Ok(session)
        }
        Err(e) if e == "revoked" => {
            // The user signed out of ChatGPT or revoked the app. A dead bundle
            // in the keychain would keep reporting "connected" forever.
            let _ = clear();
            Err("revoked".into())
        }
        Err(e) => Err(e),
    }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// Whether a ChatGPT sign-in is held, and for whom. Reads the keychain only.
#[tauri::command]
pub fn chatgpt_status() -> Result<Status, String> {
    Ok(load()?.map(|s| s.status()).unwrap_or_default())
}

/// Run the sign-in: system browser → loopback callback → token exchange →
/// keychain. Resolves once the bundle is stored, or with why it was not:
/// `"cancelled"` when this sign-in was abandoned by the button or replaced by
/// a newer click, and a sentence for everything else.
#[tauri::command]
pub async fn chatgpt_login(app: AppHandle) -> Result<Status, String> {
    let (verifier, challenge) = pkce_pair()?;
    let state = random_urlsafe(32)?;
    let url = authorize_url(&state, &challenge)?;

    // Whatever was waiting is a tab the user gave up on; this click is the
    // retry. Replace it rather than reporting its port as taken.
    cancel_pending();

    // Bind *before* opening the browser, and on this task rather than on the
    // listener's thread: a fast redirect would otherwise race the bind, and a
    // bind that fails must fail here — not after a tab is open with nowhere
    // to land.
    let listener = tauri::async_runtime::spawn_blocking(bind_listener)
        .await
        .map_err(|e| format!("sign-in listener stopped: {e}"))??;
    let cancel = register_pending();
    let deadline = Instant::now() + LOGIN_TIMEOUT;
    let waiter = {
        let cancel = cancel.clone();
        let state = state.clone();
        tauri::async_runtime::spawn_blocking(move || wait_for_callback(listener, deadline, cancel, &state))
    };

    if let Err(e) = app.opener().open_url(url.as_str(), None::<&str>) {
        cancel.store(true, Ordering::Relaxed);
        clear_pending(&cancel);
        return Err(format!("could not open the browser: {e}"));
    }

    let waited = waiter.await;
    clear_pending(&cancel);
    let callback = waited.map_err(|e| format!("sign-in listener stopped: {e}"))??;
    if let Some(error) = callback.error {
        return Err(format!("ChatGPT declined the sign-in: {error}"));
    }
    let code = callback.code.ok_or("the sign-in returned no authorization code")?;

    let response = post_form(&[
        ("grant_type", "authorization_code"),
        ("code", &code),
        ("redirect_uri", &redirect_uri()),
        ("client_id", CLIENT_ID),
        ("code_verifier", &verifier),
    ])
    .await?;
    let session = session_from(response, None)?;
    store(&session)?;

    // The user is looking at a browser tab; bring them back.
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    Ok(session.status())
}

/// Abandon the sign-in waiting on the port, if any. The pending
/// `chatgpt_login` resolves with `"cancelled"` and the port is released. A
/// sign-in that already finished is untouched — that is `chatgpt_logout`.
#[tauri::command]
pub fn chatgpt_login_cancel() {
    cancel_pending();
}

/// The headers for one request: a live access token and the account id.
/// Refreshes first when the token is within five minutes of expiry. `None`
/// when there is no sign-in; `Err("revoked")` when there was one and ChatGPT
/// no longer honours it — the web app answers both by offering the button.
#[tauri::command]
pub async fn chatgpt_credential() -> Result<Option<Credential>, String> {
    let Some(session) = load()? else {
        return Ok(None);
    };
    let session = if session.needs_refresh() { refresh(session).await? } else { session };
    Ok(Some(Credential {
        access_token: session.access_token,
        account_id: session.account_id,
    }))
}

/// Forget the sign-in. The app registration at OpenAI is untouched — that is
/// the user's to revoke from their ChatGPT settings.
#[tauri::command]
pub fn chatgpt_logout() -> Result<(), String> {
    clear()
}


#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::thread;

    /// Both tests need the real, fixed port; cargo runs tests in parallel.
    static PORT: Mutex<()> = Mutex::new(());

    fn get(query: &str) -> String {
        let mut stream = TcpStream::connect((REDIRECT_HOST, REDIRECT_PORT)).expect("listener up");
        write!(stream, "GET {REDIRECT_PATH}?{query} HTTP/1.1\r\nHost: localhost\r\n\r\n").unwrap();
        let mut body = String::new();
        stream.read_to_string(&mut body).unwrap();
        body
    }

    #[test]
    fn cancel_ends_the_wait_and_frees_the_port() {
        let _port = PORT.lock().unwrap_or_else(|p| p.into_inner());
        let listener = bind_listener().expect("port free for the test");
        let cancel = Arc::new(AtomicBool::new(false));
        let waiter = {
            let cancel = cancel.clone();
            thread::spawn(move || wait_for_callback(listener, Instant::now() + LOGIN_TIMEOUT, cancel, "s"))
        };
        cancel.store(true, Ordering::Relaxed);
        assert_eq!(waiter.join().unwrap().unwrap_err(), CANCELLED);
        // The next sign-in must be able to take the port straight away.
        assert!(bind_listener().is_ok());
    }

    #[test]
    fn a_callback_with_someone_elses_state_does_not_end_the_wait() {
        let _port = PORT.lock().unwrap_or_else(|p| p.into_inner());
        let listener = bind_listener().expect("port free for the test");
        let cancel = Arc::new(AtomicBool::new(false));
        let waiter = thread::spawn(move || {
            wait_for_callback(listener, Instant::now() + LOGIN_TIMEOUT, cancel, "ours")
        });
        assert!(get("code=stray&state=theirs").contains("Sign-in failed"));
        assert!(get("code=abc&state=ours").contains("signed in"));
        let callback = waiter.join().unwrap().expect("our callback ends the wait");
        assert_eq!(callback.code.as_deref(), Some("abc"));
        assert!(callback.error.is_none());
    }
}
