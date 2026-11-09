"""Canonical non-mutating verification for the smoke-test tooling."""

from __future__ import annotations

import hashlib
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
        "scripts/voices.js",
        "scripts/benchmark.cjs",
        "scripts/resilience.cjs",
        "scripts/pair-assessment.cjs",
        "scripts/chatterbox-benchmark.cjs",
        "scripts/voice-release.cjs",
        "scripts/streaming.html",
        "scripts/conversation.html",
        "playwright.config.cjs",
        "tests/browser/conversation.spec.cjs",
        "tests/browser/chatterbox.spec.cjs",
    ]
    run([biome, "format", *browser_files], 120)
    run([python, "-m", "ruff", "check", "scripts", "tests"], 120)
    run(
        [biome, "lint", "--error-on-warnings", *browser_files],
        120,
    )
    run([python, "-m", "mypy"], 180)
    run(["node", "--check", "scripts/streaming.js"], 120)
    run(["node", "--check", "scripts/voices.js"], 120)
    run(["node", "--check", "scripts/benchmark.cjs"], 120)
    run(["node", "--check", "scripts/resilience.cjs"], 120)
    run(["node", "--check", "scripts/pair-assessment.cjs"], 120)
    run(["node", "--check", "scripts/chatterbox-benchmark.cjs"], 120)
    run(["node", "--check", "scripts/voice-release.cjs"], 120)
    run(["node", "--check", "tests/browser/conversation.spec.cjs"], 120)
    run(["node", "--check", "tests/browser/chatterbox.spec.cjs"], 120)
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
    # Audit the maintained candidate independently, with no advisory exclusions.
    # PyPI uses the base Torch release; acquisition retains the official CUDA URL/hash.
    maintained_lock = json.loads((ROOT / "chatterbox-maintained-lock.json").read_text())
    source_patch = maintained_lock["source_patch"]
    if (
        hashlib.sha256((ROOT / source_patch["file"]).read_bytes()).hexdigest()
        != source_patch["sha256"]
    ):
        raise RuntimeError("Maintained source patch differs from its hash pin")
    candidate = (ROOT / "docs/runtime/chatterbox/requirements-maintained.lock").read_text()
    torch_line = re.compile(r"^torch @ https://download-r2\.pytorch\.org/whl/cu130/[^\n]+", re.M)
    candidate, replacements = torch_line.subn(
        lambda _match: "torch==" + maintained_lock["torch"].split("+")[0] + " \\", candidate
    )
    if replacements != 1:
        raise RuntimeError("Review maintained CUDA advisory normalization after changing its pin")
    with tempfile.TemporaryDirectory() as temporary:
        candidate_input = Path(temporary) / "maintained.txt"
        candidate_input.write_text(candidate, encoding="utf-8")
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
                str(candidate_input),
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
        "hazel-lock.json",
        "chatterbox-lock.json",
        "chatterbox-gpu-lock.json",
        "chatterbox-maintained-lock.json",
        "voice-media-lock.json",
        "avatar-pairs.json",
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
            "hazel-lock.json",
            "avatar-pairs.json",
            "docs/runtime/rtx3090-phase6-fixture.json",
            "docs/runtime/rtx3090-phase6-real.json",
            "docs/runtime/rtx3090-phase6-stop.json",
            "docs/runtime/phase6-clean-startup.json",
            "chatterbox-lock.json",
            "chatterbox-gpu-lock.json",
            "chatterbox-maintained-lock.json",
            "voice-media-lock.json",
            "docs/runtime/chatterbox/maintenance-candidate-inventory.json",
            "docs/runtime/chatterbox/maintenance-python-security.json",
            "docs/runtime/chatterbox/native-release.json",
            "scripts/chatterbox_release.py",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-1.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-2.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-3.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-121-attempt-1.json",
            "docs/runtime/chatterbox/setup-result.json",
            "docs/runtime/chatterbox/clean-result.json",
            "docs/runtime/chatterbox/quality-manifest.json",
            "docs/runtime/chatterbox/alignment-verification.json",
            "docs/runtime/chatterbox/wheel-inventory.json",
            "docs/runtime/chatterbox/integration/media-validation.json",
            "docs/runtime/chatterbox/integration/baseline.json",
            "docs/runtime/chatterbox/integration/cpu-1089.json",
            "docs/runtime/chatterbox/integration/cpu-1089-r2.json",
            "docs/runtime/chatterbox/integration/cpu-121.json",
            "docs/runtime/chatterbox/integration/cpu-assets.json",
            "docs/runtime/chatterbox/integration/cpu-restart.json",
            "docs/runtime/chatterbox/integration/cuda-1089.json",
            "docs/runtime/chatterbox/integration/cuda-1089-r2.json",
            "docs/runtime/chatterbox/integration/environment.json",
            "docs/runtime/chatterbox/integration/cuda-121.json",
        )
    }
    public_metadata = re.compile(
        r'\s*"(?:id|session|request|run)": "[0-9a-f-]{32,36}",?\s*'
        r'|\s*"(?:sha256|declared_pcm_sha256)": "[0-9a-f]{64}",?\s*'
    )
    # Only the new explicit evidence captures' Git source pin; review on schema changes.
    source_pin = re.compile(r'\s*"source": "[0-9a-f]{40}",?\s*')
    # Public artifact hashes/source pins only in the named Chatterbox evidence schemas.
    # Review these exact fields if the schemas or artifact sources change.
    chatterbox_evidence = {
        (ROOT / name).resolve()
        for name in (
            "chatterbox-lock.json",
            "chatterbox-gpu-lock.json",
            "chatterbox-maintained-lock.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-1.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-2.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-1089-attempt-3.json",
            "docs/runtime/chatterbox/maintenance-attempts/preview-121-attempt-1.json",
            "docs/runtime/chatterbox/setup-result.json",
            "docs/runtime/chatterbox/clean-result.json",
            "docs/runtime/chatterbox/quality-manifest.json",
            "docs/runtime/chatterbox/alignment-verification.json",
            "docs/runtime/chatterbox/wheel-inventory.json",
            "docs/runtime/chatterbox/integration/media-validation.json",
            "docs/runtime/chatterbox/integration/baseline.json",
            "docs/runtime/chatterbox/integration/cpu-1089.json",
            "docs/runtime/chatterbox/integration/cpu-1089-r2.json",
            "docs/runtime/chatterbox/integration/cpu-121.json",
            "docs/runtime/chatterbox/integration/cpu-assets.json",
            "docs/runtime/chatterbox/integration/cpu-restart.json",
            "docs/runtime/chatterbox/integration/cuda-1089.json",
            "docs/runtime/chatterbox/integration/cuda-1089-r2.json",
            "docs/runtime/chatterbox/integration/environment.json",
            "docs/runtime/chatterbox/integration/cuda-121.json",
        )
    }
    chatterbox_pin = re.compile(
        r'\s*"(?:perth_revision|source_revision|model_revision)": "[0-9a-f]{40}",?\s*'
        r'|\s*"(?:sha256|reference_sha256|output_sha256|asset_sha256)": "[0-9a-f]{64}",?\s*'
    )
    # Only the three public current artifact approvals in the release policy module.
    # A pin change needs renewed native/security evidence and updated approval values.
    approval_hashes = {
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "chatterbox-maintained-lock.json",
            "docs/runtime/chatterbox/requirements-maintained.lock",
            "patches/chatterbox-maintained.patch",
        )
    }
    for filename in list(findings):
        evidence_path = (ROOT / filename).resolve()
        if evidence_path in evidence_paths:
            evidence_lines = evidence_path.read_text(encoding="utf-8").splitlines()
            findings[filename] = [
                finding
                for finding in findings[filename]
                if not (
                    finding["type"] == "Hex High Entropy String"
                    and (
                        public_metadata.fullmatch(evidence_lines[finding["line_number"] - 1])
                        or (
                            evidence_path == (ROOT / "scripts/chatterbox_release.py").resolve()
                            and any(
                                re.fullmatch(
                                    r'\s*"' + digest + r'",?\s*',
                                    evidence_lines[finding["line_number"] - 1],
                                )
                                for digest in approval_hashes
                            )
                        )
                        or (
                            evidence_path == ROOT / "voice-media-lock.json"
                            and re.fullmatch(
                                r'\s*"(?:ffmpeg|ffprobe)\.exe": "[0-9a-f]{64}",?\s*',
                                evidence_lines[finding["line_number"] - 1],
                            )
                        )
                        or (
                            evidence_path in chatterbox_evidence
                            and chatterbox_pin.fullmatch(evidence_lines[finding["line_number"] - 1])
                        )
                        or (
                            evidence_path.name
                            in (
                                "rtx3090-phase5-baseline.json",
                                "rtx3090-phase5-recovery.json",
                                "rtx3090-phase6-fixture.json",
                                "rtx3090-phase6-real.json",
                                "rtx3090-phase6-stop.json",
                                "phase6-clean-startup.json",
                            )
                            and source_pin.fullmatch(evidence_lines[finding["line_number"] - 1])
                        )
                    )
                )
            ]
            if not findings[filename]:
                del findings[filename]
    if findings:
        raise RuntimeError(f"Potential secrets found: {json.dumps(findings)}")
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
