"""Canonical non-mutating verification for the smoke-test tooling."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

from prepare import ROOT, run

# B404/B603: fixed shell-free verification tools only; review if commands become external.


def main() -> None:
    python = sys.executable
    run([python, "-m", "ruff", "format", "--check", "scripts", "tests"], 120)
    run([python, "-m", "ruff", "check", "scripts", "tests"], 120)
    run([python, "-m", "mypy"], 180)
    run([python, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "scripts", "tests"], 120)
    tests = [python, "-W", "error", "-m", "unittest", "discover", "-s", "tests"]
    if os.environ.get("CI"):
        tests.append("--failfast")
    run(tests, 180)
    run(["uv", "lock", "--check"], 180)
    run([python, "-m", "pip_audit", "--progress-spinner", "off"], 600)
    # PyPI advisories identify the base PyTorch release, not its official CUDA local suffix.
    requirements = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
    requirements = requirements.replace("+cu128", "")
    # Version-scoped exceptions: see docs/runtime/security-exceptions.md.
    # Updating either package requires reviewing and removing/updating its exception.
    for pin in ("torch==2.11.0 \\", "setuptools==81.0.0 \\"):
        if pin not in requirements:
            raise RuntimeError(f"Review runtime security exceptions after changing {pin}")
    with tempfile.TemporaryDirectory() as temporary:
        audit_input = Path(temporary) / "runtime.txt"
        audit_input.write_text(requirements, encoding="utf-8")
        run(
            [
                python,
                "-m",
                "pip_audit",
                "--disable-pip",
                "--require-hashes",
                "--progress-spinner",
                "off",
                "--ignore-vuln",
                "PYSEC-2025-194",
                "--ignore-vuln",
                "PYSEC-2026-3447",
                "--ignore-vuln",
                "GHSA-xmj3-9gf7-h52w",
                "-r",
                str(audit_input),
            ],
            600,
        )
    run(
        [
            python,
            "-m",
            "pip_audit",
            "--disable-pip",
            "--require-hashes",
            "--progress-spinner",
            "off",
            "-r",
            "requirements-download.lock",
        ],
        600,
    )
    # Scan the delivered files, including newly added files before their first commit.
    command = [
        python,
        "-m",
        "detect_secrets",
        "scan",
        "--all-files",
        # Only the named source/model commit fields: public revision hashes, not secrets.
        "--exclude-lines",
        r'"(?:upstream_revision|revision)": "[0-9a-f]{40}"',
        "scripts",
        "tests",
        "docs/runtime",
        ".github",
        "pyproject.toml",
        "runtime-lock.json",
    ]
    secrets = subprocess.check_output(command, cwd=ROOT, text=True, timeout=180)  # nosec B603
    if json.loads(secrets)["results"]:
        raise RuntimeError(f"Potential secrets found: {secrets}")
    # This repository delivers scripts, not a distributable Python package.
    for directory in ("scripts", "tests"):
        for path in (ROOT / directory).glob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
    run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            "$errors = $null; $tokens = $null; foreach ($script in "
            "(Get-ChildItem scripts/*.ps1)) { "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            "$script.FullName, [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors) { $errors | Write-Error; exit 1 } }",
        ],
        120,
    )
    print("Verification passed")


if __name__ == "__main__":
    main()
