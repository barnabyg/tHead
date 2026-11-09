"""Two bounded warm speech workers with explicit failover and finite replenishment."""

from __future__ import annotations

import hashlib
import importlib
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chatterbox_voice import ChatterboxVoice, reference_record, validate_reference
from shutdown import cleanup, join_worker

MINIMUM_FREE_RAM = 8 * 1024**3
MINIMUM_FREE_VRAM = 8 * 1024**3


@dataclass
class WorkerSlot:
    voice: ChatterboxVoice
    path: Path
    state: str = "unprepared"
    version: int = -1


class ChatterboxEngine:
    def __init__(
        self,
        state: Path,
        identity: str,
        fixture: bool = False,
        configuration: str = "maintained",
        *,
        reference_path: Path | None = None,
        reference_sha256: str | None = None,
    ) -> None:
        if not fixture and configuration not in ("cuda", "maintained"):
            raise ValueError("Conversational failover requires an explicit CUDA configuration")
        if reference_path is None:
            reference_path = state / "references" / f"{identity}.wav"
            reference_sha256 = str(reference_record(identity)["sha256"])
        if reference_sha256 is None:
            raise ValueError("Reference SHA-256 is required")
        self.state, self.fixture, self.configuration = state, fixture, configuration
        self.lock = threading.RLock()
        self.shutdown = threading.Event()
        self.reference = self.load_reference(identity, reference_path, reference_sha256)
        self.version = 0
        self.active = 0
        self.turn: int | None = None
        self.turn_cancelled: threading.Event | None = None
        self.replenisher: threading.Thread | None = None
        self.prepared = False
        self.preparing = False
        self.error = ""
        self.capacity: dict[str, int] = {}
        self.next_fault = ""
        self.pending_discards: dict[str, set[int]] = {}
        pool_id = uuid.uuid4().hex
        self.slots = []
        for index in range(2):
            path = reference_path.parent / f"engine-{pool_id}-{index}.wav"
            voice = ChatterboxVoice(
                state,
                identity,
                fixture,
                configuration,
                reference_path=path,
                reference_sha256=reference_sha256,
            )
            self.slots.append(WorkerSlot(voice, path))

    @staticmethod
    def load_reference(identity: str, path: Path, digest: str) -> tuple[str, bytes, str]:
        validate_reference(path, digest)
        audio = path.read_bytes()
        if len(audio) > 30 * 24000 * 2 + 4096 or hashlib.sha256(audio).hexdigest() != digest:
            raise ValueError("Canonical reference changed or exceeded the audio sample limit")
        return identity, audio, digest

    def check_capacity(self) -> None:
        if self.fixture:
            return
        psutil = importlib.import_module("psutil")
        torch = importlib.import_module("torch")
        if not torch.cuda.is_available():
            raise ValueError("Warm speech failover requires CUDA; no CPU fallback")
        if torch.cuda.get_device_name(0) != "NVIDIA GeForce RTX 3090":
            raise ValueError(
                "Conversational cloned voices require the verified RTX 3090 configuration"
            )
        free_vram, total_vram = torch.cuda.mem_get_info()
        free_ram = int(psutil.virtual_memory().available)
        self.capacity = {
            "free_ram_bytes": free_ram,
            "free_vram_bytes": int(free_vram),
            "total_vram_bytes": int(total_vram),
        }
        if free_vram < MINIMUM_FREE_VRAM or free_ram < MINIMUM_FREE_RAM:
            raise ValueError(
                "Warm standby requires 8 GiB free VRAM and 8 GiB available RAM alongside FlashHead"
            )

    def ready(self, index: int) -> bool:
        slot = self.slots[index]
        return (
            slot.state == "ready"
            and slot.version == self.version
            and slot.voice.process is not None
            and slot.voice.process.poll() is None
        )

    def promote(self) -> bool:
        if self.ready(self.active):
            return True
        for index in range(2):
            if self.ready(index):
                self.active = index
                return True
        return False

    @property
    def metadata(self) -> dict[str, Any]:
        with self.lock:
            for slot in self.slots:
                process = slot.voice.process
                if slot.state == "ready" and (process is None or process.poll() is not None):
                    slot.state = "failed"
                    self.error = "Speech worker exited; using the warm survivor while recovering"
                    self.schedule_replenishment()
            if self.turn is None:
                self.promote()
            active = self.slots[self.turn if self.turn is not None else self.active]
            values = dict(active.voice.metadata)
            ready_workers = sum(self.ready(index) for index in range(2))
            if self.shutdown.is_set():
                lifecycle = "closed"
            elif self.turn is not None:
                lifecycle = active.voice.metadata.get("lifecycle_state", "synthesising")
            elif ready_workers:
                lifecycle = "ready"
            elif self.preparing or self.replenisher and self.replenisher.is_alive():
                lifecycle = "recovering"
            else:
                lifecycle = "unavailable"
            return {
                **values,
                "reference_id": self.reference[0],
                "reference_sha256": self.reference[2],
                "lifecycle_state": lifecycle,
                "worker_alive": active.voice.process is not None
                and active.voice.process.poll() is None,
                "worker_count": sum(
                    slot.voice.process is not None and slot.voice.process.poll() is None
                    for slot in self.slots
                ),
                "ready_workers": ready_workers,
                "conditioning_cache_sizes": [
                    slot.voice.metadata.get("conditioning_cache_size", 0) for slot in self.slots
                ],
                "worker_pids": [slot.voice.metadata.get("worker_pid") for slot in self.slots],
                "pending_conditioning_discards": len(self.pending_discards),
                "replenishing": bool(self.replenisher and self.replenisher.is_alive()),
                "recovery_error": self.error,
                "capacity": dict(self.capacity),
            }

    @property
    def fault(self) -> str:
        return self.next_fault

    @fault.setter
    def fault(self, value: str) -> None:
        self.next_fault = value

    def configure_slot(self, index: int, cancelled: threading.Event) -> None:
        with self.lock:
            version, reference = self.version, self.reference
            slot = self.slots[index]
        voice = slot.voice
        if cancelled.is_set() or self.shutdown.is_set():
            raise InterruptedError("Speech preparation cancelled")
        if voice.pending:
            # Drain obsolete PCM using its original immutable reference before replacing it.
            voice.set_reference(voice.identity, slot.path, voice.reference_sha256, cancelled)
        identity, audio, digest = reference
        temporary = slot.path.with_suffix(".tmp")
        slot.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary.write_bytes(audio)
            temporary.replace(slot.path)
        finally:
            temporary.unlink(missing_ok=True)
        voice.set_reference(identity, slot.path, digest, cancelled)
        if voice.process is None or voice.process.poll() is not None:
            self.check_capacity()
        voice.prepare(cancelled)
        while True:
            self.apply_discards(index, cancelled)
            with self.lock:
                if any(
                    index in indices and digest != voice.reference_sha256
                    for digest, indices in self.pending_discards.items()
                ):
                    continue
                slot.version = version
                slot.state = "ready" if self.version == version else "stale"
                return

    def apply_discards(self, index: int, cancelled: threading.Event) -> None:
        voice = self.slots[index].voice
        while True:
            with self.lock:
                pending = [
                    digest
                    for digest, indices in self.pending_discards.items()
                    if index in indices and digest != voice.reference_sha256
                ]
            if not pending:
                return
            for digest in pending:
                voice.discard_conditioning(digest, cancelled)
                with self.lock:
                    indices = self.pending_discards.get(digest)
                    if indices is not None:
                        indices.discard(index)
                        if not indices:
                            del self.pending_discards[digest]

    def discard_inactive_conditioning(self, cancelled: threading.Event | None = None) -> None:
        with self.lock:
            digests = set(self.pending_discards)
            for slot in self.slots:
                digests.update(slot.voice.metadata.get("conditioning_hashes", []))
                digests.add(slot.voice.reference_sha256)
                if slot.voice.pending:
                    digests.add(slot.voice.pending["reference_sha256"])
            digests.discard(self.reference[2])
        for digest in digests:
            self.discard_conditioning(digest, cancelled)

    def discard_conditioning(self, digest: str, cancelled: threading.Event | None = None) -> None:
        cancellation = cancelled or self.shutdown
        with self.lock:
            if self.shutdown.is_set():
                raise RuntimeError("Speech engine is closed")
            if digest == self.reference[2]:
                return
            if self.turn is not None:
                if self.turn_cancelled is None or not self.turn_cancelled.is_set():
                    raise RuntimeError("Stop the active turn before discarding conditioning")
                self.abandon(self.turn)
            indices = {
                index
                for index, slot in enumerate(self.slots)
                if digest in slot.voice.metadata.get("conditioning_hashes", [])
                or slot.voice.reference_sha256 == digest
                or slot.voice.pending
                and slot.voice.pending.get("reference_sha256") == digest
            }
            if not indices:
                return
            self.pending_discards.setdefault(digest, set()).update(indices)
            idle = [index for index in indices if self.ready(index)]
            for index in idle:
                self.slots[index].state = "maintenance"
        for index in idle:
            try:
                self.apply_discards(index, cancellation)
            except Exception:
                with self.lock:
                    self.slots[index].state = "failed"
                    for remaining in idle:
                        if self.slots[remaining].state == "maintenance":
                            self.slots[remaining].state = "stale"
                    self.schedule_replenishment()
                raise
            with self.lock:
                self.slots[index].state = "ready"
        with self.lock:
            self.promote()

    def prepare(self, cancelled: threading.Event) -> None:
        with self.lock:
            if self.shutdown.is_set():
                raise RuntimeError("Speech engine is closed")
            if self.turn is not None and self.turn_cancelled and self.turn_cancelled.is_set():
                self.abandon(self.turn)
            if self.prepared:
                if not self.promote():
                    self.schedule_replenishment(retry=True)
                    raise RuntimeError(
                        "Both speech workers are unavailable; wait for finite recovery and retry"
                    )
                return
            if self.preparing:
                raise RuntimeError("Speech workers are already preparing")
            self.preparing = True
        try:
            for index in range(2):
                with self.lock:
                    self.slots[index].state = "recovering"
                self.configure_slot(index, cancelled)
            with self.lock:
                self.prepared, self.error = True, ""
        except Exception:
            for slot in self.slots:
                try:
                    slot.voice.close()
                except (OSError, RuntimeError, TimeoutError) as cleanup_error:
                    self.error = str(cleanup_error)
                finally:
                    slot.state = "unprepared"
            raise
        finally:
            with self.lock:
                self.preparing = False

    def schedule_replenishment(self, *, retry: bool = False) -> None:
        # Called with self.lock; exactly one background thread can own a rebuilding slot.
        if (
            self.shutdown.is_set()
            or self.preparing
            or self.replenisher
            and self.replenisher.is_alive()
        ):
            return
        if retry:
            for slot in self.slots:
                if slot.state == "unavailable":
                    slot.state = "failed"
        if not any(slot.state in ("failed", "draining", "stale") for slot in self.slots):
            return
        self.replenisher = threading.Thread(target=self.replenish, daemon=True)
        self.replenisher.start()

    def replenish(self) -> None:
        attempted: set[tuple[int, int]] = set()
        while not self.shutdown.is_set():
            with self.lock:
                candidates = [
                    index
                    for index, slot in enumerate(self.slots)
                    if (index, self.version) not in attempted
                    and slot.state in ("failed", "draining", "stale")
                ]
                if not candidates:
                    return
                index = candidates[0]
                attempted.add((index, self.version))
                if len(attempted) > 6:
                    self.slots[index].state = "unavailable"
                    self.error = "Reference changed repeatedly during recovery; wait and retry"
                    return
                slot = self.slots[index]
                slot.state = "recovering"
            try:
                if slot.voice.process is None or slot.voice.process.poll() is not None:
                    slot.voice.close()
                self.configure_slot(index, self.shutdown)
            except (OSError, ValueError, RuntimeError, TimeoutError, InterruptedError) as error:
                message = str(error)
                try:
                    slot.voice.close()
                except (OSError, RuntimeError, TimeoutError) as cleanup_error:
                    message += f"; worker cleanup failed: {cleanup_error}"
                with self.lock:
                    slot.state = "unavailable"
                    self.error = message

    def begin_turn(self, cancelled: threading.Event) -> None:
        self.prepare(cancelled)
        with self.lock:
            if self.turn is not None:
                raise RuntimeError("Another conversation or voice preview is active")
            if not self.promote():
                raise RuntimeError("Both speech workers are busy or recovering; wait and retry")
            index = self.active
            self.turn, self.turn_cancelled = index, cancelled
            self.slots[index].state = "busy"
        try:
            self.slots[index].voice.begin_turn(cancelled)
        except Exception:
            self.abandon(index)
            raise

    def active_turn(self, cancelled: threading.Event) -> tuple[int, ChatterboxVoice]:
        with self.lock:
            if self.turn is None or cancelled is not self.turn_cancelled:
                raise ValueError("Speech operation does not belong to the active turn")
            return self.turn, self.slots[self.turn].voice

    def abandon(self, index: int) -> None:
        with self.lock:
            slot = self.slots[index]
            process = slot.voice.process
            slot.state = "draining" if process is not None and process.poll() is None else "failed"
            self.turn, self.turn_cancelled = None, None
            self.promote()
            self.schedule_replenishment()

    def speak(self, text: str, cancelled: threading.Event) -> bytes:
        index, voice = self.active_turn(cancelled)
        voice.fault, self.next_fault = self.next_fault, ""
        try:
            return voice.speak(text, cancelled)
        except Exception:
            self.abandon(index)
            raise

    def finish_turn(self, cancelled: threading.Event) -> bytes:
        index, voice = self.active_turn(cancelled)
        try:
            pcm = voice.finish_turn(cancelled)
        except Exception:
            self.abandon(index)
            raise
        with self.lock:
            self.slots[index].state = "ready"
            self.turn, self.turn_cancelled = None, None
        return pcm

    def set_reference(
        self, identity: str, path: Path, digest: str, cancelled: threading.Event | None = None
    ) -> None:
        cancellation = cancelled or self.shutdown
        reference = self.load_reference(identity, path, digest)
        with self.lock:
            if self.shutdown.is_set():
                raise RuntimeError("Speech engine is closed")
            if self.preparing:
                raise RuntimeError("Wait until initial speech preparation finishes")
            if self.turn is not None:
                if self.turn_cancelled is None or not self.turn_cancelled.is_set():
                    raise RuntimeError("Stop the active turn or preview before changing references")
                self.abandon(self.turn)
            if reference[0] == self.reference[0] and reference[2] == self.reference[2]:
                return
            self.reference, self.version = reference, self.version + 1
            # A newly selected saved reference can legitimately share a formerly deleted hash.
            self.pending_discards.pop(reference[2], None)
            indices = [index for index, slot in enumerate(self.slots) if slot.state == "ready"]
            for index in indices:
                self.slots[index].state = "recovering"
        for index in indices:
            try:
                self.configure_slot(index, cancellation)
            except Exception:
                with self.lock:
                    self.slots[index].state = "failed"
                    for pending in indices:
                        if self.slots[pending].state == "recovering":
                            self.slots[pending].state = "stale"
                    if self.prepared:
                        self.schedule_replenishment()
                raise
        with self.lock:
            for slot in self.slots:
                if slot.state == "ready" and slot.version != self.version:
                    slot.state = "stale"
            self.promote()
            if self.prepared:
                self.schedule_replenishment()

    def close(self) -> None:
        self.shutdown.set()
        with self.lock:
            if self.turn_cancelled:
                self.turn_cancelled.set()
        paths = [path for slot in self.slots for path in (slot.path, slot.path.with_suffix(".tmp"))]

        def release_invalidations() -> None:
            with self.lock:
                self.pending_discards.clear()

        cleanup(
            *(
                (f"speech worker {index}", slot.voice.close)
                for index, slot in enumerate(self.slots)
            ),
            ("speech replenisher", lambda: join_worker(self.replenisher, 240)),
            ("conditioning bookkeeping", release_invalidations),
            *(
                ("speech snapshot", lambda path=path: path.unlink(missing_ok=True))
                for path in paths
            ),
        )
