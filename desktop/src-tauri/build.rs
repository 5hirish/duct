fn main() {
    // `sidecar.rs` reads this through `option_env!`, which cargo does not track
    // on its own — without this line, changing the secret leaves a stale binary
    // compiled against the old value.
    println!("cargo:rerun-if-env-changed=DUCT_GOOGLE_CLIENT_SECRET");

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
        ])),
    )
    .expect("failed to run tauri-build");
}
