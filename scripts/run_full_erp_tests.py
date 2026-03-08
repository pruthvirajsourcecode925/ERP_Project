from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODULE_TESTS: list[tuple[str, list[str]]] = [
    ("Authentication", ["tests/test_auth.py", "tests/test_users.py", "tests/test_roles.py"]),
    ("Sales", ["tests/test_sales.py"]),
    ("Engineering", ["tests/test_engineering.py"]),
    ("Purchase", ["tests/test_purchase.py"]),
    ("Stores", ["tests/test_stores.py"]),
    ("Production", ["tests/test_production.py", "tests/test_production_reports.py"]),
    ("Quality", ["tests/test_traceability_flow.py"]),
    ("Maintenance", ["tests/test_maintenance.py"]),
    (
        "Dispatch",
        [
            "tests/test_dispatch.py",
            "tests/test_dispatch_business_rules.py",
            "tests/test_dispatch_pdf.py",
            "tests/test_dispatch_roles.py",
        ],
    ),
]


def run_module_tests(module_name: str, test_targets: list[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pytest", *test_targets]
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def main() -> int:
    for module_name, test_targets in MODULE_TESTS:
        result = run_module_tests(module_name, test_targets)
        if result.returncode != 0:
            print(f"[FAIL] {module_name}")
            if result.stdout.strip():
                print(result.stdout.strip())
            if result.stderr.strip():
                print(result.stderr.strip())
            return result.returncode

        print(f"[PASS] {module_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())