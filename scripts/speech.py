"""Bounded local English speech adapter; no network, SSML or GPU synthesis."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import re
import subprocess  # nosec B404
import threading
import time
from pathlib import Path
from typing import Any, Protocol


class SpeechVoice(Protocol):
    @property
    def metadata(self) -> dict[str, Any]: ...

    def prepare(self, cancelled: threading.Event) -> None: ...
    def begin_turn(self, cancelled: threading.Event) -> None: ...
    def speak(self, text: str, cancelled: threading.Event) -> bytes: ...
    def finish_turn(self, cancelled: threading.Event) -> bytes: ...
    def close(self) -> None: ...


def segments(text: str) -> list[str]:
    """Normalise whitespace; prefer sentence ends, then whitespace within 180 characters."""
    if not isinstance(text, str) or not text.strip() or len(text) > 1200:
        raise ValueError("Enter 1–1200 characters of English text")
    text = " ".join(text.split())
    result = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > 180:
            cut = sentence.rfind(" ", 0, 181)
            if cut < 1:
                raise ValueError("A word exceeds the 180-character phrase limit")
            result.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            result.append(sentence)
    return result


class Voice:
    """Reusable SAPI owner. Cancellation kills synthesis; the next run reloads the voice."""

    def __init__(self, lock_path: Path | None = None) -> None:
        self.lock_path = lock_path or Path(__file__).parents[1] / "speech-lock.json"
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.lines: queue.Queue[str] = queue.Queue(2)
        self.metadata: dict[str, Any] = {}

    def read(self, process: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
        assert process.stdout is not None  # nosec B101
        for line in process.stdout:
            try:
                lines.put(line, timeout=1)
            except queue.Full:
                return

    def reply(self, cancelled: threading.Event) -> dict[str, Any]:
        deadline = time.monotonic() + 120
        while not cancelled.is_set():
            try:
                value: dict[str, Any] = json.loads(self.lines.get(timeout=0.05))
                return value
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    raise RuntimeError(
                        "Local TTS worker exited; install the declared Desktop voice; "
                        "see windows-pairs.md"
                    ) from None
                if time.monotonic() > deadline:
                    raise TimeoutError("Local TTS exceeded two minutes") from None
        raise InterruptedError("Speech stopped")

    def prepare(self, cancelled: threading.Event) -> None:
        if self.process is not None:
            return
        lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
        windows = Path(os.environ.get("WINDIR", "C:/Windows"))
        for asset in lock["installed_files"]:
            path = windows / asset["path"]
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]
            ):
                raise RuntimeError(
                    f"{lock['voice']} asset missing or changed: {path}; see windows-pairs.md"
                )
        self.lines = queue.Queue(2)
        # B603/B607: fixed Windows executable/script; untrusted text uses JSON stdin only.
        self.process = subprocess.Popen(  # nosec B603 B607
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(Path(__file__).with_name("speech-worker.ps1")),
                "-VoiceName",
                lock["voice"],
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self.reader = threading.Thread(
            target=self.read, args=(self.process, self.lines), daemon=True
        )
        self.reader.start()
        try:
            self.metadata = self.reply(cancelled)
            if not self.metadata.get("ready"):
                raise RuntimeError("Local voice did not become ready")
            if not self.metadata.get("voice_id", "").endswith(lock["voice_token"]):
                raise RuntimeError("Unexpected Windows voice token")
            if self.metadata.get("voice") != lock["voice"] or not self.metadata.get(
                "culture", ""
            ).startswith("en-"):
                raise RuntimeError("Expected the declared local English Desktop voice")
        except Exception:
            self.close()
            raise

    def speak(self, text: str, cancelled: threading.Event) -> bytes:
        try:
            self.prepare(cancelled)
            assert self.process is not None and self.process.stdin is not None  # nosec B101
            self.process.stdin.write(json.dumps({"text": text}) + "\n")
            self.process.stdin.flush()
            pcm = base64.b64decode(self.reply(cancelled)["pcm"], validate=True)
            if not pcm or len(pcm) % 2 or len(pcm) > 30 * 32000:
                raise ValueError("TTS returned invalid or excessive PCM16 audio")
            return pcm
        except Exception:
            self.close()
            raise

    def begin_turn(self, cancelled: threading.Event) -> None:
        pass

    def finish_turn(self, cancelled: threading.Event) -> bytes:
        return b""

    def close(self) -> None:
        process, self.process = self.process, None
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            if self.reader:
                self.reader.join(timeout=5)
                if self.reader.is_alive():
                    raise TimeoutError("TTS pipe reader did not stop")
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
