"""Operator layer: the human-only residue, harness-assisted.

Generates an interactive checklist from the ``manual-ui`` rows of
``FEATURE_MATRIX.md`` (the source of truth). For each item the harness pre-arms
what it can (boots the daemon, clears ``/last-transcription``) and auto-detects
the result by polling the API where possible, so the human's only job is the
physical act (hold the trigger, speak) and a y/n confirmation. Results are
written to a timestamped, git-ignored run report.

Tier: manual-ui — needs a human keypress and visual confirmation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from .harness import _http, _wait_status, boot_headless_daemon
from .matrix import Row, manual_ui_rows
from .outcomes import CheckResult, Outcome

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / ".validation-reports"

_PLATFORM_LABEL = {"darwin": "macOS", "linux": "Linux"}


def _row_applies(row: Row, platform: str) -> bool:
    label = _PLATFORM_LABEL.get(platform, platform)
    plats = row.platforms.lower()
    return "both" in plats or label.lower() in plats


def _is_ptt(row: Row) -> bool:
    return "push-to-talk" in row.feature.lower()


def run_operator(
    interactive: bool = True,
    input_fn=input,
    output_fn=print,
    platform: str | None = None,
) -> list[CheckResult]:
    """Walk the operator checklist; return one CheckResult per applicable item."""
    platform = platform or sys.platform
    rows = [r for r in manual_ui_rows() if _row_applies(r, platform)]
    results: list[CheckResult] = []

    if not interactive:
        # Non-interactive (CI / unattended): cannot perform manual checks.
        return [
            CheckResult(
                r.feature,
                Outcome.UNVERIFIED,
                "operator layer skipped (non-interactive)",
                tier="manual-ui",
                platform=platform,
            )
            for r in rows
        ]

    output_fn("\n--- Operator layer (human-in-the-loop) ---")
    output_fn("Type y = works, n = broken, s = skip/can't test.\n")

    for row in rows:
        if _is_ptt(row):
            results.append(_run_ptt_item(row, input_fn, output_fn, platform))
        else:
            results.append(_run_confirm_item(row, input_fn, output_fn, platform))

    _write_report(results, platform)
    return results


def _prompt(input_fn, output_fn, feature: str, instruction: str) -> str:
    output_fn(f"\n• {feature}\n  {instruction}")
    return input_fn("  result [y/n/s]: ").strip().lower()


def _verdict(answer: str, feature: str, platform: str, detail_yes: str = "confirmed by operator") -> CheckResult:
    if answer.startswith("y"):
        return CheckResult(feature, Outcome.PASS, detail_yes, tier="manual-ui", platform=platform)
    if answer.startswith("n"):
        return CheckResult(feature, Outcome.FAIL, "operator reported broken", tier="manual-ui", platform=platform)
    return CheckResult(feature, Outcome.UNVERIFIED, "operator skipped", tier="manual-ui", platform=platform)


def _run_confirm_item(row: Row, input_fn, output_fn, platform: str) -> CheckResult:
    answer = _prompt(input_fn, output_fn, row.feature, f"{row.notes}. Does it work?")
    return _verdict(answer, row.feature, platform)


def _run_ptt_item(row: Row, input_fn, output_fn, platform: str) -> CheckResult:
    """Pre-arm the daemon, let the human dictate, auto-detect the transcription."""
    with boot_headless_daemon() as (proc, base_url):
        if base_url is None:
            return CheckResult(
                row.feature, Outcome.UNVERIFIED, "daemon did not boot", tier="manual-ui", platform=platform
            )
        if _wait_status(base_url, time.monotonic() + 10) is None:
            return CheckResult(
                row.feature, Outcome.UNVERIFIED, "daemon not reachable", tier="manual-ui", platform=platform
            )

        output_fn(f"\n• {row.feature}")
        output_fn(f"  Focus a text field, then: {row.notes}.")
        input_fn("  Press ENTER when you are ready, then perform the dictation...")

        # Poll for a fresh transcription appearing.
        before = _http("GET", f"{base_url}/last-transcription", timeout=5).get("text")
        detected = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(0.5)
            now = _http("GET", f"{base_url}/last-transcription", timeout=5).get("text")
            if now and now != before:
                detected = now
                break

        if detected:
            output_fn(f"  Detected transcription: {detected!r}")
            ans = input_fn("  Did that exact text land in your focused field? [y/n/s]: ").strip().lower()
            return _verdict(ans, row.feature, platform, detail_yes=f"injected: {detected!r}")
        ans = input_fn("  No transcription detected. Did dictation work at all? [y/n/s]: ").strip().lower()
        return _verdict(ans, row.feature, platform, detail_yes="operator confirmed despite no API signal")


def _write_report(results: list[CheckResult], platform: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"operator-{platform}-{stamp}.md"
    lines = [f"# Operator validation run — {platform} — {stamp}", ""]
    for r in results:
        lines.append(f"- [{r.outcome.value}] {r.feature} — {r.detail}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
