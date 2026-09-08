//! The reporting backend, chosen at compile time.
//!
//! Everything that knows a vendor's name lives in this file and nowhere else.
//! `telemetry` above it decides *whether* to report; this decides *how*, and
//! the no-op below is a complete implementation of the same contract — so a
//! build without the feature is not a build with holes in it.
//!
//! Selected by the `crash-reporting` Cargo feature, which is **not** on by
//! default. The builds we distribute turn it on; anyone building Duct for
//! themselves gets a shell with no reporting dependency compiled in at all, and
//! can either leave it that way, point `SENTRY_DSN` at their own collector
//! (GlitchTip and self-hosted Sentry both speak the same protocol), or write a
//! third arm here against the four functions below.

#[cfg(feature = "crash-reporting")]
mod backend {
    /// Held for the life of the app — dropping it stops the background
    /// transport, so an unheld guard silently reports nothing.
    pub type Guard = Option<sentry::ClientInitGuard>;

    /// Set at build time so the value is not in the repository. Read by
    /// `option_env!` while rustc compiles, NOT at runtime.
    ///
    /// Deliberately the same name the backend reads at runtime and the same one
    /// `backend/.env.local` already defines — a shell set up for the backend
    /// builds a reporting shell with no extra step, and there is one spelling
    /// to remember across all three processes.
    const DSN: Option<&str> = option_env!("SENTRY_DSN");

    fn dsn() -> Option<&'static str> {
        DSN.filter(|d| !d.is_empty())
    }

    pub fn is_available() -> bool {
        dsn().is_some()
    }

    pub fn init(enabled: bool) -> Guard {
        let dsn = dsn()?;
        if !enabled {
            return None;
        }
        // Built by mutation, not a struct literal: `ClientOptions` is
        // `#[non_exhaustive]` as of sentry 0.49, so `..Default::default()` does
        // not compile from outside the crate.
        let mut options = sentry::ClientOptions::default();
        options.release = sentry::release_name!();
        // The shell handles the user's provider API keys and OAuth codes.
        // Nothing here should ever carry them, but the default is off
        // regardless — this is a crash reporter, not an analytics pipe.
        options.send_default_pii = false;
        Some(sentry::init((dsn, options)))
    }

    pub fn capture_message(message: &str) {
        sentry::capture_message(message, sentry::Level::Error);
    }

    pub fn sidecar_env(enabled: bool) -> Vec<(&'static str, String)> {
        if !enabled {
            return Vec::new();
        }
        match dsn() {
            // SENTRY_ENABLE_LOCALHOST is not optional: the sidecar binds
            // 127.0.0.1, and `server.py` treats that as "not deployed" and
            // drops every event without it.
            Some(dsn) => vec![
                ("SENTRY_DSN", dsn.to_string()),
                ("SENTRY_ENABLE_LOCALHOST", "1".to_string()),
            ],
            None => Vec::new(),
        }
    }
}

#[cfg(not(feature = "crash-reporting"))]
mod backend {
    pub type Guard = ();

    pub fn is_available() -> bool {
        false
    }

    pub fn init(_enabled: bool) -> Guard {}

    pub fn capture_message(_message: &str) {}

    pub fn sidecar_env(_enabled: bool) -> Vec<(&'static str, String)> {
        Vec::new()
    }
}

pub use backend::{capture_message, init, is_available, sidecar_env, Guard};
