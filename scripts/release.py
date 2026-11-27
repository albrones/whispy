#!/usr/bin/env python3
"""Compute and stamp Whispy's next version from the conventional commits.

Run by .github/workflows/release.yml after every push to main whose CI is
green. It reads the commits since the last ``vX.Y.Z`` tag reachable from
HEAD and picks the bump:

- ``fix(...)``                                   -> patch (2.0.0 -> 2.0.1)
- ``feat(...)``                                  -> minor (2.0.1 -> 2.1.0)
- ``feat!``/``fix!`` or a ``BREAKING CHANGE:`` footer -> major
- anything else (``chore``, ``docs``, ``test``...) -> no release

When a release is due it writes the new version into every file that carries
it (the V2 crate and its lock entry, the website's menu demo),
moves the CHANGELOG's ``[Unreleased]`` notes under a new version heading with
the list of features and fixes, writes the same notes to ``--notes`` for the
GitHub release, and prints the version. It prints nothing when no release is
due. Committing, tagging and publishing stay in the workflow.

    python3 scripts/release.py --notes notes.md         # stamp, print version
    python3 scripts/release.py --dry-run                # print version only
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SUBJECT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<desc>.+)$")
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)

PATCH, MINOR, MAJOR = 1, 2, 3


@dataclass(frozen=True)
class Commit:
    subject: str
    body: str = ""


@dataclass(frozen=True)
class Entry:
    kind: str  # "feat" or "fix"
    scope: str | None
    text: str
    breaking: bool


def parse(commit: Commit) -> Entry | None:
    """The changelog entry for a feat/fix commit, None for anything else."""
    m = SUBJECT_RE.match(commit.subject.strip())
    if not m:
        return None
    kind = m["type"].lower()
    breaking = bool(m["bang"]) or bool(BREAKING_RE.search(commit.body))
    if kind not in ("feat", "fix"):
        return None
    return Entry(kind=kind, scope=m["scope"] or None, text=m["desc"].strip(), breaking=breaking)


def bump_level(entries: list[Entry]) -> int:
    level = 0
    for e in entries:
        level = max(level, MAJOR if e.breaking else MINOR if e.kind == "feat" else PATCH)
    return level


def next_version(current: tuple[int, int, int], level: int) -> tuple[int, int, int]:
    major, minor, patch = current
    if level == MAJOR:
        return (major + 1, 0, 0)
    if level == MINOR:
        return (major, minor + 1, 0)
    if level == PATCH:
        return (major, minor, patch + 1)
    return current


def fmt(version: tuple[int, int, int]) -> str:
    return ".".join(str(n) for n in version)


def release_notes(entries: list[Entry], unreleased: str = "") -> str:
    """The body shared by the CHANGELOG section and the GitHub release."""

    def line(e: Entry) -> str:
        scope = f"**{e.scope}:** " if e.scope else ""
        return f"- {scope}{e.text}"

    parts = []
    if unreleased.strip():
        parts.append(unreleased.strip())
    for title, kind in (("Features", "feat"), ("Fixes", "fix")):
        lines = [line(e) for e in entries if e.kind == kind]
        if lines:
            parts.append(f"### {title}\n\n" + "\n".join(lines))
    breaking = [line(e) for e in entries if e.breaking]
    if breaking:
        parts.insert(0, "### Breaking changes\n\n" + "\n".join(breaking))
    return "\n\n".join(parts) + "\n"


def update_changelog(text: str, version: str, date: str, entries: list[Entry]) -> tuple[str, str]:
    """Move the ``[Unreleased]`` notes under ``## [version] — date``.

    Returns the new changelog and the release notes. ``[Unreleased]`` stays,
    empty, for the hand-written notes of the next release.
    """
    m = re.search(r"^## \[Unreleased\][^\n]*\n", text, re.MULTILINE)
    if not m:
        raise SystemExit("CHANGELOG.md has no '## [Unreleased]' heading")
    nxt = re.search(r"^## ", text[m.end() :], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(text)
    notes = release_notes(entries, text[m.end() : end])
    section = f"## [{version}] — {date}\n\n{notes}\n"
    return text[: m.end()] + "\n" + section + text[end:], notes


# Every file that states the version, with the pattern whose group 1 is it.
VERSION_SITES: list[tuple[str, re.Pattern[str]]] = [
    ("v2/whispy2/Cargo.toml", re.compile(r'^\[package\]\nname = "whispy2"\nversion = "([^"]+)"', re.MULTILINE)),
    ("v2/Cargo.lock", re.compile(r'^name = "whispy2"\nversion = "([^"]+)"', re.MULTILINE)),
    ("website/index.html", re.compile(r'<div class="dd-header">Whispy (\S+) · voice dictation</div>')),
]


def stamp(root: Path, version: str) -> None:
    for rel, pattern in VERSION_SITES:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        m = pattern.search(text)
        if not m:
            raise SystemExit(f"{rel}: version not found ({pattern.pattern})")
        path.write_text(text[: m.start(1)] + version + text[m.end(1) :], encoding="utf-8")


def stamped_versions(root: Path) -> dict[str, str]:
    """The version each file states (all equal on a healthy checkout)."""
    out = {}
    for rel, pattern in VERSION_SITES:
        m = pattern.search((root / rel).read_text(encoding="utf-8"))
        out[rel] = m.group(1) if m else ""
    return out


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def last_tag(root: Path) -> tuple[str, tuple[int, int, int]]:
    tag = git(root, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*", "HEAD").strip()
    m = TAG_RE.match(tag)
    if not m:
        raise SystemExit(f"last tag {tag!r} is not vX.Y.Z")
    return tag, (int(m[1]), int(m[2]), int(m[3]))


def commits_since(root: Path, tag: str) -> list[Commit]:
    raw = git(root, "log", "--no-merges", "--reverse", "--format=%s%x1f%b%x1e", f"{tag}..HEAD")
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        subject, _, body = record.partition("\x1f")
        commits.append(Commit(subject=subject, body=body))
    return commits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--notes", type=Path, help="write the release notes here")
    ap.add_argument("--dry-run", action="store_true", help="print the next version, change nothing")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)

    tag, current = last_tag(args.root)
    entries = [e for e in (parse(c) for c in commits_since(args.root, tag)) if e]
    level = bump_level(entries)
    if not level:
        print(f"no feat/fix commit since {tag}: nothing to release", file=sys.stderr)
        return 0
    version = fmt(next_version(current, level))
    if not args.dry_run:
        changelog = args.root / "CHANGELOG.md"
        text, notes = update_changelog(changelog.read_text(encoding="utf-8"), version, args.date, entries)
        changelog.write_text(text, encoding="utf-8")
        stamp(args.root, version)
        if args.notes:
            args.notes.write_text(notes, encoding="utf-8")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
