## Context

Today `whispy2` is one binary launched from a terminal (`v2/whispy2/src/main.rs`):

- the terminal holds its permissions and receives its log (`eprintln!`);
- `machine.rs` is a pure state machine fed `Event`s (`FnDown`, `FnUp`, `Tick`,
  `V1Running`…);
- `controller.rs` runs it on its own thread, with two ports: `Capture` and
  `Inserter`;
- `mac/` holds the adapters: `fn_key`, `microphone` (cpal, the default device
  opened per dictation), `inserter`, `menu_bar`.

V1's packaging is reusable as it stands:

- `packaging/macos/create_signing_cert.sh` creates the "Whispy Local Signing"
  identity;
- `build_app.sh` signs with `--options runtime` and
  `whispy.entitlements`;
- `reinstall.sh` replaces, relaunches and waits.

`ort` is built with `copy-dylibs`, but on macOS it links ONNX Runtime
statically (measured while building the bundle: the release binary loads only
system libraries and has no `LC_RPATH`), so the bundle carries no dylib; the
bundle script still handles one if a future `ort` ships it dynamically.
`whisper-rs` was built with `metal` unconditionally.

## Goals / Non-Goals

**Goals:**
- Every new piece is either portable or sits behind a port, so that
  `v2-linux-wayland` only adds adapters.
- No new behaviour inside `machine.rs`: the socket and Fn both produce
  the events it already knows.
- The trial numbers come from files V2 writes as it runs, not from a separate
  tool you have to remember to start.

**Non-Goals:**
- Notarisation, a DMG, auto-update, an icon redesign. V2 reuses V1's
  `whispy.icns`.
- Making V2 able to stop V1. The cohabitation rule stays as it is.

## Decisions

### 1. The socket is the trigger seam and the instance lock
`control.rs` (portable, `std::os::unix::net`):
- binds `~/.whispy/v2/control.sock` in a 0700 directory, then chmods the
  socket to 0600;
- runs one accept thread with one short-lived handler per connection;
- maps `start` → `FnDown(now)`, `stop` → `FnUp(now)`, `toggle` →
  `FnDown` then `FnUp` 50 ms later (under the 0.3 s tap threshold);
- answers `status` through a new `Input::Query(Sender<Status>)` on the
  controller channel.

The machine stays unaware of where an edge came from. That is why a `stop`
while idle is ignored for free. The reply to `start` while yielding comes from
the `Status` (`yielded`), read before forwarding.

The lock works by connecting first (decision recorded in the spec):
- a successful connect → exit 0;
- `ECONNREFUSED` → unlink the stale file and bind;
- any other error → bind anyway and log.

*Alternatives:*
- `flock` on a pid file: a second mechanism, and stale-file handling all the
  same.
- An HTTP server like V1's `:9090`: needs a token and an open port, and
  nothing gains from it.
- The 0700 directory is the real guard. Permissions on a socket file alone
  are not portable across BSD and Linux.

### 2. Trigger provenance for the journal
The controller records which source produced the `FnDown` that started the
dictation. To do this, `Input::Event` gains a `Source` (fn | socket) next to
the event. Only the controller looks at it; the machine never sees it.

### 3. Logging is a tiny portable module, not a crate
`log.rs`:
- a global `Mutex<File>` writer opened at startup with mode 0600;
- size checked before each write, renamed to `.1` past 5 MB;
- mirrored to stderr when stderr is a TTY, so `cargo run` stays readable;
- `eprintln!("[whispy2] …")` call sites become `log::line(…)`.

The dictation line repeats the journal fields: duration, latency, engine,
outcome, length.

*Alternative:* the `log` + `simplelog`/`flexi_logger` crates. They are three
dependencies for twenty lines of code, against the V2 rule that every crate
must be justified.

### 4. The journal is written by the worker after delivery
The worker thread already holds the transcript and runs the delivery. It
receives the release `Instant` with the job, and appends after `deliver`
returns, or after the empty, heard-nothing, lost or failed outcome. Each line
is a hand-written JSON object with fixed keys, written with
`OpenOptions::append` at mode 0600. Strings in the line are only enum names,
the engine name and the device name; the device name is escaped.

### 5. Heard-nothing is decided before the pipeline
In `transcribe`, before the pipeline is called:
- duration ≥ 0.5 s and no 30 ms window with RMS × 10 ≥ 0.1 (V1's level scale; a sample-peak reading of 0.1 called quiet speech silence on the first real dictations) → outcome `heard_nothing`;
- `Event::Transcribed(String::new())` keeps the machine path unchanged;
- a separate `Input::Note` carries the device name.

The microphone adapter exposes the name of the device it opened (`cpal`
`Device::name`). The thresholds are V1's, measured on its deaf takes, and
their constants carry a comment that points back there.

### 6. Indicator and sound behind one port
A new `Feedback` port:
- `show(Phase)`, with `Phase` = Recording | Transcribing | Hidden;
- `level(f32)`;
- `alert()`.

The controller drives `show` from the machine state, and `alert` on heard
nothing. The microphone pushes the RMS level of each block, throttled to
20 Hz.

The mac adapter (`mac/indicator.rs`) is an `NSPanel`:
- `NonactivatingPanel` style, status-bar level;
- collection behaviour `canJoinAllSpaces | fullScreenAuxiliary |
  stationary`, `ignoresMouseEvents`;
- holds an `NSLevelIndicator` and a label;
- placed bottom-centre of the screen with the mouse;
- updates hop to the main queue (`dispatch2`, already used).

`alert()` is `NSSound(named: "Basso")`, the same sound as V1.

*Alternatives:*
- A custom-drawn view: it needs `define_class!` and drawing code. Not worth
  it for a trial; the ferrofluid look is a parity question.
- `NSUserNotification`: deprecated, and it needs authorisation.

### 7. Login item through SMAppService, bundle-only
`mac/login_item.rs` uses `objc2-service-management` (pinned with `=`):
- `SMAppService.mainApp` gives the status, then `register` or `unregister`;
- `RequiresApproval` → the menu note « Approve Whispy V2 in System Settings
  → Login Items ».

The item is enabled only when the executable sits inside a `.app`
(`NSBundle.mainBundle.bundlePath` ends in `.app`). That rule is pure and
unit-tested.

### 8. Bundle assembly is a shell script beside V1's
`packaging/macos-v2/build_bundle.sh` runs these steps:
1. `cargo build --release -p whispy2`;
2. lays out `Whispy V2.app/Contents/{MacOS,Resources,Info.plist}`;
3. copies `whispy2` and every `*.dylib` from `target/release`;
4. checks with `otool -L` that each dylib is found through `@executable_path`
   (adding the rpath with `install_name_tool` if not);
5. copies `whispy.icns`;
6. signs, exactly like V1: `--force --deep --options runtime --entitlements`
   with a V2 copy of `whispy.entitlements` (audio-input, apple-events);
7. `codesign --verify --strict`.

`packaging/macos-v2/reinstall.sh` runs these steps:
1. quits the running V2 (`osascript quit`, then the socket disappearing as
   the signal);
2. `ditto` into `/Applications`;
3. `open`;
4. polls `status` on the socket for 30 s;
5. on failure, tails the log.

`Makefile`: `v2-app` and `v2-reinstall`.

`Info.plist`:
- `CFBundleIdentifier com.whispy.v2`, `CFBundleName Whispy V2`;
- `LSUIElement true`;
- `NSMicrophoneUsageDescription`;
- `NSAppleEventsUsageDescription` (System Events ⌘V).

### 9. `metal` only on macOS
`whispy-core/Cargo.toml` moves `whisper-rs` to
`[target.'cfg(target_os = "macos")'.dependencies]` with `metal`, and adds a
non-Metal entry for other targets. This change does not build Linux in CI; it
only keeps the workspace from requiring Metal there.

### 10. `banc --trial` lives in the bench, not the app
A new `banc/src/trial.rs` holds:
- a journal parser;
- the V1 log parser, with regexes on the two V1 line formats
  (`Transcribed a ([0-9.]+)s clip`, `Lost speech: … for a ([0-9.]+)s clip`);
- the percentiles: nearest-rank, the same definition as the existing p95 in
  `measure.rs`.

The lost share is weighted by duration, because V1 logs per streamed chunk
and V2 per dictation, so counts would not compare.

### 11. TRIAL.md is a procedure, not a report
`v2/TRIAL.md` holds:
- the setup: quit V1, turn off its "Start at login", install V2, turn on V2's
  login item, run `banc --labelled` once at the start;
- the minimum length;
- the five criteria, each naming the command and number it is read from;
- where the result goes: the go/no-go and the list of missed V1 features
  open the parity change, `openspec/changes/v2-parity/`.

## Risks / Trade-offs

- **`libonnxruntime` not found inside the bundle** (rpath pointing at
  `target/`). → The bundle script checks `otool -L`/`-l` and fixes the rpath.
  The "runs without the build tree" scenario catches what remains.
- **whisper.cpp Metal shaders not embedded** (the fallback fails only once
  outside the build tree). → Check that the whisper-rs 0.16 build embeds the
  Metal library (`GGML_METAL_EMBED_LIBRARY`). The manual scenario forces a
  reprise with a quiet clip through `banc --transcribe` against the installed
  binary's environment.
- **Hardened runtime blocks loading the unsigned onnxruntime dylib.** →
  `--deep` signs the nested dylibs with the same identity. If Library
  Validation still refuses it, add
  `com.apple.security.cs.disable-library-validation` to the V2 entitlements
  and record why.
- **The duration-weighted lost share undercounts V2 partial losses.** In a
  long dictation, one silent 20 s piece is not flagged as lost. → Accepted for
  the trial and stated in TRIAL.md. The piece-level count is a parity
  candidate.
- **A socket `start` without a `stop`** (a crashed client). → The existing
  5-minute watchdog ends it, with the text going to the clipboard only.
- **Both the indicator and the menu icon show the state.** → Accepted: the
  icon stays the always-on cue, and the panel is visible only during a
  dictation.

## Migration Plan

1. Branch from `origin/main`, which has `banc --labelled` (#34).
2. Implement, then run `make v2-reinstall` and grant the three permissions to
   Whispy V2 once.
3. Run the trial per `v2/TRIAL.md`.
4. To roll back: quit V2, turn its login item off, relaunch
   `/Applications/Whispy.app`. Nothing of V1 was changed.
