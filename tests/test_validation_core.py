"""unit-pure tests for the release-validation reporting core and matrix linter.

Verifies the three-state contract (PASS/FAIL/UNVERIFIED), that an all-UNVERIFIED
run is distinguishable from an all-PASS run, the skip→UNVERIFIED classification,
and that the matrix linter flags missing 'Verified by' targets and bad tiers.
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent
_src = _root / "src"
for p in (str(_root), str(_src)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests.validation.matrix import lint_matrix, manual_ui_rows, parse_matrix
from tests.validation.outcomes import (
    EXIT_FAIL,
    EXIT_OK,
    EXIT_UNVERIFIED,
    CheckResult,
    Outcome,
    classify_pytest_skip,
    summarize,
)
from tests.validation.preflight import run_preflight


def _r(outcome):
    return CheckResult("feat", outcome, tier="unit-pure")


class TestThreeStateContract:
    def test_all_pass_exits_zero(self):
        s = summarize([_r(Outcome.PASS), _r(Outcome.PASS)])
        assert s.exit_code == EXIT_OK
        assert s.counts[Outcome.PASS] == 2

    def test_any_unverified_is_distinct_nonzero(self):
        s = summarize([_r(Outcome.PASS), _r(Outcome.UNVERIFIED)])
        assert s.exit_code == EXIT_UNVERIFIED
        assert s.exit_code != EXIT_OK

    def test_all_unverified_distinguishable_from_all_pass(self):
        unv = summarize([_r(Outcome.UNVERIFIED), _r(Outcome.UNVERIFIED)])
        passed = summarize([_r(Outcome.PASS), _r(Outcome.PASS)])
        assert unv.exit_code != passed.exit_code
        assert unv.render() != passed.render()

    def test_fail_dominates_unverified(self):
        s = summarize([_r(Outcome.FAIL), _r(Outcome.UNVERIFIED), _r(Outcome.PASS)])
        assert s.exit_code == EXIT_FAIL

    def test_unverified_never_reads_as_pass_in_render(self):
        s = summarize([_r(Outcome.UNVERIFIED)])
        out = s.render()
        assert "UNVERIFIED" in out
        assert "0 passed" in out


class TestSkipClassification:
    def test_passed_maps_to_pass(self):
        assert classify_pytest_skip("passed") is Outcome.PASS

    def test_failed_maps_to_fail(self):
        assert classify_pytest_skip("failed") is Outcome.FAIL
        assert classify_pytest_skip("error") is Outcome.FAIL

    def test_skip_maps_to_unverified_not_pass(self):
        assert classify_pytest_skip("skipped") is Outcome.UNVERIFIED
        assert classify_pytest_skip("xfailed") is Outcome.UNVERIFIED


class TestMatrixLinter:
    def test_repo_matrix_is_clean(self):
        # The shipped FEATURE_MATRIX.md must lint clean.
        assert lint_matrix() == []

    def test_repo_matrix_has_manual_ui_rows(self):
        assert len(manual_ui_rows()) >= 1

    def test_linter_flags_missing_target(self, tmp_path):
        m = tmp_path / "FEATURE_MATRIX.md"
        m.write_text(
            "## Matrix\n\n"
            "| Feature | Platform(s) | Tier | Verified by | Notes |\n"
            "|---|---|---|---|---|\n"
            "| Foo | both | unit-pure | tests/does_not_exist.py | x |\n",
            encoding="utf-8",
        )
        issues = lint_matrix(path=m, repo_root=tmp_path)
        assert any("not found" in i for i in issues)

    def test_linter_flags_bad_tier_and_operator_misuse(self, tmp_path):
        m = tmp_path / "FEATURE_MATRIX.md"
        m.write_text(
            "## Matrix\n\n"
            "| Feature | Platform(s) | Tier | Verified by | Notes |\n"
            "|---|---|---|---|---|\n"
            "| Bad | both | not-a-tier | operator | x |\n",
            encoding="utf-8",
        )
        issues = lint_matrix(path=m, repo_root=tmp_path)
        assert any("unknown tier" in i for i in issues)
        assert any("only valid on manual-ui" in i for i in issues)


class TestPreflightAggregation:
    def _check(self, name, status, detail=""):
        from whispy.doctor import CheckResult as DoctorResult

        return lambda: DoctorResult(name, status, detail)

    def test_warn_becomes_unverified_and_notes_downstream(self):
        from whispy.doctor import OK, WARN

        checks = [
            self._check("audio backend", OK, "ok"),
            self._check("Microphone", WARN, "not yet requested"),
        ]
        pf = run_preflight(checks=checks)
        outcomes = {r.feature: r.outcome for r in pf.results}
        assert outcomes["preflight: audio backend"] is Outcome.PASS
        assert outcomes["preflight: Microphone"] is Outcome.UNVERIFIED
        assert any("Microphone" in n and "UNVERIFIED downstream" in n for n in pf.notes)
        assert pf.hard_stop is False

    def test_hard_prerequisite_failure_stops_flow(self):
        from whispy.doctor import FAIL, OK

        checks = [
            self._check("audio backend", FAIL, "sounddevice missing"),
            self._check("model", OK, "cached"),
        ]
        pf = run_preflight(checks=checks)
        assert pf.hard_stop is True
        assert any("HARD STOP" in n for n in pf.notes)


class TestMatrixParseExtra:
    def test_parse_reads_all_columns(self, tmp_path):
        m = tmp_path / "FEATURE_MATRIX.md"
        m.write_text(
            "## Matrix\n\n"
            "| Feature | Platform(s) | Tier | Verified by | Notes |\n"
            "|---|---|---|---|---|\n"
            "| Foo | macOS | manual-ui | operator | a note |\n",
            encoding="utf-8",
        )
        rows = parse_matrix(m)
        assert len(rows) == 1
        assert rows[0].feature == "Foo"
        assert rows[0].tier == "manual-ui"
        assert rows[0].refs == ["operator"]
