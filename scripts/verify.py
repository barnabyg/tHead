"""Canonical non-mutating verification for the smoke-test tooling."""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from prepare import ROOT, run

# B404/B603: fixed shell-free verification tools only; review if commands become external.


def main() -> None:
    python = sys.executable
    run([python, "-m", "ruff", "format", "--check", "scripts", "tests"], 120)
    biome = str(ROOT / "node_modules/.bin/biome.cmd")
    browser_files = [
        "scripts/streaming.js",
        "scripts/benchmark.cjs",
        "scripts/resilience.cjs",
        "scripts/streaming.html",
        "scripts/conversation.html",
        "playwright.config.cjs",
        "tests/browser/conversation.spec.cjs",
    ]
    run([biome, "format", *browser_files], 120)
    run([python, "-m", "ruff", "check", "scripts", "tests"], 120)
    run(
        [biome, "lint", "--error-on-warnings", *browser_files],
        120,
    )
    run([python, "-m", "mypy"], 180)
    run(["node", "--check", "scripts/streaming.js"], 120)
    run(["node", "--check", "scripts/benchmark.cjs"], 120)
    run(["node", "--check", "scripts/resilience.cjs"], 120)
    run(["node", "--check", "tests/browser/conversation.spec.cjs"], 120)
    run(["node", "--check", "playwright.config.cjs"], 120)
    run([python, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "scripts", "tests"], 120)
    modules = sorted((ROOT / "tests").glob("test_*.py"))
    # Independent command suites have separate temporary directories and ports.
    # unittest has no parallel worker mode; run its modules concurrently instead.
    failures = []
    cancelled = threading.Event() if os.environ.get("CI") else None
    with ThreadPoolExecutor(max_workers=min(len(modules), os.cpu_count() or 1)) as pool:
        pending = []
        os.environ["THEAD_TEST_PYTHON"] = python
        pending.append(
            pool.submit(
                run,
                [str(ROOT / "node_modules/.bin/playwright.cmd"), "test"],
                600,
                cancelled=cancelled,
            )
        )
        for module in modules:
            tests = [
                python,
                "-W",
                "error",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                module.name,
            ]
            if os.environ.get("CI"):
                tests.append("--failfast")
            pending.append(pool.submit(run, tests, 180, cancelled=cancelled))
        for future in as_completed(pending):
            try:
                future.result()
            except Exception as error:
                failures.append(error)
                if os.environ.get("CI"):
                    assert cancelled is not None  # nosec B101
                    cancelled.set()
                    for other in pending:
                        other.cancel()
                    raise
    if failures:
        raise RuntimeError(f"{len(failures)} test suites failed") from failures[0]
    run(["uv", "lock", "--check"], 180)
    run(["npm.cmd", "ls", "--depth=0"], 180)
    run(["npm.cmd", "audit", "--audit-level=low"], 600)
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
        "speech-lock.json",
        "package.json",
        "package-lock.json",
        "biome.json",
    ]
    secrets = subprocess.check_output(command, cwd=ROOT, text=True, timeout=180)  # nosec B603
    findings = json.loads(secrets)["results"]
    # Public run UUIDs / fixture PCM digests in the named evidence files and voice lock.
    # Do not suppress other fields or detector types; review if its schema changes.
    evidence_paths = {
        (ROOT / name).resolve()
        for name in (
            "docs/runtime/rtx3090-streaming.json",
            "docs/runtime/rtx3090-speech.json",
            "docs/runtime/rtx3090-conversation.json",
            "docs/runtime/rtx3090-phase5-baseline.json",
            "docs/runtime/rtx3090-phase5-recovery.json",
            "speech-lock.json",
        )
    }
    public_metadata = re.compile(
        r'\s*"(?:id|session|request)": "[0-9a-f-]{32,36}",?\s*'
        r'|\s*"(?:sha256|declared_pcm_sha256)": "[0-9a-f]{64}",?\s*'
    )
    for filename in list(findings):
        evidence_path = (ROOT / filename).resolve()
        if evidence_path in evidence_paths:
            evidence_lines = evidence_path.read_text(encoding="utf-8").splitlines()
            findings[filename] = [
                finding
                for finding in findings[filename]
                if not (
                    finding["type"] == "Hex High Entropy String"
                    and public_metadata.fullmatch(evidence_lines[finding["line_number"] - 1])
                )
            ]
            if not findings[filename]:
                del findings[filename]
    if findings:
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
