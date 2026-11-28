"""scripts/release.py: the version the release workflow publishes on each push to main."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release", REPO_ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(_spec)
sys.modules["release"] = release  # dataclasses resolve annotations through it
_spec.loader.exec_module(release)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "HOME": str(root),
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout shaped like Whispy's, tagged v2.0.0."""
    for rel in ("v2/whispy2", "website"):
        (tmp_path / rel).mkdir(parents=True)
    (tmp_path / "v2/whispy2/Cargo.toml").write_text(
        '[package]\nname = "whispy2"\nversion = "2.0.0"\nedition = "2021"\n'
    )
    (tmp_path / "v2/Cargo.lock").write_text(
        '[[package]]\nname = "whispy-core"\nversion = "0.1.0"\n\n[[package]]\nname = "whispy2"\nversion = "2.0.0"\n'
    )
    (tmp_path / "website/index.html").write_text(
        '<div class="dd-header">Whispy 2.0.0 · voice dictation</div>\n'
        '<div class="dd-item dd-version">Whispy 2.0.0 · up to date</div>\n'
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- Hand-written note.\n\n## [2.0.0] — 2026-10-06\n\nOld.\n"
    )
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feat: whispy 2")
    _git(tmp_path, "tag", "-a", "v2.0.0", "-m", "Whispy 2.0.0")
    return tmp_path


def _commit(root: Path, message: str) -> None:
    _git(root, "commit", "-q", "--allow-empty", "-m", message)


def _run(root: Path, *extra: str, capsys) -> str:
    assert release.main(["--root", str(root), "--date", "2026-11-26", *extra]) == 0
    return capsys.readouterr().out.strip()


def _publish(root: Path, version: str) -> None:
    """What the workflow does after the script: commit and tag."""
    _git(root, "commit", "-q", "--all", "-m", f"chore(release): v{version}")
    _git(root, "tag", "-a", f"v{version}", "-m", f"Whispy {version}")


# Criteria 1 and 4: a fix after the last tag (v2.0.0) publishes the next patch.
def test_a_fix_publishes_the_patch_after_the_last_tag(repo, capsys, tmp_path):
    _commit(repo, "fix(v2): the pill no longer flickers (#60)")
    notes = tmp_path / "notes.md"
    assert _run(repo, "--notes", str(notes), capsys=capsys) == "2.0.1"
    assert release.stamped_versions(repo) == dict.fromkeys(release.stamped_versions(repo), "2.0.1")
    # The menu demo states it twice: its header and its grey version line.
    site = (repo / "website/index.html").read_text()
    assert site.count("Whispy 2.0.1 ·") == 2 and "2.0.0" not in site
    changelog = (repo / "CHANGELOG.md").read_text()
    assert "## [Unreleased]\n\n## [2.0.1] — 2026-11-26\n" in changelog
    assert "### Fixes\n\n- **v2:** the pill no longer flickers (#60)" in changelog
    # The hand-written [Unreleased] notes move under the version, once.
    assert changelog.count("Hand-written note.") == 1
    assert changelog.index("Hand-written note.") > changelog.index("## [2.0.1]")
    assert changelog.index("## [2.0.1]") < changelog.index("## [2.0.0]")
    assert notes.read_text().startswith("### Added\n- Hand-written note.")
    assert "- **v2:** the pill no longer flickers (#60)" in notes.read_text()


# Criterion 2: a feat publishes a minor; chore or docs alone publish nothing.
def test_a_feat_publishes_a_minor_and_chores_alone_publish_nothing(repo, capsys):
    _commit(repo, "fix(v2): a fix")
    _publish(repo, _run(repo, capsys=capsys))
    _commit(repo, "feat(v2): a feature")
    _commit(repo, "fix: another fix")
    version = _run(repo, capsys=capsys)
    assert version == "2.1.0"
    _publish(repo, version)
    _commit(repo, "chore: tidy")
    _commit(repo, "docs(readme): typo")
    before = (repo / "CHANGELOG.md").read_text()
    assert _run(repo, capsys=capsys) == ""
    assert (repo / "CHANGELOG.md").read_text() == before
    assert set(release.stamped_versions(repo).values()) == {"2.1.0"}


def test_a_release_commit_alone_publishes_nothing(repo, capsys):
    _commit(repo, "fix: a fix")
    _publish(repo, _run(repo, capsys=capsys))
    assert _run(repo, "--dry-run", capsys=capsys) == ""


def test_merge_commits_are_read_through(repo, capsys):
    _git(repo, "checkout", "-q", "-b", "topic")
    _commit(repo, "feat(v2): from a branch")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #61 from albrones/topic", "topic")
    assert _run(repo, "--dry-run", capsys=capsys) == "2.1.0"


def test_dry_run_changes_nothing(repo, capsys):
    _commit(repo, "feat: x")
    assert _run(repo, "--dry-run", capsys=capsys) == "2.1.0"
    assert _git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    ("subject", "body", "level"),
    [
        ("fix(v2): x", "", release.PATCH),
        ("feat(install): x", "", release.MINOR),
        ("feat!: x", "", release.MAJOR),
        ("fix(api)!: x", "", release.MAJOR),
        ("fix: x", "BREAKING CHANGE: the API moved", release.MAJOR),
        ("chore: x", "", 0),
        ("docs: x", "", 0),
        ("chore(release): v2.1.0", "", 0),
        ("Merge pull request #1", "", 0),
        ("featuring a thing", "", 0),
    ],
)
def test_bump_level(subject, body, level):
    entry = release.parse(release.Commit(subject, body))
    assert release.bump_level([entry] if entry else []) == level


def test_next_version():
    assert release.next_version((2, 0, 0), release.PATCH) == (2, 0, 1)
    assert release.next_version((2, 0, 1), release.MINOR) == (2, 1, 0)
    assert release.next_version((2, 1, 3), release.MAJOR) == (3, 0, 0)


def test_the_checkout_states_one_version():
    """Every file the release stamps agrees, and the website demo shows it."""
    versions = release.stamped_versions(REPO_ROOT)
    assert all(versions.values()), versions
    assert len(set(versions.values())) == 1, versions
