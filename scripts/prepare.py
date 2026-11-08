"""Prepare pinned sources, Windows wheels and model files, then run the smoke test."""

from __future__ import annotations

import json
import os

# Bounded shell-free tooling; review B404 if commands become external.
import subprocess  # nosec B404
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def run(
    command: list[str],
    timeout: int,
    cwd: Path = ROOT,
    cancelled: threading.Event | None = None,
    *,
    output: BinaryIO | None = None,
) -> None:
    print(f"Running: {' '.join(command)}", flush=True)
    # Commands come only from checked-in preparation, evaluation and verification tooling.
    with subprocess.Popen(  # nosec B603
        command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT if output is not None else None
    ) as process:
        code: int | None
        try:
            if cancelled is None:
                code = process.wait(timeout=timeout)
            else:
                deadline = time.monotonic() + timeout
                while (code := process.poll()) is None:
                    if cancelled.is_set():
                        raise InterruptedError("Cancelled after another verification suite failed")
                    if time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(command, timeout)
                    cancelled.wait(0.1)
        except (subprocess.TimeoutExpired, InterruptedError, KeyboardInterrupt):
            if sys.platform == "win32":
                # Fixed Windows tool and numeric PID; review if command/args become external.
                subprocess.run(  # nosec B603 B607
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    timeout=30,
                )
            else:
                process.kill()
            raise
        if code:
            raise subprocess.CalledProcessError(code, command)


def check_source(source: Path, revision: str, *, apply_patch: bool = False) -> str:
    """Accept only the pinned tracked tree plus the recorded patch."""
    # Fixed git invocations; review exceptions if executable/arguments become external.
    actual_revision = subprocess.check_output(  # nosec B603 B607
        ["git", "rev-parse", "HEAD"], cwd=source, text=True, timeout=30
    )
    if actual_revision.strip() != revision:
        raise RuntimeError("Existing source revision differs; preserve edits and move it aside")
    patch = ROOT / "patches/windows-eager-single-gpu.patch"
    actual = subprocess.check_output(  # nosec B603 B607
        ["git", "diff", "HEAD", "--binary"], cwd=source, timeout=30
    )
    if not actual and apply_patch:
        run(["git", "apply", str(patch)], 60, source)
        actual = subprocess.check_output(  # nosec B603 B607
            ["git", "diff", "HEAD", "--binary"], cwd=source, timeout=30
        )
    if actual.replace(b"\r\n", b"\n") != patch.read_bytes().replace(b"\r\n", b"\n"):
        raise RuntimeError("Existing upstream edits differ from the recorded Windows patch")
    untracked = subprocess.check_output(  # nosec B603 B607
        ["git", "ls-files", "--others", "--exclude-standard", "--", "*.py"],
        cwd=source,
        text=True,
        timeout=30,
    )
    if untracked.strip():
        raise RuntimeError(f"Unexpected untracked Python sources: {untracked.strip()}")
    return revision


def main() -> int:
    RUNTIME.mkdir(exist_ok=True)
    readiness = RUNTIME / "readiness.json"
    readiness.write_text('{"status": "blocked", "stage": "setup"}\n', encoding="utf-8")
    lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
    os.environ["UV_CACHE_DIR"] = str(RUNTIME / "uv-cache")
    os.environ["UV_PYTHON_INSTALL_DIR"] = str(RUNTIME / "python")
    os.environ["HF_HOME"] = str(RUNTIME / "hf-cache")
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    stage = "platform"
    started = time.perf_counter()
    try:
        if sys.platform != "win32":
            raise RuntimeError("This smoke test requires native Windows")
        stage = "source"
        source = RUNTIME / "FlashHead"
        if not (source / ".git").exists():
            run(["git", "clone", lock["upstream_url"], str(source)], 600)
            run(["git", "checkout", "--detach", lock["upstream_revision"]], 60, source)
        check_source(source, lock["upstream_revision"], apply_patch=True)
        stage = "python"
        python = RUNTIME / "venv/Scripts/python.exe"
        if not python.exists():
            run(["uv", "venv", "--python", lock["python"], str(RUNTIME / "venv")], 900)
        # Reject a stale environment rather than silently abandoning the Python pin.
        version = subprocess.check_output(  # nosec B603
            [str(python), "-c", "import platform; print(platform.python_version())"],
            text=True,
            timeout=30,
        )
        if version.strip() != lock["python"]:
            raise RuntimeError("Existing Python differs from the pin; move the environment aside")
        stage = "dependencies"
        run(
            [
                "uv",
                "pip",
                "sync",
                "--python",
                str(python),
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--index-url",
                "https://pypi.org/simple",
                "--extra-index-url",
                "https://download.pytorch.org/whl/cu128",
                "--index-strategy",
                "unsafe-best-match",
                str(ROOT / "requirements-runtime.lock"),
            ],
            3600,
        )
        stage = "model-download"
        download_python = RUNTIME / "download-venv/Scripts/python.exe"
        if not download_python.exists():
            run(["uv", "venv", "--python", str(python), str(RUNTIME / "download-venv")], 300)
        run(
            [
                "uv",
                "pip",
                "sync",
                "--python",
                str(download_python),
                "--require-hashes",
                "--only-binary",
                ":all:",
                str(ROOT / "requirements-download.lock"),
            ],
            600,
        )
        hf = download_python.parent / "hf.exe"
        for model in lock["models"]:
            run(
                [
                    str(hf),
                    "download",
                    model["repository"],
                    *model["files"],
                    "--revision",
                    model["revision"],
                    "--local-dir",
                    str(RUNTIME / "models" / model["directory"]),
                ],
                3600,
            )
        stage = "pipeline-load"
        run([str(python), str(ROOT / "scripts/smoke.py")], 900)
        (RUNTIME / "setup-result.json").write_text(
            json.dumps({"status": "ready", "elapsed_seconds": time.perf_counter() - started})
            + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        evidence = {
            "status": "blocked",
            "stage": stage,
            "error": str(error),
            "elapsed_seconds": time.perf_counter() - started,
        }
        # Keep the more detailed smoke result when the pipeline itself failed.
        (RUNTIME / "setup-result.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
        if json.loads(readiness.read_text(encoding="utf-8"))["stage"] == "setup":
            readiness.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evidence, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
