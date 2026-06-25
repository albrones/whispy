"""Tests for the per-install API token (whispy.core.auth)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import os
import stat

from whispy.core.auth import load_or_create_token, read_token, token_path


def test_token_path_derives_from_config_stem(tmp_path):
    cfg = tmp_path / "config.json"
    assert token_path(cfg) == tmp_path / "config.token"


def test_read_token_none_when_absent(tmp_path):
    assert read_token(tmp_path / "config.json") is None


def test_load_or_create_generates_and_persists(tmp_path):
    cfg = tmp_path / "config.json"
    token = load_or_create_token(cfg)
    assert token
    # Persisted and readable back.
    assert read_token(cfg) == token


def test_load_or_create_is_idempotent(tmp_path):
    cfg = tmp_path / "config.json"
    first = load_or_create_token(cfg)
    second = load_or_create_token(cfg)
    assert first == second  # does not rotate on every boot


def test_token_file_is_owner_only(tmp_path):
    cfg = tmp_path / "config.json"
    load_or_create_token(cfg)
    mode = stat.S_IMODE(os.stat(token_path(cfg)).st_mode)
    assert mode == 0o600


def test_throwaway_config_gets_its_own_token(tmp_path):
    # The validation harness drives a separate WHISPY_CONFIG; its token must not
    # collide with the real one.
    a = load_or_create_token(tmp_path / "real.json")
    b = load_or_create_token(tmp_path / "throwaway.json")
    assert a != b
