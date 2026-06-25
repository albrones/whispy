## Context

The API is a localhost HTTP control plane for a desktop daemon, intended only for same-machine, same-user clients (the menu bar app and the maintainer's `curl`). The threat is not a remote network attacker but the user's own browser: JavaScript on any visited page can reach loopback, and DNS-rebinding lets a hostile domain pose as `127.0.0.1`. The defense has to distinguish "a local CLI/native client" from "a browser executing someone else's JS". A shared secret the browser cannot read, plus Host/Origin pinning, achieves that without a full auth system.

## Goals / Non-Goals

**Goals:**
- No unauthenticated caller can start the mic, read transcripts, change config, or read arbitrary files.
- A browser page (even via DNS rebinding) is rejected before any side effect.
- Transcribed text can never be executed as AppleScript.

**Non-Goals:**
- TLS / certificates (loopback only).
- Multi-user / remote access.
- Rate limiting beyond the body-size cap.

## Decisions

### Token model
Generate 32 bytes from `secrets.token_urlsafe` on first daemon start; store at a fixed path with `0600`. The daemon loads it at boot; native clients read the same file (same user, same machine) and send it. A browser cannot read the file, so it cannot forge the header. Token check runs first in the request handler; missing/wrong → `401` with no body.

### Host / Origin pinning
Even with a token, defense-in-depth against rebinding: reject if `Host` ∉ {`127.0.0.1:<port>`, `localhost:<port>`}, and reject if `Origin` or `Referer` is present at all (native clients omit them; browsers always attach them on cross-origin `fetch`). This blocks the attack even before the token check matters.

### Body cap
Parse `Content-Length`; if absent on a body-bearing method or `> 64 KB`, return `413` without reading. Prevents `rfile.read(attacker_length)` memory blowup.

### `/transcribe-file` allow-list
Resolve the requested path (`Path(...).resolve()`) and require it to be under the committed fixtures dir (also resolved). Reject otherwise with `403`. Removes the arbitrary-read / existence-oracle.

### AppleScript injection
Root cause: `text.replace('"', '\\"')` escapes quotes only. Fix by not building code from data: pipe the text to `pbcopy` via stdin for clipboard, and for keystroke mode pass text through argv to an `osascript` `on run argv` handler. No user text reaches the `-e` parser. Linux path already uses `xdotool ... --` (argv, safe) — unchanged.

## Risks / Trade-offs

- Existing `curl` muscle-memory breaks (now needs the token header) — documented in README and caveats.
- The menu bar app and tests must learn the token; covered in Impact.
- Token file readable by the same user's other processes — acceptable; the boundary is the browser, not other local user processes (which already have full user privileges).

## Migration Plan

First run after upgrade generates the token; the bundled menu bar reads it automatically. Users with scripts hitting the API must add the header (README shows how to print the token). No config schema migration.

## Open Questions

- Header name: `Authorization: Bearer` (standard) vs `X-Whispy-Token` (simpler). Leaning `Authorization: Bearer`.
- Whether to drop `/last-transcription` entirely rather than gate it — gating is sufficient given the token, but not retaining transcript text server-side is stronger. Decide during implementation.
