//! The reporting backend, chosen at compile time.
//!
//! Everything that knows a vendor's name lives in this file and nowhere else.
//! `telemetry` above it decides *whether* to report; this decides *how*, and
//! the no-op below is a complete implementation of the same contract — so a
//! build without the feature is not a build with holes in it.
//!
//! Selected by the `crash-reporting` Cargo feature, which is **not** on by
//! default. The builds we distribute turn it on; anyone building Duct for
//! themselves gets a shell with no reporting code compiled in at all, and can
//! either leave it that way, point `POSTHOG_HOST` at their own PostHog, or
//! write a third arm here against the four functions below.
//!
//! The vendor is PostHog error tracking, spoken to directly: one `$exception`
//! event per report, POSTed to the capture endpoint the moment it is made. No
//! SDK, no queue, no background transport — there is nothing to flush, so a
//! report is either sent or it is not.

/// What PostHog is sent, built without touching the network.
///
/// Compiled for tests as well as for the feature: CI checks a pull request on
/// default features only, so without this the payload a release sends would
/// first be compiled by the release itself.
#[cfg(any(test, feature = "crash-reporting"))]
mod event {
    use std::path::Path;

    use serde_json::{json, Value};

    /// Names this reporter in PostHog's SDK views, apart from posthog-js.
    const LIB: &str = "duct-desktop-native";
    /// Beside `telemetry.json`, but a file of its own: `write_prefs` rewrites
    /// the preference file whole, and an id that changed every time the switch
    /// was touched would count one install as several.
    const ID_FILE: &str = "telemetry-id";
    /// Enough to see the crash site and how it was reached. Deep recursion
    /// would otherwise send hundreds of copies of the same frame.
    const MAX_FRAMES: usize = 64;

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum Kind {
        /// A Rust panic: unhandled, and the thread — often the app — is going down.
        Panic,
        /// `capture_message`: the shell noticed something broken and carried on.
        Message,
    }

    #[derive(Debug, Default, PartialEq, Eq)]
    pub struct Frame {
        pub function: Option<String>,
        pub filename: Option<String>,
        pub lineno: Option<u32>,
        pub colno: Option<u32>,
    }

    pub struct Report {
        pub kind: Kind,
        pub message: String,
        /// Where a panic was raised. `#[track_caller]` compiles this into the
        /// binary, so it survives where the stack has no names at all — a
        /// Windows build, which ships no PDB to name them from.
        pub location: Option<(String, u32, u32)>,
        /// Innermost first, as `std::backtrace` prints them.
        pub frames: Vec<Frame>,
    }

    /// Frames out of `std::backtrace::Backtrace`'s `Display` output.
    ///
    /// Parsed rather than walked: std's structured accessor is unstable, and
    /// the `backtrace` crate would link a second copy of the symbolizer std
    /// already carries. The format has not moved since std grew `Backtrace`.
    /// If it ever does, reports lose their frames and keep everything else, and
    /// `a_real_backtrace_parses_into_named_frames` fails on the toolchain bump
    /// that did it.
    pub fn parse_backtrace(rendered: &str) -> Vec<Frame> {
        let mut frames: Vec<Frame> = Vec::new();
        for line in rendered.lines() {
            let line = line.trim_start();
            if let Some(at) = line.strip_prefix("at ") {
                if let Some(frame) = frames.last_mut() {
                    let (file, lineno, colno) = split_location(at);
                    frame.filename = Some(file.to_string());
                    frame.lineno = lineno;
                    frame.colno = colno;
                }
                continue;
            }
            // `   7: name` opens a frame. A bare `name` beneath it is a function
            // inlined into that frame, and to a reader it is a frame of its own.
            let name = match line.split_once(": ") {
                Some((index, name))
                    if !index.is_empty() && index.bytes().all(|b| b.is_ascii_digit()) =>
                {
                    name
                }
                _ => line,
            };
            if !name.is_empty() {
                frames.push(Frame {
                    function: (name != "<unknown>").then(|| name.to_string()),
                    ..Frame::default()
                });
            }
        }
        frames
    }

    /// `path:line:col` or `path:line`, split from the right so a Windows drive
    /// letter is never read as a line number.
    fn split_location(at: &str) -> (&str, Option<u32>, Option<u32>) {
        let Some((rest, last)) = at.rsplit_once(':') else {
            return (at, None, None);
        };
        let Ok(last) = last.parse() else {
            return (at, None, None);
        };
        match rest.rsplit_once(':').map(|(path, mid)| (path, mid.parse())) {
            Some((path, Ok(line))) => (path, Some(line), Some(last)),
            _ => (rest, Some(last), None),
        }
    }

    /// The capture request body for one report.
    pub fn build(report: Report, api_key: &str, distinct_id: &str, home: Option<&str>) -> Value {
        let panic = report.kind == Kind::Panic;
        let mut exception = json!({
            // A message has no exception type of its own. `Error` is what
            // posthog-js files a captured string under, so both surfaces read alike.
            "type": if panic { "Panic" } else { "Error" },
            "value": scrub_home(&report.message, home),
            "mechanism": {
                "type": if panic { "panic" } else { "generic" },
                "handled": !panic,
                // A message's stack is where it was reported from, not where
                // anything was thrown, and `synthetic` tells PostHog exactly that.
                "synthetic": !panic,
            },
        });
        let frames = wire_frames(report.kind, report.frames, home);
        if !frames.is_empty() {
            exception["stacktrace"] = json!({ "type": "raw", "frames": frames });
        }

        let (os, platform) = os_and_platform();
        let version = env!("CARGO_PKG_VERSION");
        let mut properties = json!({
            "$exception_list": [exception],
            "$exception_level": if panic { "fatal" } else { "error" },
            "$lib": LIB,
            "$lib_version": version,
            "shell_version": version,
            "$os": os,
            "platform": platform,
            "arch": std::env::consts::ARCH,
            "surface": "desktop-native",
            // Personless. An anonymous install id is all there is to attach,
            // and events that create person profiles are billed at a higher rate.
            "$process_person_profile": false,
        });
        if let Some((file, line, column)) = report.location {
            properties["$exception_panic_file"] = json!(scrub_home(&file, home));
            properties["$exception_panic_line"] = json!(line);
            properties["$exception_panic_column"] = json!(column);
        }

        // No `timestamp`: every report leaves the moment it is made, so the
        // server's clock is a better witness than the laptop's.
        json!({
            "api_key": api_key,
            "event": "$exception",
            "distinct_id": distinct_id,
            "properties": properties,
        })
    }

    /// Frames in PostHog's wire order (outermost first, crash site last), with
    /// the reporter's own frames cut off the top so every issue does not open
    /// on the same three lines of panic machinery.
    fn wire_frames(kind: Kind, mut frames: Vec<Frame>, home: Option<&str>) -> Vec<Value> {
        // Matched loosely on purpose. The same function is
        // `desktop_lib::telemetry::reporter::backend::capture_message` in a
        // release build and bare `capture_message` in a dev one (see `in_app`).
        let is_marker = |f: &Frame| {
            f.function.as_deref().is_some_and(|n| match kind {
                Kind::Panic => n.contains("__rust_end_short_backtrace"),
                Kind::Message => n.ends_with("capture_message"),
            })
        };
        if let Some(end) = frames.iter().position(is_marker) {
            frames.drain(..=end);
        }
        // A frame with no name and no file is an address nobody can resolve:
        // there is no symbol upload for the server to look it up in.
        frames.retain(|f| f.function.is_some() || f.filename.is_some());
        frames.truncate(MAX_FRAMES);
        frames
            .into_iter()
            .rev()
            .map(|f| {
                json!({
                    "platform": "native",
                    "lang": "rust",
                    "in_app": in_app(&f),
                    "function": f.function,
                    "filename": f.filename.map(|path| scrub_home(&path, home)),
                    "lineno": f.lineno,
                    "colno": f.colno,
                    "synthetic": false,
                    // Named in process from the binary's own symbols. With no
                    // instruction address alongside, the server keeps it as sent.
                    "client_resolved": true,
                })
            })
            .collect()
    }

    /// Ours is `desktop_lib`, plus the two-line `desktop` binary around it.
    ///
    /// Two tests, one per build. A release build has no DWARF (Cargo drops it
    /// from that profile by default), so frames are named from the symbol
    /// table, with their full path, and have no file. A dev build keeps line
    /// tables only, which name this crate's functions bare — `spawn`, not
    /// `desktop_lib::sidecar::spawn` — so there the file is what says whose
    /// frame it is.
    fn in_app(frame: &Frame) -> bool {
        let by_name = frame
            .function
            .as_deref()
            .is_some_and(|name| name.contains("desktop_lib::") || name.starts_with("desktop::"));
        let by_file = frame.filename.as_deref().is_some_and(|path| {
            path.starts_with("./src/")
                || path.contains("src-tauri/src/")
                || path.contains(r"src-tauri\src\")
        });
        by_name || by_file
    }

    /// The user's home directory, out of a path or a message: data-dir paths
    /// and macOS user folders carry the account name. Build-machine paths (the
    /// CI runner's, rustc's) name nobody and are left alone.
    fn scrub_home(text: &str, home: Option<&str>) -> String {
        let home = home
            .map(|h| h.trim_end_matches(['/', '\\']))
            .filter(|h| !h.is_empty());
        match home {
            Some(home) => text
                .replace(&format!("{home}/"), "~/")
                .replace(&format!("{home}\\"), "~\\"),
            None => text.to_string(),
        }
    }

    /// `$os` in PostHog's own spelling, so native and webview events share its
    /// OS breakdowns; `platform` is the short form, for filtering by hand.
    fn os_and_platform() -> (&'static str, &'static str) {
        match std::env::consts::OS {
            "macos" => ("Mac OS X", "mac"),
            "windows" => ("Windows", "windows"),
            "linux" => ("Linux", "linux"),
            other => (other, other),
        }
    }

    /// An anonymous id for this install, made on the first report and kept.
    ///
    /// Random rather than derived from the machine, so it identifies nothing
    /// but itself. It is there so that a hundred reports from one wedged
    /// install read as one install, not as a hundred people. A file that cannot
    /// be written still yields an id; it just lasts one run.
    pub fn install_id(data_dir: &Path) -> String {
        let path = data_dir.join(ID_FILE);
        if let Ok(existing) = std::fs::read_to_string(&path) {
            let existing = existing.trim();
            if is_uuid(existing) {
                return existing.to_string();
            }
        }
        let id = new_uuid();
        let _ = std::fs::create_dir_all(data_dir).and_then(|()| std::fs::write(&path, &id));
        id
    }

    fn is_uuid(s: &str) -> bool {
        s.len() == 36
            && s.char_indices().all(|(i, c)| match i {
                8 | 13 | 18 | 23 => c == '-',
                _ => c.is_ascii_hexdigit(),
            })
    }

    /// RFC 4122 version 4. The shell already links getrandom for its keys, so
    /// this costs no crate. The randomness source failing on a desktop OS is
    /// not a case worth a fallback; it yields the nil-ish id below, which is
    /// still a valid id.
    fn new_uuid() -> String {
        let mut b = [0u8; 16];
        let _ = getrandom::fill(&mut b);
        b[6] = (b[6] & 0x0f) | 0x40;
        b[8] = (b[8] & 0x3f) | 0x80;
        let hex: String = b.iter().map(|x| format!("{x:02x}")).collect();
        format!(
            "{}-{}-{}-{}-{}",
            &hex[0..8],
            &hex[8..12],
            &hex[12..16],
            &hex[16..20],
            &hex[20..32]
        )
    }

    #[cfg(test)]
    mod tests {
        //! The payload, pinned without a network. If PostHog stops filing these
        //! reports, compare what it now documents against these assertions
        //! before suspecting the transport.

        use super::*;
        use crate::test_support::scratch_dir;

        fn frame(function: &str) -> Frame {
            Frame {
                function: Some(function.to_string()),
                ..Frame::default()
            }
        }

        fn panic_report(frames: Vec<Frame>) -> Report {
            Report {
                kind: Kind::Panic,
                message: "called `Option::unwrap()` on a `None` value".into(),
                location: Some(("src/lib.rs".into(), 42, 7)),
                frames,
            }
        }

        #[test]
        fn a_panic_is_an_unhandled_fatal_exception_with_its_frames_crash_site_last() {
            // Innermost first and named as a release build names them (v0
            // demangling, rustc 1.97): the capture itself, the reporter, std's
            // panic machinery, then the code that actually panicked.
            let frames = vec![
                frame("<std::backtrace::Backtrace>::create"),
                frame("desktop_lib::telemetry::reporter::backend::init::{closure#0}"),
                frame("std::panicking::panic_with_hook"),
                frame(concat!(
                    "std::sys::backtrace::__rust_end_short_backtrace",
                    "::<std::panicking::begin_panic_handler::{closure#0}, !>"
                )),
                frame("core::panicking::panic_fmt"),
                frame("desktop_lib::sidecar::spawn"),
                frame("desktop_lib::run::{closure#0}"),
                Frame::default(),
                frame("std::rt::lang_start_internal"),
            ];
            let body = build(panic_report(frames), "phc_test", "install-1", None);

            assert_eq!(body["api_key"], "phc_test");
            assert_eq!(body["event"], "$exception");
            assert_eq!(body["distinct_id"], "install-1");
            assert!(body.get("timestamp").is_none());

            let props = &body["properties"];
            assert_eq!(props["$exception_level"], "fatal");
            assert_eq!(props["$exception_panic_file"], "src/lib.rs");
            assert_eq!(props["$exception_panic_line"], 42);
            assert_eq!(props["$exception_panic_column"], 7);
            assert_eq!(props["$lib"], "duct-desktop-native");
            assert_eq!(props["$lib_version"], env!("CARGO_PKG_VERSION"));
            assert_eq!(props["shell_version"], env!("CARGO_PKG_VERSION"));
            assert_eq!(props["surface"], "desktop-native");
            assert_eq!(props["$process_person_profile"], false);
            assert_eq!(props["arch"], std::env::consts::ARCH);
            assert!(["mac", "windows", "linux"].contains(&props["platform"].as_str().unwrap()));
            assert!(props["$os"].is_string());

            let exception = &props["$exception_list"][0];
            assert_eq!(exception["type"], "Panic");
            assert_eq!(exception["value"], "called `Option::unwrap()` on a `None` value");
            assert_eq!(
                exception["mechanism"],
                json!({ "type": "panic", "handled": false, "synthetic": false })
            );
            assert_eq!(exception["stacktrace"]["type"], "raw");

            let frames = exception["stacktrace"]["frames"].as_array().unwrap();
            let names: Vec<&str> = frames.iter().map(|f| f["function"].as_str().unwrap()).collect();
            // The reporter and panic machinery are gone, the nameless frame is
            // dropped, and the order is reversed so the crash site comes last.
            assert_eq!(
                names,
                [
                    "std::rt::lang_start_internal",
                    "desktop_lib::run::{closure#0}",
                    "desktop_lib::sidecar::spawn",
                    "core::panicking::panic_fmt",
                ]
            );
            let in_app: Vec<bool> = frames.iter().map(|f| f["in_app"].as_bool().unwrap()).collect();
            assert_eq!(in_app, [false, true, true, false]);
            for f in frames {
                assert_eq!(f["platform"], "native");
                assert_eq!(f["lang"], "rust");
                assert_eq!(f["client_resolved"], true);
                assert_eq!(f["synthetic"], false);
            }
        }

        #[test]
        fn a_message_is_a_handled_error_reported_from_its_caller() {
            // Named as a dev build names this crate's frames: bare, with the
            // file saying whose they are.
            let ours = |name: &str, file: &str| Frame {
                function: Some(name.into()),
                filename: Some(file.into()),
                lineno: Some(1),
                colno: Some(1),
            };
            let report = Report {
                kind: Kind::Message,
                message: "sidecar failed to start: no handshake".into(),
                location: None,
                frames: vec![
                    frame("<std::backtrace::Backtrace>::force_capture"),
                    ours("capture_message", "./src/telemetry/reporter.rs"),
                    ours("{closure#0}", "./src/lib.rs"),
                    frame("tauri::app::setup"),
                ],
            };
            let body = build(report, "phc_test", "install-1", None);
            let props = &body["properties"];
            assert_eq!(props["$exception_level"], "error");
            assert!(props.get("$exception_panic_file").is_none());

            let exception = &props["$exception_list"][0];
            assert_eq!(exception["type"], "Error");
            assert_eq!(
                exception["mechanism"],
                json!({ "type": "generic", "handled": true, "synthetic": true })
            );
            let frames = exception["stacktrace"]["frames"].as_array().unwrap();
            let names: Vec<&str> = frames.iter().map(|f| f["function"].as_str().unwrap()).collect();
            assert_eq!(names, ["tauri::app::setup", "{closure#0}"]);
            assert_eq!(frames[0]["in_app"], false);
            assert_eq!(frames[1]["in_app"], true, "a bare name in our file is ours");
        }

        #[test]
        fn no_frames_means_no_stacktrace_rather_than_an_empty_one() {
            let body = build(panic_report(Vec::new()), "phc_test", "install-1", None);
            assert!(body["properties"]["$exception_list"][0].get("stacktrace").is_none());
        }

        #[test]
        fn the_home_directory_never_leaves_the_machine() {
            let mut report = panic_report(vec![Frame {
                function: Some("desktop_lib::run".into()),
                filename: Some("/Users/alice/src/duct/desktop/src-tauri/src/lib.rs".into()),
                lineno: Some(1),
                colno: None,
            }]);
            report.message = "could not open /Users/alice/Library/Application Support/x".into();
            report.location = Some(("/Users/alice/src/duct/x.rs".into(), 1, 1));
            let body = build(report, "phc_test", "install-1", Some("/Users/alice/"));
            assert!(!body.to_string().contains("alice"), "{body}");
            let props = &body["properties"];
            assert_eq!(
                props["$exception_list"][0]["value"],
                "could not open ~/Library/Application Support/x"
            );

            let windows = build(
                Report {
                    kind: Kind::Message,
                    message: r"C:\Users\bob\AppData\Roaming\Duct is not writable".into(),
                    location: None,
                    frames: Vec::new(),
                },
                "phc_test",
                "install-1",
                Some(r"C:\Users\bob"),
            );
            assert!(!windows.to_string().contains("bob"), "{windows}");

            // A home of `/` would otherwise turn every path into `~`.
            assert_eq!(scrub_home("/usr/lib/x", Some("/")), "/usr/lib/x");
        }

        #[test]
        fn backtrace_text_parses_including_inlined_frames_and_windows_paths() {
            let rendered = "   0: desktop_lib::run::{closure#0}\n\
                            \x20            at ./src/lib.rs:1200:9\n\
                            \x20     desktop_lib::sidecar::spawn\n\
                            \x20            at C:\\work\\duct\\src\\sidecar.rs:388\n\
                            \x20  1: <unknown>\n\
                            \x20  2: std::rt::lang_start_internal\n";
            let frames = parse_backtrace(rendered);
            assert_eq!(
                frames,
                [
                    Frame {
                        function: Some("desktop_lib::run::{closure#0}".into()),
                        filename: Some("./src/lib.rs".into()),
                        lineno: Some(1200),
                        colno: Some(9),
                    },
                    Frame {
                        function: Some("desktop_lib::sidecar::spawn".into()),
                        filename: Some(r"C:\work\duct\src\sidecar.rs".into()),
                        lineno: Some(388),
                        colno: None,
                    },
                    Frame::default(),
                    frame("std::rt::lang_start_internal"),
                ]
            );
        }

        #[test]
        fn a_real_backtrace_parses_into_named_frames() {
            // The guard on the parser: if a toolchain changes std's format, this
            // is the test that says so, rather than a quiet release whose crash
            // reports have no stacks.
            let rendered = std::backtrace::Backtrace::force_capture().to_string();
            let frames = parse_backtrace(&rendered);
            let here = frames
                .iter()
                .find(|f| {
                    f.function
                        .as_deref()
                        .is_some_and(|n| n.contains("a_real_backtrace_parses_into_named_frames"))
                })
                .unwrap_or_else(|| panic!("this test's own frame is missing from:\n{rendered}"));
            // Test builds keep line tables for this crate (`profile.dev`), so
            // the frame has a file, and that file is what makes it ours.
            let file = here.filename.as_deref().unwrap_or_default();
            assert!(file.ends_with("reporter.rs"), "{here:?}");
            assert!(here.lineno.is_some(), "{here:?}");
            assert!(in_app(here), "{here:?}");
        }

        #[test]
        fn the_install_id_is_made_once_and_kept() {
            let root = scratch_dir("telemetry-install-id");
            // Absent and nested: the first report can come before anything has
            // created the data dir.
            let dir = root.join("not").join("yet");
            let first = install_id(&dir);
            assert!(is_uuid(&first), "{first}");
            assert_eq!(first.as_bytes()[14], b'4', "version 4: {first}");
            assert_eq!(install_id(&dir), first, "a second report, same run");

            // Garbage in the file is replaced, not sent.
            std::fs::write(dir.join(ID_FILE), "not an id").unwrap();
            let replaced = install_id(&dir);
            assert!(is_uuid(&replaced) && replaced != first);
            assert_eq!(install_id(&dir), replaced);

            // Two installs never share one.
            assert_ne!(install_id(&root.join("other")), replaced);
            let _ = std::fs::remove_dir_all(&root);
        }
    }
}

#[cfg(feature = "crash-reporting")]
mod backend {
    use std::backtrace::{Backtrace, BacktraceStatus};
    use std::cell::Cell;
    use std::panic::PanicHookInfo;
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
    use std::sync::mpsc;
    use std::time::Duration;

    use super::event::{self, Kind, Report};

    /// Nothing to hold. Each report is one request, sent as it happens, so
    /// there is no transport to keep alive. Kept in the contract for a reporter
    /// that has one.
    pub type Guard = ();

    /// Set at build time and read by `option_env!` while rustc compiles, NOT
    /// at runtime. A `phc_` project token is public by design — it writes
    /// events and evaluates flags but reads nothing back, which is why
    /// posthog-js puts one in every page — so the release workflow passes it as
    /// a repository variable, not a secret.
    const TOKEN: Option<&str> = option_env!("POSTHOG_PROJECT_TOKEN");
    /// Overridable for the EU cloud or a self-hosted PostHog.
    const HOST: Option<&str> = option_env!("POSTHOG_HOST");
    const DEFAULT_HOST: &str = "https://us.i.posthog.com";
    const CAPTURE_PATH: &str = "/i/v0/e/";

    /// The request's whole life, connection to response.
    const SEND_TIMEOUT: Duration = Duration::from_secs(3);
    /// How long a panicking thread waits for its report. Longer than the send
    /// by the time it takes to name the frames, which on first use means
    /// reading the binary's symbol table.
    const PANIC_WAIT: Duration = Duration::from_secs(5);
    /// A panic in a command the page calls on every render would otherwise
    /// send one report per render, per user, for as long as the bug ships. The
    /// first few carry everything the rest would.
    const MAX_REPORTS_PER_RUN: u32 = 10;

    /// What `init` was told at launch. Turning reporting on mid-session takes
    /// effect at the next launch, as it always has for the sidecar.
    static ENABLED: AtomicBool = AtomicBool::new(false);
    static SENT: AtomicU32 = AtomicU32::new(0);

    thread_local! {
        /// A panic on the thread that is sending a report must not report
        /// itself: that is a loop, bounded only by `MAX_REPORTS_PER_RUN`.
        static ON_REPORTER_THREAD: Cell<bool> = const { Cell::new(false) };
    }

    fn token() -> Option<&'static str> {
        TOKEN.filter(|t| !t.is_empty())
    }

    fn host() -> &'static str {
        HOST.filter(|h| !h.is_empty())
            .unwrap_or(DEFAULT_HOST)
            .trim_end_matches('/')
    }

    pub fn is_available() -> bool {
        token().is_some()
    }

    pub fn init(enabled: bool) -> Guard {
        if token().is_none() || !enabled {
            return;
        }
        ENABLED.store(true, Ordering::Release);
        // Chained, not replaced: the default hook is what prints the panic to
        // stderr, and a dev reading a terminal still wants that line.
        let previous = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            report_panic(info);
            previous(info);
        }));
    }

    /// Runs on the panicking thread, before it unwinds or the process aborts,
    /// and waits for the send: after this returns there may be no process
    /// left to send from.
    fn report_panic(info: &PanicHookInfo<'_>) {
        if ON_REPORTER_THREAD.get() {
            return;
        }
        let report = Report {
            kind: Kind::Panic,
            message: info.payload_as_str().unwrap_or("Box<dyn Any>").to_string(),
            location: info
                .location()
                .map(|l| (l.file().to_string(), l.line(), l.column())),
            frames: Vec::new(),
        };
        if let Some(sent) = send(report, Backtrace::force_capture()) {
            let _ = sent.recv_timeout(PANIC_WAIT);
        }
    }

    /// Never inlined, so the frame it leaves is the one `event` cuts off the
    /// top of the stack; inlined, the caller would be cut instead.
    #[inline(never)]
    pub fn capture_message(message: &str) {
        let report = Report {
            kind: Kind::Message,
            message: message.to_string(),
            location: None,
            frames: Vec::new(),
        };
        // Not waited for. The shell is carrying on, and its callers are on the
        // UI thread, which a slow network must not freeze.
        let _ = send(report, Backtrace::force_capture());
    }

    /// Sends one report from a thread of its own, returning a receiver that
    /// closes when it is done. A thread rather than the caller's because the
    /// caller may be a tokio worker, where reqwest's blocking client panics.
    fn send(mut report: Report, backtrace: Backtrace) -> Option<mpsc::Receiver<()>> {
        if !ENABLED.load(Ordering::Acquire)
            || SENT.fetch_add(1, Ordering::Relaxed) >= MAX_REPORTS_PER_RUN
        {
            return None;
        }
        let token = token()?;
        let (done, sent) = mpsc::channel::<()>();
        std::thread::Builder::new()
            .name("duct-crash-report".into())
            .spawn(move || {
                // Moved in so it drops when this thread ends, however it ends:
                // that is what a waiting panic hook hears.
                let _done = done;
                ON_REPORTER_THREAD.set(true);
                let Some(data_dir) = crate::telemetry::default_data_dir() else {
                    return;
                };
                // Asked again at send time, not only at launch: someone who
                // switches reporting off is not reported on for the rest of
                // the session.
                if !crate::telemetry::is_enabled(&data_dir) {
                    return;
                }
                // Named here, not where it was captured: `capture_message` is
                // called from the UI thread, and naming frames can mean reading
                // the binary's whole symbol table.
                if backtrace.status() == BacktraceStatus::Captured {
                    report.frames = event::parse_backtrace(&backtrace.to_string());
                }
                let home =
                    crate::telemetry::dirs_home().map(|h| h.to_string_lossy().into_owned());
                let distinct_id = event::install_id(&data_dir);
                let body = event::build(report, token, &distinct_id, home.as_deref());
                let result = reqwest::blocking::Client::builder()
                    .timeout(SEND_TIMEOUT)
                    .build()
                    .and_then(|client| {
                        client
                            .post(format!("{}{CAPTURE_PATH}", host()))
                            .json(&body)
                            .send()?
                            .error_for_status()
                    });
                if let Err(err) = result {
                    eprintln!("duct: crash report not sent: {err}");
                }
            })
            .ok()?;
        Some(sent)
    }

    pub fn sidecar_env(enabled: bool) -> Vec<(&'static str, String)> {
        match token() {
            // The names the backend reads. An environment variable rather than
            // the secrets line on stdin, because a project token is not a
            // secret (see `TOKEN`).
            Some(token) if enabled => vec![
                ("POSTHOG_API_KEY", token.to_string()),
                ("POSTHOG_HOST", host().to_string()),
                // The sidecar binds 127.0.0.1, and the backend treats a
                // loopback deployment as "not deployed" and sends nothing
                // (`service/analytics.py`) unless told otherwise. The user's
                // switch is that telling.
                ("POSTHOG_ENABLE_LOCALHOST", "true".to_string()),
            ],
            _ => Vec::new(),
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
