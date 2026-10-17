## 1. App crate (`v2/whispy2`)

- [x] 1.1 State machine (`machine.rs`): hold, tap-to-toggle, watchdog, Fn as modifier, V1 yield; unit tests
- [x] 1.2 Controller and worker threads, ports `Capture` and `Inserter`; tests with a scripted engine
- [x] 1.3 Resampling device audio to 16 kHz mono; tone tests
- [x] 1.4 V1 detection (port 9090, bundle process); tests
- [x] 1.5 macOS adapters: Fn tap with re-arm and missed-release replay, microphone, paste inserter, menu bar
- [x] 1.6 Quit stops the threads and frees the models before exit

## 2. Proof

- [x] 2.1 End-to-end latency test with a WAV microphone and a recording inserter, real models: p95 0.37 s
- [x] 2.2 Launch with V1 running: menu reads « Whispy V1 is running — Fn is left to it »; Quit exits cleanly

Left `[à l'usage]`, outside these tasks: a real Fn hold and tap and a real paste into an app, with V1 quit (needs the user's keyboard).

## 3. Delivery

- [x] 3.1 `v2/README.md`: launch, permissions, Globe key setting, cohabitation, latency
- [x] 3.2 `cargo fmt --check`, `cargo test --release --locked`, `cargo clippy --release --locked --all-targets -- -D warnings`
