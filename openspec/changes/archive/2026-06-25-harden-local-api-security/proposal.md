## Why

The daemon's HTTP control API listens on `127.0.0.1:9090` with **no authentication and no Origin/Host validation**. Binding to loopback is not a security boundary against the browser: any web page the user visits can issue `fetch('http://127.0.0.1:9090/start')` (a DNS-rebinding / CSRF surface). An attacker page can therefore silently start the microphone, read `GET /last-transcription` to exfiltrate dictated text (passwords, messages), rewrite the config, and call `POST /transcribe-file` with an arbitrary path (filesystem existence oracle + transcribe-back). There is also no `Content-Length` cap, so an unauthenticated client can force an unbounded allocation (DoS).

Separately, the macOS clipboard/keystroke injection builds an AppleScript string by interpolating the transcribed text into `osascript -e 'set the clipboard to "..."'` while escaping only `"` and not `\`. A backslash or AppleScript metacharacter in the dictated text breaks out of the string literal and is parsed as code — an AppleScript injection path.

This was the API-auth / DNS-rebinding follow-up explicitly deferred by `2026-06-15-code-health-audit-and-fixes`. It is a v1 release blocker.

## What Changes

- **Per-install loopback token**: generate a random secret on first run, persist it (mode `0600`), and require it on every API request (e.g. `Authorization: Bearer <token>` or `X-Whispy-Token`). Requests without the valid token get `401`.
- **Origin / Host pinning (DNS-rebinding defense)**: reject any request whose `Host` header is not exactly `127.0.0.1:<port>` / `localhost:<port>`, and reject any request that carries an `Origin` or `Referer` header (a same-process CLI client sends neither; a browser always does).
- **Request-size cap**: reject requests whose `Content-Length` exceeds a small limit (e.g. 64 KB) before reading the body.
- **`/transcribe-file` path restriction**: only accept paths inside an allow-listed fixtures directory; resolve and prefix-check; reject anything outside.
- **Safe AppleScript injection**: stop interpolating transcribed text into the `-e` script; pass the text via stdin/argv (e.g. `pbcopy` reading stdin, or `osascript - <<'EOF'` with a `run argv` handler) so the text is never parsed as code. Escape backslashes before quotes anywhere interpolation remains.
- Update the in-repo API clients (menu bar, CLI/curl docs, tests) to send the token.

## Capabilities

### Added Capabilities
- `api-interface`: the API SHALL authenticate every request with a per-install token, SHALL reject browser-originated and rebinding requests via Host/Origin checks, and SHALL bound request bodies.
- `text-injection`: text injection on macOS SHALL never let transcribed content be interpreted as AppleScript.

## Impact

- `src/whispy/api/server.py` — token check, Host/Origin/Referer rejection, Content-Length cap, `/transcribe-file` path allow-list.
- `src/whispy/core/paths.py` / config — persist the loopback token (`0600`).
- `src/whispy/hardware/injection.py` — replace string-interpolated `osascript` with stdin/argv; escape backslashes.
- `src/whispy/ui/menu_bar.py` and any HTTP client — attach the token.
- `README.md` — update the documented `curl` examples to include the token header.
- `tests/` — auth-required, Host/Origin-rejection, oversized-body rejection, path-traversal rejection, and AppleScript-escaping regression tests.
