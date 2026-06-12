#!/usr/bin/env python3
"""Run pytest with a per-file timeout using signal.alarm."""

import os
import subprocess

project_root = "/Users/alexisbrones/Documents/Perso/whispy"

# List test files
test_files = [
    "tests/test_core.py",
    "tests/test_audio.py",
    "tests/test_integration.py",
    "tests/test_e2e.py",
    "tests/test_event_tap.py",
    "tests/test_event_tap_e2e.py",
    "tests/test_api.py",
    "tests/test_config_validation.py",
    "tests/test_simplify_config_ui.py",
    "tests/test_stress.py",
]

for tf in test_files:
    full_path = os.path.join(project_root, tf)
    if not os.path.exists(full_path):
        continue

    print(f"\n{'=' * 60}")
    print(f"RUNNING: {tf}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(
            [".venv/bin/pytest", "-v", "--tb=short", full_path],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
        output = result.stdout
        # Show last part (results)
        lines = output.split("\n")
        # Find summary
        for i, line in enumerate(lines):
            if "passed" in line or "failed" in line or "error" in line or "PASSED" in line or "FAILED" in line:
                # Print from 10 lines before to 10 lines after
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                for line_out in lines[start:end]:
                    print(line_out)
                print(f"... [output truncated, exit code: {result.returncode}]")
                break
    except subprocess.TimeoutExpired:
        print("*** TIMEOUT after 30s — HANG DETECTED ***")
