fn main() {
    // `sidecar.rs` reads this through `option_env!`, which cargo does not track
    // on its own — without this line, changing the secret leaves a stale binary
    // compiled against the old value.
    println!("cargo:rerun-if-env-changed=GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET");
    bake_desktop_client_secret();
    // Same mechanism again, for which database the bundled sidecar talks to.
    println!("cargo:rerun-if-env-changed=DUCT_SIDECAR_ENV_FILE");
    bake_sidecar_env_file();
    // Same reason: telemetry.rs reads this through `option_env!`. Same spelling
    // as the backend's own variable, so one value serves both halves.
    println!("cargo:rerun-if-env-changed=SENTRY_DSN");

    // App-defined commands are allowed by default only for *local* content. The
    // window loads a remote origin (app.getduct.ai, or the Next dev server in a
    // dev build), and a capability can only grant permissions that exist — so
    // without this these commands are unreachable from the webview and every
    // invoke fails with "<command> not allowed. Plugin not found".
    //
    // Declaring them here autogenerates `allow-*` / `deny-*` permissions that
    // `capabilities/*.json` can reference. Keep this list in sync with the
    // `tauri::generate_handler!` list in `src/lib.rs`.
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
            "get_provider_key",
            "set_provider_key",
            "delete_provider_key",
            "get_shell_info",
            "get_sidecar_info",
            "open_external",
            "check_for_update",
            "install_update",
            "get_telemetry_settings",
            "set_telemetry_enabled",
        ])),
    )
    .expect("failed to run tauri-build");
}

/// Supply the Google desktop client secret from `backend/.env.local` when the
/// build environment does not already carry it.
///
/// `option_env!` reads whatever environment happened to start the build, so
/// without this the value depends on *where* you build from: a terminal that
/// exported it produces a working app, the IDE run config right next to it
/// produces one that cannot sign in — and nothing about the build says which
/// you got. CI never reaches this path: it sets the variable from the repo
/// secret, and `.env.local` does not exist on a runner.
///
/// The emitted `cargo:rustc-env` line lands in `target/**/output`, which is
/// gitignored and local. The value is an installed-app secret that Google
/// documents as non-confidential (see the constant in `src/sidecar.rs`).
fn bake_desktop_client_secret() {
    const KEY: &str = "GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET";

    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let env_path = format!("{manifest}/../../backend/.env.local");
    println!("cargo:rerun-if-changed={env_path}");

    if std::env::var(KEY).is_ok_and(|v| !v.trim().is_empty()) {
        return;
    }
    let Ok(contents) = std::fs::read_to_string(&env_path) else {
        return;
    };
    for line in contents.lines() {
        let Some(rest) = line.trim().strip_prefix(&format!("{KEY}=")) else {
            continue;
        };
        let value = rest.trim().trim_matches('"').trim_matches('\'');
        if !value.is_empty() {
            println!("cargo:rustc-env={KEY}={value}");
        }
        return;
    }
}

/// Point a **debug** bundle's sidecar at the developer's `backend/.env.local`,
/// so a dev build runs against staging rather than an empty local SQLite.
///
/// This is the difference between a desktop build you can test and one you
/// cannot. The sidecar has always been able to run against a deployment — it
/// declines to migrate a database it did not create — but an app launched from
/// Spotlight or the Finder inherits no shell environment, so there was no way
/// to *tell* an installed bundle which database to use. The result was that the
/// desktop app could only ever see its own empty SQLite, and every attempt to
/// test it against real data failed somewhere further downstream.
///
/// Emitted through `cargo:rustc-env` rather than left to the ambient
/// environment, for the reason the secret above documents: `option_env!` reads
/// whatever environment started the build, so the same command from a different
/// shell produced a different app and nothing said which one you got.
///
/// Debug only. A release build's sidecar owns the SQLite file in its own data
/// directory, and a developer's absolute path would be meaningless on a user's
/// machine — so release gets nothing and keeps the local-first behaviour.
fn bake_sidecar_env_file() {
    const KEY: &str = "DUCT_SIDECAR_ENV_FILE";

    if let Ok(explicit) = std::env::var(KEY) {
        if !explicit.trim().is_empty() {
            println!("cargo:rustc-env={KEY}={explicit}");
            return;
        }
    }

    if std::env::var("PROFILE").as_deref() != Ok("debug") {
        return;
    }

    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let env_path = format!("{manifest}/../../backend/.env.local");
    println!("cargo:rerun-if-changed={env_path}");
    if std::fs::metadata(&env_path).is_ok() {
        println!("cargo:rustc-env={KEY}={env_path}");
    }
}
