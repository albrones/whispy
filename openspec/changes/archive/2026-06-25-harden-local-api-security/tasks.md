## 1. Loopback token

- [x] 1.1 Generate a per-install token (`secrets.token_urlsafe(32)`) on first daemon start; persist at a fixed path with `0600`
- [x] 1.2 Load the token at daemon boot; expose a helper for native clients to read it

## 2. Request authentication + rebinding defense (server.py)

- [x] 2.1 Reject requests missing/with wrong token → `401` (check first)
- [x] 2.2 Reject requests whose `Host` is not `127.0.0.1:<port>` / `localhost:<port>` → `403`
- [x] 2.3 Reject requests carrying any `Origin` or `Referer` header → `403`
- [x] 2.4 Cap `Content-Length` (reject `> 64 KB` or absent-on-body) → `413` before reading the body

## 3. /transcribe-file path allow-list (server.py)

- [x] 3.1 Resolve the requested path and require it under the committed fixtures dir; else `403`

## 4. Safe AppleScript injection (injection.py)

- [x] 4.1 Replace clipboard `osascript -e` interpolation with `pbcopy` reading text from stdin
- [x] 4.2 Replace keystroke-mode interpolation with an `osascript` `on run argv` handler (text via argv)
- [x] 4.3 Escape backslashes before quotes anywhere string interpolation remains

## 5. Client + docs updates

- [x] 5.1 Make the menu bar / any in-repo HTTP client send the token header
- [x] 5.2 Update README `curl` examples to include the token header and show how to print the token

## 6. Tests

- [x] 6.1 Request without token → `401`; with token → success
- [x] 6.2 Request with a foreign `Host` and with an `Origin` header → `403`
- [x] 6.3 Oversized `Content-Length` → `413` without reading body
- [x] 6.4 `/transcribe-file` with a path outside the fixtures dir → `403`
- [x] 6.5 Injection of text containing `"` , `\`, and AppleScript metacharacters is delivered verbatim and executes no code

## 7. Verification

- [x] 7.1 Run the full test suite; confirm no regression
- [x] 7.2 `ruff check` / `ruff format --check` on changed files
- [x] 7.3 `openspec validate harden-local-api-security --strict`
