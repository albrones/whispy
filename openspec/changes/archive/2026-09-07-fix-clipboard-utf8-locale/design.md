## Context

See proposal.md for the repro. Facts measured on this machine (macOS 25.5):

- `pbcopy` with no locale in env decodes stdin as Mac Roman (`ça` → `√ßa`).
- `pbpaste` with no locale in env encodes its output as Mac Roman (`à` → `0x88`).
- `LC_ALL=en_US.UTF-8` fixes both, and overrides a stray `LANG=C`. `LANG` alone
  also works, `LC_CTYPE=UTF-8` also works.
- `osascript` with an argv argument passes UTF-8 through untouched. The
  keystroke path does not need the fix; giving it the env is harmless.
- `_spawn` calls `subprocess.Popen(cmd, ...)` and `_snapshot_clipboard` calls
  `subprocess.run(["pbpaste"], ...)`, both without `env`, so the child inherits
  whatever launchd gave the app: nothing.

## Goals / Non-Goals

**Goals:**
- Byte-exact UTF-8 through `pbcopy`/`pbpaste` on every path in the macOS injector.
- Snapshot and restore encode identically, so fixing copy cannot corrupt restore.

**Non-Goals:**
- Linux (`xclip`/`xsel`/`xdotool`): not measured, may have its own story.
- Changing how text reaches the helpers (stdin/argv contract is unchanged).

## Decisions

### D1 — One environment, applied to every subprocess in the injector

A module-level dict, `{**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}`,
passed as `env=` to the `Popen` in `_spawn` and the `run` in `_snapshot_clipboard`.

- Why `LC_ALL` and not just `LANG`: `LC_ALL` wins over any `LANG`/`LC_CTYPE`
  the environment might already carry (a loose-script launch from a shell with
  `LANG=C`). `LANG` is set too so tools that read only `LANG` agree.
- Why every subprocess and not only `pbcopy`: snapshot (`pbpaste`) and restore
  (`pbcopy`) must share an encoding or the restore corrupts the user's previous
  clipboard. Applying it uniformly, `osascript` included, removes a class of
  "which step has it" bugs for the cost of nothing.
- Alternative rejected: decode `pbpaste` output / re-encode for `pbcopy` in
  Python. Guessing the child's encoding is exactly the bug; forcing it is
  smaller and deterministic.
- Alternative rejected: `en_US.UTF-8` vs `C.UTF-8`. macOS ships `en_US.UTF-8`;
  `C.UTF-8` is not guaranteed on older macOS.

### D2 — Test at the seam, verify at the real seam once

`test_injection.py` already mocks `Popen` and inspects call args; add
assertions that every `Popen`/`run` call carries `env` with
`LC_ALL == "en_US.UTF-8"`. A real `pbcopy` round-trip test would clobber the
developer's clipboard, so the real-seam check is a manual task on the built
app, which is also the only place the empty launchd environment actually occurs.

## Risks / Trade-offs

- [`en_US.UTF-8` locale absent] → macOS has shipped it for every supported
  version; `pbcopy` falls back to Mac Roman only, never crashes, so the failure
  mode is the status quo, not a regression.
- [A user relies on Mac Roman clipboard content] → no such user: the current
  output is unreadable garbage, not a format anyone consumes.
