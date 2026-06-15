# Homebrew Integration

How Whispy is packaged for, released to, and installed via Homebrew. This is a
maintainer tutorial; end users only need the [Install](#end-user-flow) section.

## Overview

Whispy is distributed through a **personal tap** rather than homebrew-core,
because `faster-whisper` pulls a heavy dependency tree (torch, ctranslate2, …)
that is impractical to vendor as Homebrew `resource` blocks. Instead the formula
creates a Python virtualenv under `libexec` and `pip install`s the package into
it.

Two repos are involved:

| Repo | Role |
| ---- | ---- |
| `albrones/whispy` (this repo) | Holds the **canonical** formula at `packaging/homebrew/whispy.rb` and the release pipeline. |
| `albrones/homebrew-whispy` (the tap) | Holds the **published** formula at `Formula/whispy.rb`. This is what `brew install` reads. |

The canonical formula is the source of truth; the release pipeline copies it
into the tap and patches the `url` + `sha256` for the released tag.

## Tap repo layout

The tap repo is a normal GitHub repo named `homebrew-whispy` (the
`homebrew-` prefix is what lets `brew tap albrones/whispy` find it):

```
homebrew-whispy/
└── Formula/
    └── whispy.rb     # published formula, auto-updated by release.yml
```

You create it once, empty. The first release populates `Formula/whispy.rb`.

## Formula anatomy

`packaging/homebrew/whispy.rb` (the canonical copy):

- **Metadata** — `desc`, `homepage`, `license "GPL-3.0-or-later"`.
- **`url` + `sha256`** — point at the GitHub source tarball for a tag
  (`…/archive/refs/tags/vX.Y.Z.tar.gz`). These two lines are rewritten per
  release by the pipeline; `head` also allows `brew install --HEAD`.
- **`depends_on`** — `python@3.12`, `:macos`, and `sox` (the recorder backend).
- **`install`** — keeps the whole repo tree in `libexec` (the daemon entry point
  `whispy_daemon.py` and `icons/` live at the repo root, not inside the Python
  package), creates `libexec/venv`, `pip install`s the package plus `Pillow`,
  then runs `generate_icons.py` to render the menu-bar icons.
- **`service do`** — registers a `brew services` background service that runs
  `venv/bin/python whispy_daemon.py`, with `keep_alive`, `run_at_load`, log paths
  under `~/.whispy.log` / `~/.whispy-error.log`, and a `PATH` that finds the brew
  binaries.
- **`caveats`** — tells the user to `brew services start whispy` and to grant
  Microphone, Accessibility, and Input Monitoring to the bundled Python binary
  (`opt_libexec/venv/bin/python`), and warns that a `brew upgrade` can change
  that path so permissions may need re-granting.
- **`test do`** — `python -c "import whispy"` inside the venv (`brew test whispy`).

## Release pipeline

`.github/workflows/release.yml` fires **only** on a `v*` tag push (website pushes
carry no tag, so a website edit never triggers a Homebrew build). On a tag it:

1. Checks out the repo.
2. Creates a GitHub release with auto-generated notes
   (`softprops/action-gh-release`). GitHub auto-attaches the source tarball at
   `…/archive/refs/tags/<tag>.tar.gz` — nothing is built by us.
3. Computes the tarball `sha256` (`curl … | shasum -a 256`), retrying a few
   times because the release tarball can lag a few seconds after creation.
4. Clones the tap repo using `HOMEBREW_TAP_TOKEN`, copies the canonical
   `packaging/homebrew/whispy.rb` into `tap/Formula/whispy.rb`, and patches the
   single `url` and `sha256` lines (a `count=1` regex) to match the released
   tag. It then commits `whispy <tag>` and pushes.

Because step 4 starts from the **canonical** formula every time, any formula
edit you make in this repo ships on the next release automatically.

### Required secret

| Secret | Where | What |
| ------ | ----- | ---- |
| `HOMEBREW_TAP_TOKEN` | this repo → Settings → Secrets and variables → Actions | A GitHub token with `contents: write` on `albrones/homebrew-whispy`. A fine-grained PAT scoped to just the tap repo is sufficient. |

The release job's own `permissions: contents: write` covers creating the release
in this repo; the token is only needed to push to the **other** repo.

## Cutting a release

```bash
# from a clean main with the version bumped (pyproject.toml, CHANGELOG.md)
git tag v0.1.1
git push origin v0.1.1
```

That tag push runs `release.yml`, which creates the release and bumps the tap.
Verify with:

```bash
brew update
brew info albrones/whispy/whispy   # should show the new version
```

## Manual formula bump

If you ever need to update the formula by hand (pipeline down, or first-time
bootstrap), compute the sha256 and edit the two lines:

```bash
TAG=v0.1.1
curl -fsSL "https://github.com/albrones/whispy/archive/refs/tags/${TAG}.tar.gz" | shasum -a 256
# put the printed hash in sha256 "…" and update the url "…/tags/v0.1.1.tar.gz"
```

Copy the edited `packaging/homebrew/whispy.rb` to `Formula/whispy.rb` in the tap
repo, commit, and push.

## End-user flow

```bash
# Install
brew install albrones/whispy/whispy   # taps albrones/whispy implicitly

# Start the background service
brew services start whispy

# Grant permissions to the bundled Python binary shown in `brew info` caveats:
#   System Settings → Privacy & Security → Microphone / Accessibility / Input Monitoring
#   binary: $(brew --prefix)/opt/whispy/libexec/venv/bin/python

# Status check (the daemon serves a local control API)
curl http://localhost:9090/status

# Upgrade (may change the binary path → re-grant permissions if dictation stops)
brew upgrade whispy

# Stop / uninstall
brew services stop whispy
brew uninstall whispy
brew untap albrones/whispy
```

The Whisper model downloads automatically on first use.

## Related

- [`docs/deployment.md`](deployment.md) — website (Vercel) pipeline.
- `packaging/homebrew/whispy.rb` — the canonical formula.
- `.github/workflows/release.yml` — the release/tap-bump pipeline.
- `install.sh` — the non-Homebrew bootstrap installer (alternative to brew).
