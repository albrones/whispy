"""Three-state reporting contract for release validation.

Every check resolves to exactly one of PASS / FAIL / UNVERIFIED. UNVERIFIED
means the seam could not be exercised (no device, permission not granted,
binary absent, daemon would not boot) and is NEVER reported as PASS. The run
summary prints counts per state and yields a distinct, non-zero exit code when
anything is UNVERIFIED, so a green result can never mean "nothing ran".

This module is pure (tier: unit-pure): no I/O beyond returning strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Exit codes — distinct so callers (and humans) can tell the three apart.
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNVERIFIED = 2


class Outcome(str, Enum):
    """The only three outcomes a validation check may have."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


_SYMBOL = {Outcome.PASS: "✓", Outcome.FAIL: "✗", Outcome.UNVERIFIED: "?"}


@dataclass
class CheckResult:
    """Outcome of a single validation check, attributed to a feature."""

    feature: str
    outcome: Outcome
    detail: str = ""
    tier: str = ""
    platform: str = ""


@dataclass
class Summary:
    """Aggregate of many check results with per-outcome counts."""

    results: list[CheckResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[Outcome, int]:
        c = {Outcome.PASS: 0, Outcome.FAIL: 0, Outcome.UNVERIFIED: 0}
        for r in self.results:
            c[r.outcome] += 1
        return c

    @property
    def exit_code(self) -> int:
        """FAIL dominates; otherwise any UNVERIFIED is its own non-zero code.

        Ordering matters: a real failure is worse than an unexercised seam, so
        FAIL wins. An all-UNVERIFIED run is distinct from an all-PASS run.
        """
        c = self.counts
        if c[Outcome.FAIL]:
            return EXIT_FAIL
        if c[Outcome.UNVERIFIED]:
            return EXIT_UNVERIFIED
        return EXIT_OK

    def render(self) -> str:
        """Human-readable report: per-result lines + a counts footer."""
        lines = []
        for r in self.results:
            sym = _SYMBOL[r.outcome]
            tag = f" [{r.tier}]" if r.tier else ""
            plat = f" ({r.platform})" if r.platform else ""
            detail = f" — {r.detail}" if r.detail else ""
            lines.append(f"  [{sym}] {r.outcome.value}: {r.feature}{plat}{tag}{detail}")

        c = self.counts
        lines.append("")
        lines.append(f"  {c[Outcome.PASS]} passed, {c[Outcome.FAIL]} failed, {c[Outcome.UNVERIFIED]} UNVERIFIED")
        if c[Outcome.UNVERIFIED]:
            lines.append("  NOTE: UNVERIFIED ≠ pass — those seams could not be exercised here.")
        return "\n".join(lines)


def summarize(results: list[CheckResult]) -> Summary:
    """Build a Summary from a flat list of check results."""
    return Summary(results=list(results))


def classify_pytest_skip(pytest_status: str) -> Outcome:
    """Map a pytest outcome to a validation Outcome.

    A pytest ``skip`` is the silent-pass trap: it absent-mindedly turns a green
    bar into "nothing ran". Under validation a skip is UNVERIFIED, never PASS.
    """
    status = pytest_status.strip().lower()
    if status in ("passed", "pass", "xpassed"):
        return Outcome.PASS
    if status in ("failed", "fail", "error", "errored"):
        return Outcome.FAIL
    # skipped, xfailed, deselected, or anything unknown → not proven.
    return Outcome.UNVERIFIED
