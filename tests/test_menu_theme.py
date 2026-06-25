"""Tests for menu_theme — the macOS menu-bar accent styling helpers.

The pure logic (appearance → colour selection, attributed-title construction,
plain-string fallback) is exercised without AppKit so these run on any platform.
AppKit is faked or forced absent via monkeypatching ``menu_theme._appkit``.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.ui import menu_theme


class _RecordingNSColor:
    """Captures the RGBA passed to colorWithSRGBRed_green_blue_alpha_."""

    last_rgb = None

    @classmethod
    def colorWithSRGBRed_green_blue_alpha_(cls, r, g, b, a):
        cls.last_rgb = (round(r * 255), round(g * 255), round(b * 255))
        return ("nscolor", r, g, b, a)


class _FakeAppKit:
    NSColor = _RecordingNSColor
    NSMutableAttributedString = object  # presence is all supported() checks


def _force_no_appkit(monkeypatch):
    monkeypatch.setattr(menu_theme, "_appkit", lambda: None)


def _force_fake_appkit(monkeypatch, *, dark):
    monkeypatch.setattr(menu_theme, "_appkit", lambda: _FakeAppKit)
    monkeypatch.setattr(menu_theme, "is_dark_appearance", lambda: dark)


class TestAccentColorPerAppearance:
    def test_dark_uses_bright_green(self, monkeypatch):
        _force_fake_appkit(monkeypatch, dark=True)
        menu_theme.accent_color()
        assert _RecordingNSColor.last_rgb == menu_theme.GREEN_BRIGHT

    def test_light_uses_dim_green(self, monkeypatch):
        _force_fake_appkit(monkeypatch, dark=False)
        menu_theme.accent_color()
        assert _RecordingNSColor.last_rgb == menu_theme.GREEN_DIM

    def test_no_appkit_returns_none(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        assert menu_theme.accent_color() is None


class TestBuildersPlainFallback:
    """With AppKit absent the builders must return plain strings, never raise."""

    def test_status_title_prefixes_dot(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        out = menu_theme.status_title("Ready")
        assert isinstance(out, str)
        assert out.startswith(menu_theme.DOT)
        assert "Ready" in out

    def test_section_title_uppercase(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        out = menu_theme.section_title("Settings")
        assert out == "SETTINGS"

    def test_check_title_checked_has_tick(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        out = menu_theme.check_title("French", True)
        assert isinstance(out, str)
        assert out.startswith(menu_theme.CHECK)
        assert out.endswith("French")

    def test_check_title_unchecked_has_no_tick(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        out = menu_theme.check_title("French", False)
        assert menu_theme.CHECK not in out
        assert out.endswith("French")

    def test_supported_false_without_appkit(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        assert menu_theme.supported() is False


class TestApplyTitle:
    def test_plain_string_sets_title(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        item = SimpleNamespace(title="old", _menuitem=None)
        menu_theme.apply_title(item, "NEW")
        assert item.title == "NEW"

    def test_is_dark_defaults_true_without_appkit(self, monkeypatch):
        _force_no_appkit(monkeypatch)
        assert menu_theme.is_dark_appearance() is True
