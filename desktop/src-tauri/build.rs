fn main() {
    // `sidecar.rs` reads this through `option_env!`, which cargo does not track
    // on its own — without this line, changing the secret leaves a stale binary
    // compiled against the old value.
    println!("cargo:rerun-if-env-changed=DUCT_GOOGLE_CLIENT_SECRET");
    tauri_build::build()
}
