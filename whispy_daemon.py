#!/usr/bin/env python3
"""Whispy — macOS menu bar speech-to-text daemon.

Push-to-talk via Fn key (native CGEventTap).
HTTP API on localhost:9090 for external control.
Menu bar UI via rumps for status, animation, and settings.

This is the main entry point. All logic is in src/whispy/.
"""

import signal
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path.home() / ".whispy.log"),
        logging.StreamHandler(),
    ],
)

# Ensure src/ is on the path
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "src"))

from whispy.core.engine import DictationState, Engine, load_config
from whispy.ui.menu_bar import WhisperMenuBarApp
from whispy.api.server import PORT, start_http_server

# ---------------------------------------------------------------------------
# Config path
# ---------------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".config" / "whispy"
CONFIG_PATH = CONFIG_DIR / "config.json"


def main():
    """Start Whispy: engine, UI, and HTTP server."""
    # Initialize config
    config = load_config(CONFIG_PATH)

    # Create shared state and engine
    state = DictationState()
    state.config = config
    state.app = None  # Set after app creation

    engine = Engine(state, config_path=CONFIG_PATH)

    # Create menu bar app (registers status callback)
    app = WhisperMenuBarApp(engine)
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
    main()
