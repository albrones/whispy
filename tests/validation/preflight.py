"""Preflight layer: run `doctor` and explain what it implies for validation.

Runs the existing environment diagnostic, then maps each gap to the downstream
checks it will make UNVERIFIED (so the operator can fix the environment before
blaming the app). A failure in a *hard* prerequisite (the audio backend) stops
the flow — nothing behavioral can run without it.

Tier: unit-mocked — aggregation verified with injected doctor results.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from whispy.doctor import CHECKS, FAIL, WARN

from .outcomes import CheckResult, Outcome

# Doctor check names that, when failing, make downstream seams UNVERIFIED.
# Maps doctor check name -> the downstream features it gates.
_DOWNSTREAM = {
    "Input Monitoring": ["Event tap arms with permission", "Push-to-talk → text in focused app"],
    "Accessibility": ["Clipboard round-trip / injection", "Push-to-talk → text in focused app"],
    "Microphone": ["Driven record→transcribe cycle (HTTP)", "Transcription yields text"],
    "xdotool": ["xdotool injection", "Push-to-talk → text in focused app"],
}

# A failure here means nothing behavioral can run.
_HARD_PREREQUISITES = {"audio backend"}


@dataclass
class Preflight:
    results: list[CheckResult] = field(default_factory=list)
    hard_stop: bool = False
    notes: list[str] = field(default_factory=list)


def run_preflight(checks=None) -> Preflight:
    """Run doctor checks and translate them into a Preflight verdict."""
    checks = checks if checks is not None else CHECKS
    pf = Preflight()

    for check in checks:
        r = check()
        if r.status == FAIL:
            outcome = Outcome.FAIL
            if r.name in _HARD_PREREQUISITES:
                pf.hard_stop = True
                pf.notes.append(f"HARD STOP: {r.name} — {r.detail}")
        elif r.status == WARN:
            outcome = Outcome.UNVERIFIED
        else:
            outcome = Outcome.PASS

        pf.results.append(
            CheckResult(
                feature=f"preflight: {r.name}",
                outcome=outcome,
                detail=r.detail,
                tier="unit-mocked",
                platform=sys.platform,
            )
        )

        if r.status in (FAIL, WARN) and r.name in _DOWNSTREAM:
            downstream = ", ".join(_DOWNSTREAM[r.name])
            pf.notes.append(f"{r.name} {r.status} → will be UNVERIFIED downstream: {downstream}")

    return pf
