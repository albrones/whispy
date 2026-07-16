"""Tests for ax_reader with mocked macOS Accessibility/AppKit calls."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import time

from whispy.hardware.ax_reader import (
    InjectionSnapshot,
    get_frontmost_pid,
    read_focused_field,
)


def test_snapshot_defaults():
    before = time.monotonic()
    snap = InjectionSnapshot(app_pid=123, injected_text="hello world")
    after = time.monotonic()

    assert snap.app_pid == 123
    assert snap.injected_text == "hello world"
    assert before <= snap.timestamp <= after


def test_get_frontmost_pid_success():
    mock_app = MagicMock()
    mock_app.processIdentifier.return_value = 4242
    mock_workspace = MagicMock()
    mock_workspace.frontmostApplication.return_value = mock_app
    mock_appkit = MagicMock()
    mock_appkit.NSWorkspace.sharedWorkspace.return_value = mock_workspace

    with patch.dict(sys.modules, {"AppKit": mock_appkit}):
        assert get_frontmost_pid() == 4242


def test_get_frontmost_pid_import_error():
    with patch.dict(sys.modules, {"AppKit": None}):
        assert get_frontmost_pid() is None


def _mock_application_services(focused_result, value_result):
    """Build a mocked ApplicationServices module for AX call sequencing."""
    mock_module = MagicMock()
    mock_module.AXUIElementCreateSystemWide.return_value = "system-element"

    def _copy_attribute(element, attribute, _placeholder):
        if attribute == "AXFocusedUIElement":
            return focused_result
        if attribute == "AXValue":
            return value_result
        raise AssertionError(f"unexpected attribute {attribute}")

    mock_module.AXUIElementCopyAttributeValue.side_effect = _copy_attribute
    return mock_module


def test_read_focused_field_success():
    mock_module = _mock_application_services(
        focused_result=(0, "focused-element"),
        value_result=(0, "hello world"),
    )

    with patch.dict(sys.modules, {"ApplicationServices": mock_module}):
        assert read_focused_field() == "hello world"


def test_read_focused_field_no_ax_value():
    mock_module = _mock_application_services(
        focused_result=(0, "focused-element"),
        value_result=(-25212, None),
    )

    with patch.dict(sys.modules, {"ApplicationServices": mock_module}):
        assert read_focused_field() is None


def test_read_focused_field_no_focused_element():
    mock_module = _mock_application_services(
        focused_result=(-25212, None),
        value_result=(0, "unused"),
    )

    with patch.dict(sys.modules, {"ApplicationServices": mock_module}):
        assert read_focused_field() is None


def test_read_focused_field_import_error():
    with patch.dict(sys.modules, {"ApplicationServices": None}):
        assert read_focused_field() is None
