fn main() {
    // `sidecar.rs` reads these through `option_env!`, which cargo does not track
    // on its own — without these lines, changing a value leaves a stale binary
    // compiled against the old one.
    //
    // Both halves of the Google credential, not just the secret: a fork signs in
    // against its own Google project, and an id baked from one project beside a
    // secret from another fails at the token exchange rather than at build time.
    for key in ["GOOGLE_DESKTOP_OAUTH_CLIENT_ID", "GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET"] {
        println!("cargo:rerun-if-env-changed={key}");
        bake_from_env_local(key);
    }
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

/// Supply `key` from `backend/.env.local` when the build environment does not
/// already carry it.
///
/// `option_env!` reads whatever environment happened to start the build, so
/// without this the value depends on *where* you build from: a terminal that
/// exported it produces a working app, the IDE run config right next to it
/// produces one that cannot sign in — and nothing about the build says which
/// you got. CI never reaches this path: it sets the variable from the repo
/// secret, and `.env.local` does not exist on a runner.
///
/// The same spelling the backend already uses, so one `.env.local` configures
/// the sidecar at runtime and the shell at compile time — which is also what
/// makes a fork's own Google client a one-file change rather than a code edit.
///
/// The emitted `cargo:rustc-env` line lands in `target/**/output`, which is
/// gitignored and local. The value is an installed-app secret that Google
/// documents as non-confidential (see the constant in `src/sidecar.rs`).
fn bake_from_env_local(key: &str) {
    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let env_path = format!("{manifest}/../../backend/.env.local");
    println!("cargo:rerun-if-changed={env_path}");

    if std::env::var(key).is_ok_and(|v| !v.trim().is_empty()) {
        return;
    }
    let Ok(contents) = std::fs::read_to_string(&env_path) else {
        return;
    };
    for line in contents.lines() {
        let Some(rest) = line.trim().strip_prefix(&format!("{key}=")) else {
            continue;
        };
        let value = rest.trim().trim_matches('"').trim_matches('\'');
        if !value.is_empty() {
            println!("cargo:rustc-env={key}={value}");
        }
        return;
    }
}
