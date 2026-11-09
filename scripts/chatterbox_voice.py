"""Bounded reference-conditioned worker lifecycle, shared across avatars and previews."""

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
    validate_reference(path, record["sha256"])
    return path


def validate_reference(path: Path, digest: str) -> None:
    if not path.is_file() or sha256(path) != digest:
        raise ValueError(
            "Reference missing or changed; restore or explicitly repair the saved voice"
        )


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
        self,
        state: Path,
        identity: str,
        fixture: bool = False,
        configuration: str = "cpu",
        *,
        reference_path: Path | None = None,
        reference_sha256: str | None = None,
    ) -> None:
        self.state, self.identity, self.fixture = state, identity, fixture
        if configuration not in ("cpu", "cuda", "maintained"):
            raise ValueError("Unknown experimental configuration")
        self.configuration = configuration
        self.reference_path, self.reference_sha256 = self.reference(
            identity, reference_path, reference_sha256
        )
        self.metadata: dict[str, Any] = {
            "reference_id": identity,
            "worker_alive": False,
            "lifecycle_state": "unprepared",
        }
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.log: TextIO | None = None
        self.lines: queue.Queue[dict[str, Any]] = queue.Queue(2)
        self.operation_lock = threading.RLock()
        self.pending: dict[str, str] | None = None
        self.watchdog: threading.Timer | None = None
        self.abandoned_request = ""
        self.epoch = ""
        self.turn = ""
        self.turn_cancelled: threading.Event | None = None
        self.fault = ""

    def reference(self, identity: str, path: Path | None, digest: str | None) -> tuple[Path, str]:
        if path is None and digest is None:
            record = reference_record(identity)
            return self.state / "references" / f"{identity}.wav", str(record["sha256"])
        if (
            path is None
            or digest is None
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Managed reference requires a canonical path and SHA-256")
        return path.resolve(), digest

    def read(self, process: subprocess.Popen[str], lines: queue.Queue[dict[str, Any]]) -> None:
        assert process.stdout is not None  # nosec B101
        try:
            while line := process.stdout.readline(2_000_001):
                if len(line) > 2_000_000:
                    value = {"error": "Experimental worker response exceeded its bound"}
                else:
                    try:
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("Expected an object")
                    except (ValueError, TypeError):
                        value = {"error": "Experimental worker returned invalid JSON"}
                pending = self.pending
                if pending and all(value.get(key) == item for key, item in pending.items()):
                    if self.watchdog:
                        self.watchdog.cancel()
                    if value.get("request_id") == self.abandoned_request:
                        self.metadata["lifecycle_state"] = "ready"
                lines.put(value, timeout=1)
        except queue.Full:
            return

    def reply(
        self, cancelled: threading.Event, expected: dict[str, str] | None = None
    ) -> dict[str, Any]:
        deadline = time.monotonic() + (60 if expected else 180)
        while not cancelled.is_set():
            try:
                value = self.lines.get(timeout=0.05)
                if expected and any(value.get(key) != item for key, item in expected.items()):
                    raise RuntimeError(
                        "Speech worker returned mismatched request, turn or reference identity"
                    )
                if value.get("error"):
                    raise RuntimeError(str(value["error"]))
                return value
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    raise RuntimeError(
                        "Experimental speech worker exited; retry or switch voices"
                    ) from None
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "Speech worker exceeded its finite response deadline"
                    ) from None
        raise InterruptedError("Experimental speech stopped")

    def prepare(self, cancelled: threading.Event) -> None:
        with self.operation_lock:
            if self.process is not None and self.process.poll() is None:
                return
            if self.process is not None:
                self.close()
            validate_reference(self.reference_path, self.reference_sha256)
            if not self.fixture:
                lock_name = (
                    "chatterbox-maintained-lock.json"
                    if self.configuration == "maintained"
                    else "chatterbox-lock.json"
                )
                lock = json.loads((ROOT / lock_name).read_text(encoding="utf-8"))
                for asset in lock["model"]["files"]:
                    path = self.state / "model" / asset["name"]
                    if not path.is_file() or sha256(path) != asset["sha256"]:
                        raise ValueError(
                            "Pinned Nano model missing or changed; rerun chatterbox-app.ps1"
                        )
            python = (
                Path(sys.executable) if self.fixture else self.state / "venv/Scripts/python.exe"
            )
            if not python.is_file():
                raise ValueError("Experimental environment missing; rerun chatterbox-app.ps1")
            logs = self.state / "worker-logs"
            logs.mkdir(parents=True, exist_ok=True)
            self.log = (logs / f"{uuid.uuid4().hex}.log").open("w", encoding="utf-8")
            self.lines = queue.Queue(2)
            self.epoch = uuid.uuid4().hex
            self.metadata["lifecycle_state"] = "preparing"
            self.process = subprocess.Popen(  # nosec B603
                [
                    str(python),
                    "-I",
                    str(ROOT / "scripts/chatterbox_worker.py"),
                    "--state",
                    str(self.state),
                    "--reference-id",
                    self.identity,
                    "--reference-file",
                    str(self.reference_path),
                    "--reference-sha256",
                    self.reference_sha256,
                    "--epoch",
                    self.epoch,
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
            self.reader = threading.Thread(
                target=self.read, args=(self.process, self.lines), daemon=True
            )
            self.reader.start()
            try:
                ready = self.reply(cancelled)
                if (
                    not ready.get("ready")
                    or ready.get("reference_id") != self.identity
                    or ready.get("reference_sha256") != self.reference_sha256
                    or ready.get("epoch") != self.epoch
                ):
                    raise RuntimeError("Experimental worker prepared the wrong reference or epoch")
                self.metadata.update(ready)
                self.metadata.update(worker_alive=True, lifecycle_state="ready")
            except Exception:
                self.close()
                raise

    def request(self, operation: str, cancelled: threading.Event, **fields: Any) -> dict[str, Any]:
        # The public owner serializes full turns; this lock also bounds each IPC exchange.
        with self.operation_lock:
            try:
                self.prepare(cancelled)
                if self.pending:
                    self.metadata["lifecycle_state"] = "draining"
                    self.reply(cancelled, self.pending)
                    self.pending = None
                if cancelled.is_set():
                    raise InterruptedError("Experimental speech stopped")
                identity = {
                    "epoch": self.epoch,
                    "request_id": uuid.uuid4().hex,
                    "turn_id": self.turn,
                    "reference_id": fields.get("reference_id", self.identity),
                    "reference_sha256": fields.get("reference_sha256", self.reference_sha256),
                }
                message = {"operation": operation, **identity, **fields}
                assert self.process is not None and self.process.stdin is not None  # nosec B101
                self.pending = identity
                self.watchdog = threading.Timer(60, self.expire, args=(self.process, identity))
                self.watchdog.daemon = True
                self.watchdog.start()
                self.process.stdin.write(json.dumps(message) + "\n")
                self.process.stdin.flush()
                self.metadata["lifecycle_state"] = (
                    "synthesising" if operation == "speak" else "preparing"
                )
                value = self.reply(cancelled, identity)
                self.pending = None
                self.metadata["lifecycle_state"] = "ready"
                if "metrics" in value:
                    self.metadata["last_synthesis"] = value["metrics"]
                return value
            except InterruptedError:
                self.abandoned_request = self.pending["request_id"] if self.pending else ""
                self.metadata["lifecycle_state"] = (
                    "draining" if self.pending and self.lines.empty() else "ready"
                )
                raise
            except Exception as error:
                self.close()
                self.metadata.update(lifecycle_state="failed", recovery_error=str(error))
                raise

    def expire(self, process: subprocess.Popen[str], identity: dict[str, str]) -> None:
        # Captured process identity prevents an old deadline terminating a replacement.
        if self.process is process and self.pending == identity and process.poll() is None:
            process.kill()
            self.metadata.update(
                worker_alive=False,
                lifecycle_state="failed",
                recovery_error="Speech worker exceeded its finite response deadline",
            )

    def exchange(self, operation: str, cancelled: threading.Event, text: str = "") -> bytes:
        fault = ""
        if operation == "speak":
            fault, self.fault = self.fault, ""
        value = self.request(operation, cancelled, text=text, fault=fault)
        pcm = base64.b64decode(value.get("pcm", ""), validate=True)
        if len(pcm) % 2 or len(pcm) > 31 * 32000:
            self.close()
            raise ValueError("Experimental worker returned excessive/invalid PCM16")
        if cancelled.is_set():
            raise InterruptedError("Experimental speech stopped")
        return pcm

    def begin_turn(self, cancelled: threading.Event) -> None:
        with self.operation_lock:
            if self.turn_cancelled is not None and not self.turn_cancelled.is_set():
                raise RuntimeError("Another voice turn or preview is active")
            validate_reference(self.reference_path, self.reference_sha256)
            self.prepare(cancelled)
            self.turn, self.turn_cancelled = uuid.uuid4().hex, cancelled
            try:
                self.exchange("begin", cancelled)
            except Exception:
                self.turn_cancelled = None
                raise

    def speak(self, text: str, cancelled: threading.Event) -> bytes:
        with self.operation_lock:
            if cancelled is not self.turn_cancelled:
                raise ValueError("Speech does not belong to the active turn")
            try:
                return self.exchange("speak", cancelled, text)
            except Exception:
                self.turn_cancelled = None
                raise

    def finish_turn(self, cancelled: threading.Event) -> bytes:
        with self.operation_lock:
            if cancelled is not self.turn_cancelled:
                raise ValueError("Speech does not belong to the active turn")
            try:
                return self.exchange("finish", cancelled)
            finally:
                self.turn_cancelled = None

    def set_reference(
        self, identity: str, path: Path, digest: str, cancelled: threading.Event | None = None
    ) -> None:
        with self.operation_lock:
            if self.turn_cancelled is not None and not self.turn_cancelled.is_set():
                raise RuntimeError("Wait until the current voice turn or preview has stopped")
            reference, reference_hash = self.reference(identity, path, digest)
            validate_reference(reference, reference_hash)
            if (
                identity == self.identity
                and reference == self.reference_path.resolve()
                and reference_hash == self.reference_sha256
                and self.pending is None
                and self.process is not None
                and self.process.poll() is None
            ):
                return
            if self.process is not None and self.process.poll() is None:
                try:
                    result = self.request(
                        "reference",
                        cancelled or threading.Event(),
                        reference_id=identity,
                        reference_sha256=reference_hash,
                        reference_file=str(reference),
                    )
                except InterruptedError:
                    # A cancelled conditioning change has no committed identity.
                    self.close()
                    raise
                self.metadata.update(conditioning_cache_size=result["conditioning_cache_size"])
            self.identity, self.reference_path, self.reference_sha256 = (
                identity,
                reference,
                reference_hash,
            )
            self.turn_cancelled = None
            self.metadata.update(reference_id=identity, reference_sha256=reference_hash)

    def close(self) -> None:
        # May be called by shutdown while reply() is polling; do not wait on operation_lock.
        process, self.process = self.process, None
        if self.watchdog:
            self.watchdog.cancel()
            self.watchdog = None
        self.pending, self.turn_cancelled = None, None
        self.metadata.update(worker_alive=False, lifecycle_state="closed")
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
                self.metadata.update(worker_alive=True, lifecycle_state="failed")
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
