#!/usr/bin/env python3
"""Whispy — macOS menu bar speech-to-text daemon.

Push-to-talk via Fn key (native CGEventTap).
HTTP API on localhost:9090 for external control.
Menu bar UI via rumps for status, animation, and settings.

This is the main entry point. All logic is in src/whispy/.
"""

import logging
import os
import signal
import sys
from pathlib import Path

# Point SSL at certifi's CA bundle. Inside the .app bundle the interpreter has
# no system CA file, so ssl.create_default_context() raises FileNotFoundError
# and any HTTPS (e.g. a HuggingFace model download) crashes. Harmless elsewhere.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))
except Exception:  # pragma: no cover - certifi absent on a minimal host
    pass

# Configure logging. Force UTF-8: inside a .app bundle stdout defaults to ASCII,
# so any log line with non-ASCII (the em-dashes used throughout) raised
# UnicodeEncodeError in the handler and the record was dropped. UTF-8 stdout +
# a UTF-8 file handler keep every message intact.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover - non-standard streams
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path.home() / ".whispy.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# Ensure src/ is on the path
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "src"))

# ---------------------------------------------------------------------------
# Config path
# ---------------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".config" / "whispy"
CONFIG_PATH = CONFIG_DIR / "config.json"


def main():
    """Start Whispy: engine, UI, and HTTP server."""
    # Heavy imports kept inside main() so `--doctor` can run even if the GUI
    # stack (rumps/AppKit) fails to import on a broken setup.
    from whispy.api.server import start_http_server
    from whispy.core.engine import DictationState, Engine, load_config

    # Initialize config
    config = load_config(CONFIG_PATH)

    # Create shared state and engine
    state = DictationState()
    state.config = config
    state.app = None  # Set after app creation

    engine = Engine(state, config_path=CONFIG_PATH)

    # Create the platform tray UI (rumps menu bar on macOS, pystray on Linux);
    # it registers its own engine status callbacks.
    app = engine._adapters.make_tray(engine)
    state.app = app

    # Start all components
    engine.start()

    # Start HTTP server
    http_server = start_http_server(engine)

    # Handle SIGTERM for graceful shutdown
    def _handle_sigterm(*_args):
        engine.stop()
        http_server.shutdown()
        app.quit()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    print("[main] Whispy starting (menu bar mode)")
    app.run()

    # Cleanup
    engine.stop()
    http_server.shutdown()
    print("[main] Daemon stopped.")


if __name__ == "__main__":
    if "--doctor" in sys.argv:
        from whispy.doctor import run_doctor

        sys.exit(run_doctor())
    main()
