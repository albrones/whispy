"""macOS "start at login" via SMAppService (ServiceManagement framework).

``SMAppService.mainAppService`` registers the *currently running app bundle* as
a login item (macOS 13+). We reach ``SMAppService`` through ``objc.loadBundle``
on the already-installed ``pyobjc-core`` rather than adding the dedicated
``pyobjc-framework-ServiceManagement`` package — no new dependency.

Only meaningful when running from a ``.app`` bundle: under a loose-script run
``mainAppService`` has no bundle identity (that path autostarts via its
LaunchAgent instead). State is owned by the OS — read it live, never persist it.
"""

import logging

logger = logging.getLogger(__name__)

# SMAppServiceStatus enum: 0=NotRegistered, 1=Enabled, 2=RequiresApproval,
# 3=NotFound. We treat only Enabled as "on".
_SM_STATUS_ENABLED = 1

# Resolve SMAppService once. None if the framework can't load (macOS < 13, or a
# host without the bridge) — callers gate on available().
_SMAppService = None
try:
    import objc

    _ns = {}
    objc.loadBundle(
        "ServiceManagement",
        _ns,
        bundle_path="/System/Library/Frameworks/ServiceManagement.framework",
    )
    _SMAppService = _ns.get("SMAppService")
except Exception as exc:  # pragma: no cover - depends on host OS/pyobjc stack
    logger.debug("ServiceManagement unavailable: %s", exc)


def available() -> bool:
    """Whether the start-at-login control can be used (SMAppService present)."""
    return _SMAppService is not None


def _main_service():
    return _SMAppService.mainAppService()


def is_enabled() -> bool:
    """Return True when the running bundle is registered and enabled as a login item."""
    if not available():
        return False
    try:
        return _main_service().status() == _SM_STATUS_ENABLED
    except Exception as exc:  # pragma: no cover - bridge call
        logger.warning("Could not read login-item status: %s", exc)
        return False


def _unwrap(result):
    """Normalize a register/unregister result to ``(ok, error)``.

    Loaded via ``objc.loadBundle`` without BridgeSupport metadata, the NSError**
    out-param is not recognized, so pyobjc returns just the BOOL. With metadata
    present it returns an ``(ok, error)`` tuple. Handle both.
    """
    if isinstance(result, tuple):
        return bool(result[0]), result[1]
    return bool(result), None


def enable() -> bool:
    """Register the running bundle as a login item. Return success."""
    if not available():
        return False
    try:
        ok, err = _unwrap(_main_service().registerAndReturnError_(None))
        if not ok:
            logger.warning("Login-item register failed: %s", err)
        return ok
    except Exception as exc:  # pragma: no cover - bridge call
        logger.warning("Login-item register raised: %s", exc)
        return False


def disable() -> bool:
    """Unregister the running bundle as a login item. Return success."""
    if not available():
        return False
    try:
        ok, err = _unwrap(_main_service().unregisterAndReturnError_(None))
        if not ok:
            logger.warning("Login-item unregister failed: %s", err)
        return ok
    except Exception as exc:  # pragma: no cover - bridge call
        logger.warning("Login-item unregister raised: %s", exc)
        return False
