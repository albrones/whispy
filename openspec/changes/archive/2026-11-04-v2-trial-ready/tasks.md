# Tasks

## 1. Base and portability

- [x] 1.1 Branch from `origin/main` (it carries `banc --labelled`, #34). Move this change's directory onto the branch. Verify that `cargo test --release` passes in `v2/` before any edit.
- [x] 1.2 Make `whisper-rs`'s `metal` feature macOS-only in `v2/whispy-core/Cargo.toml` (design §9). Verify that `cargo build --release` and `cargo tree -e features -p whispy-core | grep metal` still show Metal on macOS.

## 2. Log file

- [x] 2.1 Add `whispy2/src/log.rs`: a 0600 file at `~/.whispy/v2/whispy2.log` (directory 0700), rotated to `.1` past 5 MB with the limit injectable for tests, and mirrored to stderr on a TTY. Verify the rotation and mode unit tests in a temporary directory.
- [x] 2.2 Route every `eprintln!("[whispy2] …")` in `main.rs`, `controller.rs` and `mac/` through the logger. Verify that `grep -rn 'eprintln!' v2/whispy2/src` lists only the logger's own TTY mirror.

## 3. Control socket and single instance

- [x] 3.1 Add `whispy2/src/control.rs` (design §1). It binds in a 0700 directory with a 0600 socket, `WHISPY_V2_SOCKET` overrides the path, and connecting first gives the instance check (live → exit, refused → replace). Verify unit tests for modes, the second instance and the stale socket.
- [x] 3.2 Add `Input::Query(Sender<Status>)` and an event `Source` (fn | socket) to the controller (design §2). Map `start`/`stop`/`toggle` to `FnDown`/`FnUp`, and give `status` a one-line JSON reply. Verify controller tests: start + 2 s + stop delivers the text, an unknown request gets `error`, and `start` while yielding is refused.
- [x] 3.3 Wire the socket into `main.rs` before the Fn tap, and remove the socket on Quit. Verify by hand: two launches leave one process, and `echo status | nc -U ~/.whispy/v2/control.sock` answers.
- [x] 3.4 Document the socket and its protocol in `v2/README.md`. Verify that the README's command works as written.

## 4. Heard nothing, device name, recording feedback

- [x] 4.1 Expose the opened device's name from `mac/microphone.rs` through the `Capture` port, and push the block RMS level throttled to 20 Hz. Verify with a fake capture in the controller tests.
- [x] 4.2 Add the heard-nothing gate before the pipeline (design §5): duration ≥ 0.5 s and peak < 0.1. No engine call, no lost clip, note « Microphone heard nothing (<device>) ». Verify the unit tests for the 3 s deaf take and the 0.3 s silent tap.
- [x] 4.3 Add the portable `Feedback` port (`show(Phase)`, `level`, `alert`) and drive it from machine states in the controller. Verify a controller test with a fake feedback that records the sequence recording → transcribing → hidden, and `alert` on heard nothing.
- [x] 4.4 Implement `mac/indicator.rs`: a non-activating `NSPanel` with an `NSLevelIndicator`, visible on all Spaces and over full screen, ignoring the mouse, updated on the main queue. `alert` plays `NSSound` "Basso". Add the needed `objc2-app-kit` features. Verify by hand: a dictation in TextEdit keeps the focus, the panel shows over a full-screen app, and a muted mic plays Basso.
- [x] 4.5 Update `v2/README.md` (indicator, heard nothing, log path). Verify that the documented paths match the code.

## 5. Dictation journal

- [x] 5.1 Pass the release `Instant` and the `Source` with each job. After each outcome, append one hand-written JSON line to `~/.whispy/v2/dictations.jsonl` (0600) with time, duration, latency, trigger, outcome, engine and length. Log a failed write without affecting the dictation. Verify unit tests: the inserted line has its fields, « secret » never appears, and an unwritable journal still delivers.
- [x] 5.2 Write the same dictation summary as one log line. Verify the controller test that reads the log.

## 6. App bundle, login item, reinstall

- [x] 6.1 Add `packaging/macos-v2/` with `Info.plist` (`com.whispy.v2`, `Whispy V2`, `LSUIElement`, microphone and Apple Events usage strings) and `whispy2.entitlements` copied from V1's. Verify with `plutil -lint`.
- [x] 6.2 Write `packaging/macos-v2/build_bundle.sh` (design §8). It builds, lays out the bundle, copies the binary, dylibs and `whispy.icns`, fixes the rpath, signs with "Whispy Local Signing" (or ad hoc with a warning), and verifies. Add a `make v2-app` target. Verify that `codesign --verify --strict` passes and that `otool -L` shows no `target/` path.
- [x] 6.3 Check the bundle runs without the build tree. Move `v2/target` aside, launch `dist/Whispy V2.app`, dictate once, and force a whisper reprise with a quiet clip. Confirm Metal works, or record the needed fix: the `disable-library-validation` entitlement or the embedded Metal library. (2026-11-04: ran with `v2/target` moved aside, no dyld error; the whisper.cpp Metal source is embedded in the binary, 294 kernels; a real reprise could not be forced — Parakeet transcribed even `say` at volume 0.02.)
- [x] 6.4 Write `packaging/macos-v2/reinstall.sh` and the `make v2-reinstall` target. It quits V2, `ditto`s into `/Applications/Whispy V2.app`, opens it, waits up to 30 s for `status`, and tails the log on failure. Verify that V1's executable checksum is unchanged and that a deliberately broken launch exits non-zero.
- [x] 6.5 Add `mac/login_item.rs` (`objc2-service-management`, pinned with `=` and justified in a Cargo comment). The menu item "Start at login" carries a check mark, disabled outside a `.app`, with a note when approval is needed. Verify the unit test for the bundle-path rule. By hand, check System Settings → Login Items after toggling.
- [x] 6.6 Document install, permissions (granted to Whispy V2, no longer to the terminal), reinstall and the login item in `v2/README.md`. Verify by following it on this Mac.

## 7. Trial report and procedure

- [x] 7.1 Add `banc/src/trial.rs` and `banc --trial [--since YYYY-MM-DD]`. It parses the journal, reports outcome counts and shares, days with dictation, and nearest-rank p50/p95/max latency over inserted dictations, and lists the clips in `~/.whispy/v2-lost/` for the period. Verify unit tests on fixtures: the 0.1–2.0 s latencies give p95 1.9 s, and a missing journal exits zero.
- [x] 7.2 Parse V1's `~/.whispy.log` and `.log.1`, never `.presparakeet`, into a duration-weighted lost share, and print it beside V2's. Verify the fixture test with 95 s and 5 s against 196 s and 4 s, giving 5.0 % and 2.0 %. Run it on the real log to see that V1's share prints.
- [x] 7.3 Write `v2/TRIAL.md` (design §11): the setup, a minimum of 3 days and 50 dictations, five criteria each tied to a command and a number, the known undercount of partial losses, and where the go/no-go and the missed-features list go (`openspec/changes/v2-parity/`). Verify that every criterion names a number printed by `banc --trial`, `banc --labelled` or the V2 log.
- [x] 7.4 Mention `banc --trial` in `v2/README.md`'s bench section. Verify that the usage line in `banc` matches the README.

## 8. Integration

- [x] 8.1 Run `cargo fmt --check`, `cargo clippy --release --all-targets -- -D warnings` and `cargo test --release` in `v2/`, and the root `./.venv/bin/pytest` to confirm V1 is untouched. All green.
- [x] 8.2 End to end on this Mac: quit V1, run `make v2-reinstall`, grant the permissions, and dictate with Fn and with `start`/`stop` over the socket. Check that a journal line and a log line appear for each, then run `banc --trial`. Record the result in this change. (2026-11-04: via the socket with `say` into TextEdit, text correct, latency 0.5–0.9 s; with Fn by the user, 3 dictations inserted at 0.54–0.73 s; first dictation after launch 0.87 s once System Events is warmed up.)
- [x] 8.3 `openspec validate v2-trial-ready --strict` passes.
