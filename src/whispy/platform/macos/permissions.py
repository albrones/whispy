"""macOS TCC permission requests (microphone + input monitoring).

Neither permission prompts on its own for a bundled menu-bar app:
- Opening the mic via ``sounddevice``/PortAudio (CoreAudio HAL) does NOT provoke
  the microphone prompt — the app just receives silent buffers. We ask
  AVFoundation explicitly.
- Creating the Fn ``CGEventTap`` just fails (returns NULL) without Input
  Monitoring, and a background (LSUIElement) app gets no automatic prompt. We
  ask via IOKit's ``IOHIDRequestAccess`` (a C function, called through ctypes).

Both register the app with TCC and surface the system prompt. Call once at
startup (macOS only).
"""

import ctypes
import logging

logger = logging.getLogger(__name__)

# IOKit IOHIDRequestType / IOHIDAccessType constants.
_kIOHIDRequestTypeListenEvent = 1
_kIOHIDAccessTypeGranted = 0
_kIOHIDAccessTypeDenied = 1


def ensure_microphone_access() -> None:
    """Request microphone access via AVFoundation, surfacing the TCC prompt.

    Best-effort and non-blocking: logs and returns on any failure so a missing
    binding or headless host never prevents the daemon from starting. The
    completion handler runs once the user answers (after the run loop starts).
    """
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    except Exception as exc:  # pragma: no cover - depends on host pyobjc stack
        logger.warning("Cannot request microphone access (AVFoundation unavailable): %s", exc)
        return

    # 3 = authorized, 0 = not determined, 1/2 = restricted/denied.
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
    if status == 3:
        logger.info("Microphone access already granted.")
        return
    if status in (1, 2):
        logger.warning(
            "Microphone access denied — enable Whispy under System Settings -> Privacy & Security -> Microphone."
        )
        return

    # Not determined: trigger the system prompt. The handler fires asynchronously
    # once the user answers; we don't block startup waiting for it.
    def _handler(granted: bool) -> None:  # pragma: no cover - GUI callback
        logger.info("Microphone access %s.", "granted" if granted else "denied")

    AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, _handler)
    logger.info("Requested microphone access (awaiting user response).")


def ensure_input_monitoring_access() -> None:
    """Request Input Monitoring via IOKit, surfacing the TCC prompt.

    The Fn push-to-talk CGEventTap needs Input Monitoring; without it
    ``CGEventTapCreate`` returns NULL and a background app never gets prompted.
    ``IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)`` triggers the prompt the
    same way AVFoundation does for the mic. Best-effort and non-blocking.
    """
    try:
        iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        iokit.IOHIDCheckAccess.restype = ctypes.c_int
        iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        iokit.IOHIDRequestAccess.restype = ctypes.c_bool
        iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]
    except Exception as exc:  # pragma: no cover - non-macOS / missing framework
        logger.warning("Cannot request Input Monitoring access (IOKit unavailable): %s", exc)
        return

    status = iokit.IOHIDCheckAccess(_kIOHIDRequestTypeListenEvent)
    logger.info("Input Monitoring check status=%s (0=granted,1=denied,2=unknown).", status)
    if status == _kIOHIDAccessTypeGranted:
        logger.info("Input Monitoring already granted.")
        return

    # Not granted: request access. On not-determined this shows the system
    # prompt; on a prior denial it returns False without prompting (the user
    # must enable Whispy manually under Privacy & Security -> Input Monitoring).
    granted = iokit.IOHIDRequestAccess(_kIOHIDRequestTypeListenEvent)
    logger.info("Requested Input Monitoring access (granted=%s).", bool(granted))


def ensure_accessibility_access() -> None:
    """Check Accessibility and, if missing, show the system prompt.

    Posting synthetic keystrokes (CGEvent) requires Accessibility. We log the
    current trust state (diagnostic) and, when untrusted, call
    ``AXIsProcessTrustedWithOptions`` with the prompt option so macOS surfaces
    the "allow Whispy to control your computer" dialog. Best-effort.
    """
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
    except Exception as exc:  # pragma: no cover - depends on host pyobjc stack
        logger.warning("Cannot check Accessibility (ApplicationServices unavailable): %s", exc)
        return

    if AXIsProcessTrusted():
        logger.info("Accessibility already granted.")
        return

    # Not trusted: prompt. Returns the (still-false) current state; the user
    # grants in System Settings, then must restart Whispy for it to take effect.
    AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    logger.warning(
        "Accessibility not granted — prompted. Enable Whispy under System Settings -> "
        "Privacy & Security -> Accessibility, then restart Whispy."
    )


# osascript / Apple-event error returned when System Events is not allowed to
# post synthetic keystrokes (errAEEventNotPermitted). Locale-independent.
_KEYSTROKE_NOT_PERMITTED_CODE = "1002"


def ensure_automation_access() -> None:
    """Verify Whispy can actually post keystrokes via System Events.

    Text injection runs ``osascript`` telling System Events to type. Because
    System Events is Apple-signed it can post keystrokes even though Whispy is
    self-signed (a direct CGEventPost from Whispy is dropped) — but it needs
    Whispy's Automation + Accessibility grants, else osascript fails with error
    1002 ("not authorized to send keystrokes").

    A benign query (``return name``) only exercises the Automation grant and
    succeeds even when keystrokes are blocked, so it must NOT be reported as
    authorized. We instead probe the real keystroke path with an empty keystroke
    (``keystroke ""``) — side-effect-free (types nothing) but still gated by the
    same permissions, so a denial surfaces as 1002. The probe also provokes the
    consent prompt on first run. Best-effort; inject-time detection remains the
    authoritative signal.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke ""'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - spawn failure
        logger.warning("Keystroke authorization probe failed to run: %s", exc)
        return
    if proc.returncode == 0:
        logger.info("Keystroke injection (System Events) authorized.")
        return
    detail = (proc.stderr or "").strip()
    if _KEYSTROKE_NOT_PERMITTED_CODE in detail:
        logger.warning(
            "Keystroke injection not authorized (error %s): %s — grant "
            "Accessibility + Automation to Whispy under System Settings -> "
            "Privacy & Security, or run 'tccutil reset Accessibility com.whispy "
            "&& tccutil reset AppleEvents com.whispy', then restart Whispy.",
            _KEYSTROKE_NOT_PERMITTED_CODE,
            detail,
        )
    else:
        # Non-1002 failure: can't confirm the keystroke path. Don't claim
        # authorized; defer to inject-time detection.
        logger.warning(
            "Keystroke authorization unverified: %s — relying on inject-time detection.",
            detail,
        )
