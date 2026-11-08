"""Opt-in persistent reference-conditioned speech process; no application storage changes."""

from __future__ import annotations

import base64
import json
import queue
import shutil
import subprocess  # nosec B404
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, TextIO

from chatterbox_eval import sha256
from prepare import ROOT

# B404/B603/B607: fixed checked-in worker and task-owned PID cleanup only.
# Review if executable/script/commands become externally supplied.


def reference_record(identity: str) -> dict[str, Any]:
    lock = json.loads((ROOT / "chatterbox-lock.json").read_text(encoding="utf-8"))
    for record in lock["references"]:
        if record["id"] == identity:
            return dict(record)
    raise ValueError("Unknown experimental reference ID")


def reference_file(state: Path, identity: str) -> Path:
    record = reference_record(identity)
    path = state / "references" / f"{identity}.wav"
    if not path.is_file() or sha256(path) != record["sha256"]:
        raise ValueError(f"Reference {identity} missing or changed; rerun chatterbox-app.ps1")
    return path


def prepare_references(state: Path) -> None:
    lock = json.loads((ROOT / "chatterbox-lock.json").read_text(encoding="utf-8"))
    (state / "references").mkdir(parents=True, exist_ok=True)
    for record in lock["references"]:
        source = ROOT / record["file"]
        if sha256(source) != record["sha256"]:
            raise ValueError(f"Bundled reference {record['id']} changed; restore this checkout")
        path = state / "references" / f"{record['id']}.wav"
        if not path.exists():
            shutil.copyfile(source, path)
        reference_file(state, record["id"])


class ChatterboxVoice:
    def __init__(
        self, state: Path, identity: str, fixture: bool = False, configuration: str = "cpu"
    ) -> None:
        self.state, self.identity, self.fixture = state, identity, fixture
        if configuration not in ("cpu", "cuda"):
            raise ValueError("Unknown experimental configuration")
        self.configuration = configuration
        self.metadata: dict[str, Any] = {"reference_id": identity, "worker_alive": False}
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.log: TextIO | None = None
        self.lines: queue.Queue[dict[str, Any]] = queue.Queue(2)
        self.fault = ""

    def read(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None  # nosec B101
        try:
            while line := process.stdout.readline(2_000_001):
                if len(line) > 2_000_000:
                    value = {"error": "Experimental worker response exceeded its bound"}
                else:
                    try:
                        value = json.loads(line)
                    except (ValueError, TypeError):
                        value = {"error": "Experimental worker returned invalid JSON"}
                self.lines.put(value, timeout=1)
        except queue.Full:
            return

    def reply(self, cancelled: threading.Event) -> dict[str, Any]:
        deadline = time.monotonic() + 600
        while not cancelled.is_set():
            try:
                value = self.lines.get(timeout=0.05)
                if value.get("error"):
                    raise RuntimeError(str(value["error"]))
                return value
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    raise RuntimeError(
                        "Experimental speech worker exited; retry or switch voices"
                    ) from None
                if time.monotonic() > deadline:
                    raise TimeoutError("Experimental speech exceeded ten minutes") from None
        raise InterruptedError("Experimental speech stopped")

    def prepare(self, cancelled: threading.Event) -> None:
        if self.process is not None:
            return
        reference_file(self.state, self.identity)
        if not self.fixture:
            lock = json.loads((ROOT / "chatterbox-lock.json").read_text(encoding="utf-8"))
            for asset in lock["model"]["files"]:
                path = self.state / "model" / asset["name"]
                if not path.is_file() or sha256(path) != asset["sha256"]:
                    raise ValueError(
                        "Pinned Nano model missing or changed; rerun chatterbox-app.ps1"
                    )
        python = Path(sys.executable) if self.fixture else self.state / "venv/Scripts/python.exe"
        if not python.is_file():
            raise ValueError("Experimental environment missing; rerun chatterbox-app.ps1")
        logs = self.state / "worker-logs"
        logs.mkdir(parents=True, exist_ok=True)
        self.log = (logs / f"{self.identity}-{uuid.uuid4().hex}.log").open("w", encoding="utf-8")
        self.lines = queue.Queue(2)
        self.process = subprocess.Popen(  # nosec B603
            [
                str(python),
                "-I",
                str(ROOT / "scripts/chatterbox_worker.py"),
                "--state",
                str(self.state),
                "--reference-id",
                self.identity,
                "--configuration",
                self.configuration,
                *(["--fixture"] if self.fixture else []),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            encoding="utf-8",
        )
        self.reader = threading.Thread(target=self.read, args=(self.process,), daemon=True)
        self.reader.start()
        try:
            self.metadata.update(self.reply(cancelled))
            if not self.metadata.get("ready") or self.metadata.get("reference_id") != self.identity:
                raise RuntimeError("Experimental worker prepared the wrong reference")
            self.metadata["worker_alive"] = True
        except Exception:
            self.close()
            raise

    def exchange(self, operation: str, cancelled: threading.Event, text: str = "") -> bytes:
        try:
            self.prepare(cancelled)
            assert self.process is not None and self.process.stdin is not None  # nosec B101
            message = {"operation": operation, "text": text}
            if operation == "speak":
                message["fault"], self.fault = self.fault, ""
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
            value = self.reply(cancelled)
            if "metrics" in value:
                self.metadata["last_synthesis"] = value["metrics"]
            pcm = base64.b64decode(value.get("pcm", ""), validate=True)
            if len(pcm) % 2 or len(pcm) > 31 * 32000:
                raise ValueError("Experimental worker returned excessive/invalid PCM16")
            return pcm
        except Exception:
            self.close()
            raise

    def begin_turn(self, cancelled: threading.Event) -> None:
        self.exchange("begin", cancelled)

    def speak(self, text: str, cancelled: threading.Event) -> bytes:
        return self.exchange("speak", cancelled, text)

    def finish_turn(self, cancelled: threading.Event) -> bytes:
        return self.exchange("finish", cancelled)

    def close(self) -> None:
        process, self.process = self.process, None
        self.metadata["worker_alive"] = False
        if process:
            if process.stdin:
                process.stdin.close()
            if process.poll() is None:
                if sys.platform == "win32":
                    subprocess.run(  # nosec B603 B607
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                        check=False,
                    )
                else:
                    process.kill()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process = process
                self.metadata["worker_alive"] = True
                raise
            if self.reader:
                self.reader.join(timeout=5)
                if self.reader.is_alive():
                    raise TimeoutError("Experimental response reader did not release")
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if self.log:
            self.log.close()
            self.log = None
