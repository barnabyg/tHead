"""Session-scoped cloning operations over the private voice library; no provider calls."""

from __future__ import annotations

import base64
import binascii
import io
import re
import socket
import threading
import wave
from collections import deque
from collections.abc import Callable
from typing import Any

from chatterbox_release import release_readiness
from speech import SpeechVoice
from voices import MAX_INPUT_BYTES, VoiceStore

PREVIEW_TEXT = "Hello. This is a synthetic preview of your saved voice. How can I help you today?"


class VoiceLibrary:
    def __init__(
        self,
        store: VoiceStore,
        fixture: bool,
        engine: Callable[[dict[str, Any], threading.Event | None], SpeechVoice],
        release_preview: Callable[[], None],
    ) -> None:
        self.store, self.fixture, self.engine = store, fixture, engine
        self.release_preview = release_preview
        self.lock = threading.RLock()
        self.upload_slot = threading.BoundedSemaphore(1)
        self.upload_connections: set[socket.socket] = set()
        self.closed = False
        self.operation = ""
        self.candidate_id = ""
        self.cancelled = threading.Event()
        self.obsolete: deque[str] = deque(maxlen=128)
        self.state = "idle"
        self.error = ""
        self.audio = b""
        self.worker: threading.Thread | None = None

    def readiness(self) -> dict[str, Any]:
        if self.fixture:
            return {
                "available": True,
                "error": "",
                "fixture": True,
                "message": "Synthetic protocol fixture. This does not demonstrate cloned speech.",
            }
        return release_readiness()

    def track_upload(self, connection: socket.socket) -> None:
        with self.lock:
            if self.closed:
                raise ValueError("Voice library is shutting down")
            self.upload_connections.add(connection)

    def untrack_upload(self, connection: socket.socket) -> None:
        with self.lock:
            self.upload_connections.discard(connection)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "readiness": self.readiness(),
                "operation": self.operation,
                "candidate": self.candidate_id,
                "state": self.state,
                "error": self.error,
                "previewReady": bool(self.audio) and self.state == "previewed",
                "storageError": self.store.error,
            }

    def require_available(self) -> None:
        readiness = self.readiness()
        if not readiness["available"]:
            raise ValueError(readiness["error"])

    def check_operation(self, identity: Any) -> str:
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9-]{32,36}", identity):
            raise ValueError("Expected a voice operation identity; reopen Clone voice")
        return identity

    def current(self, operation: str) -> None:
        if operation != self.operation or self.cancelled.is_set():
            raise ValueError("Voice operation was cancelled; choose the recording again")

    def import_audio(self, data: dict[str, Any]) -> dict[str, Any]:
        operation = self.check_operation(data.get("operation"))
        with self.lock:
            if self.closed:
                raise ValueError("Voice library is shutting down")
            if operation in self.obsolete:
                raise ValueError("Voice operation was cancelled")
            if self.state in ("importing", "previewing", "cancelling"):
                raise ValueError("Wait for the current voice operation to finish")
            if operation == self.operation and self.candidate_id:
                return self.store.candidate(self.candidate_id)
            self.cancel()
            self.operation = operation
            self.cancelled = threading.Event()
            cancelled = self.cancelled
            self.state, self.error = "importing", ""
        candidate = ""
        try:
            encoded = data.get("audio")
            if not isinstance(encoded, str) or len(encoded) > ((MAX_INPUT_BYTES + 2) // 3) * 4:
                raise ValueError("Choose a WAV, MP3 or M4A recording of at most 20 MiB")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("Recording upload is invalid; choose the file again") from error
            record = self.store.import_audio(
                data.get("name"), data.get("filename"), raw, data.get("permission"), cancelled
            )
            candidate = record["id"]
            with self.lock:
                self.current(operation)
                self.candidate_id = candidate
                self.state = "prepared"
                return record
        except (OSError, ValueError, RuntimeError, TimeoutError, InterruptedError) as error:
            if candidate:
                self.store.cancel(candidate)
            with self.lock:
                if self.operation == operation:
                    self.state, self.error = "failed", str(error)
            raise ValueError(str(error)) from error

    def preview(self, operation: str) -> dict[str, Any]:
        self.require_available()
        with self.lock:
            self.current(operation)
            if self.state not in ("prepared", "previewed"):
                raise ValueError("Prepare the recording before previewing")
            record = self.store.candidate(self.candidate_id)
            self.state, self.error, self.audio = "previewing", "", b""
            self.worker = threading.Thread(
                target=self.synthesise, args=(operation, record, self.cancelled), daemon=True
            )
            self.worker.start()
            return self.status()

    def synthesise(
        self, operation: str, record: dict[str, Any], cancelled: threading.Event
    ) -> None:
        try:
            voice = self.engine(record, cancelled)
            voice.prepare(cancelled)
            voice.begin_turn(cancelled)
            pcm = voice.speak(PREVIEW_TEXT, cancelled) + voice.finish_turn(cancelled)
            if not pcm or len(pcm) % 2 or len(pcm) > 31 * 32000:
                raise ValueError("Preview returned incomplete or excessive audio")
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(pcm)
            self.release_preview()
            with self.lock:
                self.current(operation)
                self.store.mark_previewed(record["id"], record["sha256"])
                self.audio, self.state = buffer.getvalue(), "previewed"
        except (OSError, ValueError, RuntimeError, TimeoutError, InterruptedError) as error:
            with self.lock:
                if self.operation == operation:
                    self.audio = b""
                    self.error = str(error)
                    self.state = "cancelled" if cancelled.is_set() else "failed"
                    self.store.cancel(record["id"])
                    self.candidate_id = ""
        finally:
            if cancelled.is_set():
                try:
                    self.release_preview()
                except (OSError, ValueError, RuntimeError, TimeoutError):
                    # Cancellation remains final even when restoring an unavailable voice fails.
                    pass
            with self.lock:
                if self.operation == operation and self.state == "cancelling":
                    self.state = "cancelled"

    def preview_audio(self, operation: str) -> bytes:
        with self.lock:
            self.current(operation)
            if self.state != "previewed" or not self.audio:
                raise ValueError("Preview is no longer available")
            return self.audio

    def save(self, operation: str, name: Any, repair: str = "") -> dict[str, Any]:
        with self.lock:
            self.current(operation)
            if self.state not in ("previewed", "saved"):
                raise ValueError("Preview this recording successfully before saving")
            record = (
                self.store.repair(repair, self.candidate_id)
                if repair
                else self.store.save(self.candidate_id, name)
            )
            self.state, self.audio = "saved", b""
            return record

    def cancel(self, operation: str = "") -> None:
        with self.lock:
            if operation:
                operation = self.check_operation(operation)
                if operation != self.operation:
                    self.obsolete.append(operation)
                    return
            if self.operation:
                self.obsolete.append(self.operation)
            self.cancelled.set()
            self.audio = b""
            if self.candidate_id and self.state != "saved":
                self.store.cancel(self.candidate_id)
            self.candidate_id = ""
            self.state = "cancelling" if self.worker and self.worker.is_alive() else "cancelled"

    def close(self) -> None:
        self.cancel()
        with self.lock:
            self.closed = True
            for connection in self.upload_connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # The uploading client may already have disconnected.
        if self.worker:
            self.worker.join(timeout=120)
            if self.worker.is_alive():
                raise TimeoutError("Voice preview worker did not release")
