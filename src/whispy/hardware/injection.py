"""Text injection via macOS accessibility APIs (osascript).

Handles injecting transcribed text into the active application
using clipboard paste or direct keystroke simulation. Injection goes through
``osascript`` -> "System Events": System Events is Apple-signed, so it can post
synthetic keystrokes even though Whispy is self-signed (a direct CGEventPost
from Whispy is silently dropped). It needs Whispy's Accessibility + Automation
(Apple-events) grants; failures are logged with the osascript error.

When the synthetic keystroke is denied (osascript error ``1002`` /
errAEEventNotPermitted) the clipboard is still set but nothing is typed — a
silent failure. We detect that code (locale-independent: the number appears
whatever the system language) and surface it via a debounced callback so the
UI can prompt the user to fix the grant instead of failing quietly.
"""

import logging
import subprocess
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# osascript / Apple-event error returned when System Events is not allowed to
# post synthetic keystrokes (errAEEventNotPermitted). Match on this numeric code
# rather than the localized message, which varies by system language.
KEYSTROKE_NOT_PERMITTED_CODE = "1002"

# Delay before restoring the clipboard after a paste, so the target app has
# time to read the pasted transcript before we overwrite it again.
_CLIPBOARD_RESTORE_DELAY = 0.15


class TextInjector:
    """Injects text into the focused application via osascript."""

    def __init__(
        self,
        copy_to_clipboard: bool = True,
        on_permission_denied: Callable[[str], None] | None = None,
    ) -> None:
        self._copy_to_clipboard = copy_to_clipboard
        self._on_permission_denied = on_permission_denied
        # Debounce: True once a keystroke denial has been surfaced, reset on the
        # next successful injection. Keeps us to one notification per
        # permission-state transition instead of one per utterance.
        self._keystroke_denied = False

    def update_config(self, copy_to_clipboard: bool) -> None:
        """Update the clipboard copy setting."""
        self._copy_to_clipboard = copy_to_clipboard

    def set_permission_denied_callback(self, callback: Callable[[str], None] | None) -> None:
        """Register a callback fired (debounced) when a keystroke is denied.

        The callback receives a human-readable remediation message and is called
        off the injection worker thread.
        """
        self._on_permission_denied = callback

    def inject(self, text: str) -> None:
        """Inject transcribed text into the active application."""
        if not text:
            return

        if self._copy_to_clipboard:
            self._inject_via_clipboard(text)
        else:
            self._inject_via_keystrokes(text)

    def copy_only(self, text: str) -> None:
        """Place text on the clipboard without pasting it anywhere.

        Used when the engine must hand a transcript back to the user but has no
        business typing it -- the recording-limit stop, where the field that was
        focused when dictation started may no longer be focused after minutes of
        speech. Unlike ``_inject_via_clipboard`` this deliberately does NOT
        snapshot and restore the previous clipboard: the whole point is that the
        transcript survives on the pasteboard for the user to paste themselves.
        """
        if not text:
            return
        self._spawn([(["pbcopy"], text.encode("utf-8"))], "copy-only")

    def _spawn(
        self,
        steps: list[tuple[list[str], bytes | None] | tuple[list[str], bytes | None, float]],
        mode: str,
    ) -> None:
        """Run a sequence of subprocess steps off-thread, classifying the result.

        Each step is ``(cmd, stdin_bytes)`` or ``(cmd, stdin_bytes, delay)``;
        ``stdin_bytes`` is fed to the process stdin (this is how transcribed
        text reaches ``pbcopy``/``osascript`` — as data, never interpolated
        into a script). The optional ``delay`` (seconds) is slept before that
        step runs, e.g. to give a pasted-into app time to read the clipboard
        before a later step restores it. Steps run sequentially in one worker
        thread, stopping at the first failure. The failing (or final) step's
        exit is classified: a ``1002`` failure is a keystroke-permission
        denial that fires the debounced callback; a clean run resets the
        debounce so a later denial is surfaced again.
        """

        def _run() -> None:
            rc = 0
            detail = ""
            for step in steps:
                cmd, stdin_data, *rest = step
                delay = rest[0] if rest else 0
                if delay:
                    time.sleep(delay)
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE if stdin_data is not None else None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                try:
                    _, err = proc.communicate(input=stdin_data, timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    logger.warning("[inject] (%s) step %s timed out", mode, cmd[0])
                    return
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("[inject] (%s) step %s error: %s", mode, cmd[0], exc)
                    return
                rc = proc.returncode
                detail = err.decode("utf-8", "replace").strip() if isinstance(err, bytes | bytearray) else str(err)
                if rc:
                    break  # stop the sequence on the first failing step

            if rc:
                logger.warning("[inject] (%s) rc=%s: %s", mode, rc, detail)
                if KEYSTROKE_NOT_PERMITTED_CODE in detail:
                    self._handle_keystroke_denied()
            else:
                logger.info("[inject] (%s) ok", mode)
                self._keystroke_denied = False

        threading.Thread(target=_run, daemon=True).start()

    def _handle_keystroke_denied(self) -> None:
        """Surface a keystroke-permission denial, debounced to one per transition."""
        if self._keystroke_denied:
            return
        self._keystroke_denied = True
        logger.warning(
            "[inject] keystroke denied (error %s): Whispy lacks permission to type. "
            "Grant Accessibility + Automation to Whispy, or run "
            "'tccutil reset Accessibility com.whispy && tccutil reset AppleEvents com.whispy', "
            "then restart Whispy.",
            KEYSTROKE_NOT_PERMITTED_CODE,
        )
        if self._on_permission_denied is None:
            return
        message = (
            "Whispy can't type into apps — the text was copied to the clipboard "
            "instead. Grant Accessibility + Automation to Whispy in System "
            "Settings (or run 'tccutil reset Accessibility com.whispy && tccutil "
            "reset AppleEvents com.whispy'), then restart Whispy."
        )
        try:
            self._on_permission_denied(message)
        except Exception:  # pragma: no cover - defensive
            logger.exception("[inject] permission-denied callback failed")

    def _snapshot_clipboard(self) -> bytes:
        """Best-effort capture of the current clipboard text via ``pbpaste``.

        Called synchronously, before the clipboard is overwritten, so the
        prior content can be restored after paste. ``inject()`` is only ever
        called from a worker thread (transcription / chunk assembly), never
        from the event-tap thread, so a short blocking call here is safe. Any
        failure (missing binary, non-zero exit, timeout) is logged and
        treated as an empty snapshot — injection proceeds either way.
        """
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
        except Exception as exc:
            logger.warning("[inject] clipboard snapshot failed: %s", exc)
            return b""
        if result.returncode != 0:
            logger.warning("[inject] clipboard snapshot rc=%s", result.returncode)
            return b""
        return result.stdout

    def _inject_via_clipboard(self, text: str) -> None:
        """Copy text to clipboard (via ``pbcopy`` stdin), paste via Cmd+V, then
        restore the clipboard to what it held before injection.

        The text is written to ``pbcopy``'s stdin, never interpolated into an
        AppleScript string, so it cannot be parsed or executed as code. The
        paste step is a constant AppleScript with no user data. The clipboard
        is snapshotted before it's overwritten and restored afterwards so the
        (possibly sensitive) transcript doesn't linger on the pasteboard and
        the user's previous clipboard isn't destroyed. If the paste step
        itself fails (e.g. keystroke permission denied), ``_spawn`` stops the
        sequence before the restore step runs, deliberately leaving the
        transcript on the clipboard as the documented manual-paste fallback.
        """
        snapshot = self._snapshot_clipboard()
        self._spawn(
            [
                (["pbcopy"], text.encode("utf-8")),
                (
                    ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
                    None,
                ),
                # ponytail: pbpaste/pbcopy round-trip plain text only — if the
                # clipboard held rich text, an image, or a file reference
                # before dictation, that content is not restored, only its
                # plain-text form (or nothing, if it had none).
                (["pbcopy"], snapshot, _CLIPBOARD_RESTORE_DELAY),
            ],
            "clipboard",
        )

    def _inject_via_keystrokes(self, text: str) -> None:
        """Type the text via System Events, passing it as an argv argument.

        The script is read from stdin and the text is handed to it via ``argv``
        (``on run argv``), so the transcribed text is data, never part of the
        script source — no escaping, no injection.
        """
        script = b'on run argv\ntell application "System Events" to keystroke (item 1 of argv)\nend run\n'
        self._spawn(
            [(["osascript", "-", text], script)],
            "keystrokes",
        )
