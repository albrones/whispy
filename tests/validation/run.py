"""Release-validation orchestrator — the engine behind `make validate`.

Runs three honest layers for the host OS:

  1. preflight  — `doctor`: permissions, model, mic, xdotool, daemon state
  2. live-drive — boot the real daemon, drive a record→transcribe cycle over HTTP
  3. operator   — guided human-in-the-loop checklist (skipped when non-interactive)

Prints one structured summary and exits with the three-state contract:
0 = all pass, 1 = a real failure, 2 = something UNVERIFIED (never silent-green).
"""

from __future__ import annotations

import argparse
import sys

from .matrix import lint_matrix
from .operator import run_operator
from .outcomes import Summary, summarize
from .preflight import run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whispy-validate", description="Whispy release validation")
    parser.add_argument("--no-live", action="store_true", help="skip the live-drive layer")
    parser.add_argument("--no-operator", action="store_true", help="skip the operator (human) layer")
    parser.add_argument("--record-seconds", type=float, default=1.0, help="live-drive recording length")
    args = parser.parse_args(argv)

    all_results = []

    # 0. Matrix lint — surface coverage gaps (rows whose 'Verified by' is missing).
    issues = lint_matrix()
    print("=== Feature matrix lint ===")
    if issues:
        for i in issues:
            print(f"  ! {i}")
        print("  (gaps above: features lacking a resolvable verification target)")
    else:
        print("  ✓ matrix clean — every row has a resolvable verification target")

    # 1. Preflight.
    print("\n=== Preflight (doctor) ===")
    pf = run_preflight()
    all_results.extend(pf.results)
    print(Summary(pf.results).render())
    for note in pf.notes:
        print(f"  · {note}")
    if pf.hard_stop:
        print("\nHard prerequisite failed — skipping behavioral layers.")
        return _finish(all_results)

    # 2. Live-drive (imported lazily so preflight-only runs need no daemon deps).
    if not args.no_live:
        print("\n=== Live-drive (real daemon over HTTP) ===")
        from .harness import run_live_drive

        live = run_live_drive(record_seconds=args.record_seconds)
        all_results.extend(live)
        print(Summary(live).render())

    # 3. Operator (human-in-the-loop) — only when attached to a TTY.
    interactive = sys.stdin.isatty() and not args.no_operator
    if not args.no_operator:
        op = run_operator(interactive=interactive)
        all_results.extend(op)
        if not interactive:
            print("\n=== Operator layer ===")
            print(Summary(op).render())

    return _finish(all_results)


def _finish(results: list) -> int:
    summary = summarize(results)
    print("\n=== Validation summary ===")
    print(summary.render())
    code = summary.exit_code
    verdict = {0: "PASS", 1: "FAIL", 2: "UNVERIFIED (not a pass)"}[code]
    print(f"\nResult: {verdict}  (exit {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
