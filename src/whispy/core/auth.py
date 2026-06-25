"""Per-install loopback API token.

The HTTP control API binds to loopback, but loopback is not a security boundary
against the browser: any web page can ``fetch('http://127.0.0.1:9090/…')`` and
DNS-rebinding lets a hostile origin pose as ``127.0.0.1``. A shared secret the
browser cannot read distinguishes a same-machine native client (menu bar app,
``curl``, the validation harness) from JavaScript executing in the user's
browser.

The token lives next to the config file (``config.json`` -> ``config.token``)
with ``0600`` permissions, so it is unique per config (the validation harness
drives a throwaway ``WHISPY_CONFIG`` and gets its own token, never colliding
with the real one) and readable only by the user.
"""

import logging
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard ``Authorization: Bearer <token>`` scheme.
AUTH_HEADER = "Authorization"
AUTH_SCHEME = "Bearer"


def token_path(config_path: Path) -> Path:
    """Return the token file path derived from the config file path.

    ``~/.config/whispy/config.json`` -> ``~/.config/whispy/config.token``. Using
    the config's stem keeps the token unique per config so a throwaway config
    (NamedTemporaryFile) gets its own token rather than sharing a directory-wide
    one.
    """
    return config_path.with_suffix(".token")


def load_or_create_token(config_path: Path) -> str:
    """Return the per-install token, generating and persisting it if absent.

    Called by the daemon at boot. Writes the file with ``0600`` so only the
    owning user can read the secret.
    """
    path = token_path(config_path)
    existing = read_token(config_path)
    if existing:
        return existing

    token = secrets.token_urlsafe(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create with 0600 from the start (no world-readable window).
        path.write_text(token, encoding="utf-8")
        path.chmod(0o600)
    except OSError as exc:  # pragma: no cover - defensive (read-only home, etc.)
        logger.warning("[auth] could not persist API token at %s: %s", path, exc)
    return token


def read_token(config_path: Path) -> str | None:
    """Return the existing token for a config, or ``None`` if not yet created.

    Used by native clients (doctor, validation harness) to authenticate to a
    running daemon.
    """
    path = token_path(config_path)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return token or None
