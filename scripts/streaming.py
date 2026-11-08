"""Loopback browser demonstration with one persistent native Windows GPU owner."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import math
import platform
import socket
import threading
import time
import uuid
import wave
from collections import deque
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pairs import configured_pair
from prepare import ROOT, RUNTIME
from smoke import load_pipeline
from speech import SpeechVoice, Voice, segments
from stream_media import Mux

SAMPLES = 15360


class LoopbackServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits two live listeners, routing to the wrong app.
    allow_reuse_address = False
    # Polling, media and telemetry can burst while a busy Windows host delays accept().
    # The stdlib backlog of five refuses live-server connections in that case.
    request_queue_size = 128

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Session:
    def __init__(self, directory: Path, fragment_frames: int = 8) -> None:
        self.id = uuid.uuid4().hex
        self.directory = directory / self.id
        self.directory.mkdir(parents=True)
        self.condition = threading.Condition()
        self.started = time.perf_counter()
        self.state = "queued"
        self.cancelled = threading.Event()
        self.parts = 0
        self.fragment_seconds = fragment_frames / 25
        self.max_pending = 72 // fragment_frames
        self.played = 0.0
        self.error = ""
        self.diagnostic_failure = False
        self.progressive = False
        self.clip = "six"
        self.text: list[str] = []
        self.fault = ""
        self.input: deque[bytes] = deque()
        self.input_index = 0
        self.input_samples = 0
        self.input_final = False
        self.input_digest = hashlib.sha256()
        self.events: list[dict[str, Any]] = []
        self.event("accepted")

    def event(self, kind: str, **data: Any) -> None:
        with self.condition:
            if self.cancelled.is_set() and kind not in (
                "client-paused",
                "digital-silence",
                "generation-abandoned",
                "tts-released",
                "resources-released",
            ):
                return
            if len(self.events) < 2000:
                self.events.append(
                    {"event": kind, "seconds": time.perf_counter() - self.started, **data}
                )

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            return {
                "id": self.id,
                "state": self.state,
                "parts": self.parts,
                "error": self.error,
                "events": list(self.events),
            }

    def save(self) -> None:
        with self.condition:
            temporary = self.directory / "result.tmp"
            temporary.write_text(json.dumps(self.snapshot(), indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.directory / "result.json")

    def abandon(self) -> None:
        with self.condition:
            self.cancelled.set()
            self.input.clear()
            self.condition.notify_all()

    def output(self, data: bytes) -> None:
        if self.fault == "buffer-delay" and self.parts == 3:
            self.event("buffer-delay")
            self.cancelled.wait(3)
        with self.condition:
            deadline = time.monotonic() + 300
            while self.parts - 1 - int(self.played / self.fragment_seconds) >= self.max_pending:
                if self.cancelled.is_set():
                    return
                if time.monotonic() > deadline:
                    raise TimeoutError("Player did not consume bounded media queue")
                self.condition.wait(0.2)
            if self.cancelled.is_set():
                return
            (self.directory / f"{self.parts}.mp4").write_bytes(data)
            self.event(
                "media-ready",
                index=self.parts,
                bytes=len(data),
                pending=max(0, self.parts - int(self.played / self.fragment_seconds)),
            )
            self.parts += 1
            self.condition.notify_all()

    def receive(self, index: int, chunk: bytes, final: bool) -> None:
        with self.condition:
            if not self.progressive or self.cancelled.is_set() or self.input_final:
                raise ValueError("Run no longer accepts audio")
            if index != self.input_index:
                raise ValueError("Expected the next ordered input index")
            if len(self.input) >= 2:
                raise BlockingIOError("Input queue full")
            if (
                len(chunk) % 2
                or len(chunk) > SAMPLES * 2
                or (not final and len(chunk) != SAMPLES * 2)
                or self.input_samples + len(chunk) // 2 > (120 if self.text else 30) * 16000
                or (not chunk and not self.input_samples)
            ):
                raise ValueError("Expected ordered PCM16 chunks, at most 30 seconds")
            self.input.append(chunk)
            self.input_index += 1
            self.input_samples += len(chunk) // 2
            self.input_digest.update(chunk)
            self.input_final = final
            self.event(
                "audio-arrived",
                index=index,
                samples=len(chunk) // 2,
                received_samples=self.input_samples,
                final=final,
                queued=len(self.input),
            )
            self.condition.notify_all()
            if final:
                self.event(
                    "input-complete",
                    samples=self.input_samples,
                    sha256=self.input_digest.hexdigest(),
                )

    def chunks(self) -> Iterator[bytes]:
        while not self.cancelled.is_set():
            with self.condition:
                if not self.input and not self.input_final:
                    self.event("input-underrun")
                    deadline = time.monotonic() + 120
                    while not self.input and not self.input_final and not self.cancelled.is_set():
                        if time.monotonic() > deadline:
                            raise TimeoutError("No audio arrived for two minutes")
                        self.condition.wait(0.2)
                    self.event("input-resumed")
                if self.cancelled.is_set() or (not self.input and self.input_final):
                    return
                chunk = self.input.popleft()
                self.condition.notify_all()
            if chunk:
                yield chunk


class Demonstration:
    page = "streaming.html"

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("Unknown command")

    def __init__(
        self,
        inputs: Path,
        directory: Path,
        test_backend: bool = False,
        fragment_frames: int = 8,
        speech_enabled: bool = False,
        diagnostics: bool = False,
    ) -> None:
        self.inputs = inputs
        self.portrait_path = inputs / "portrait.jpg"
        self.startup = time.perf_counter()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.condition = threading.Condition()
        self.state = "loading"
        self.ready = False
        self.error = ""
        self.current: Session | None = None
        self.test_backend = test_backend
        self.fragment_frames = fragment_frames
        self.voice: SpeechVoice = Voice()
        self.speech_enabled = speech_enabled
        self.diagnostics = diagnostics or test_backend
        self.shutdown = threading.Event()
        self.loading: dict[str, Any] = {
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    def status(self) -> dict[str, Any]:
        with self.condition:
            return {
                "state": self.state,
                "ready": self.ready,
                "error": self.error,
                "loading": self.loading,
                "speechEnabled": self.speech_enabled,
                "diagnostics": self.diagnostics,
                "run": self.current.snapshot() if self.current else None,
            }

    def start(
        self, diagnostic_failure: bool = False, progressive: bool = False, clip: str = "six"
    ) -> Session:
        with self.condition:
            if not self.ready or self.state != "idle":
                raise ValueError("Wait until the model is ready and idle")
            if clip not in ("six", "long", "short"):
                raise ValueError("Unknown declared audio clip")
            self.current = Session(self.directory, self.fragment_frames)
            self.current.diagnostic_failure = diagnostic_failure and self.test_backend
            self.current.progressive = progressive
            self.current.clip = clip
            self.state = "generating"
            self.condition.notify_all()
            return self.current

    def stop(self, run_id: str) -> Session:
        with self.condition:
            session = self.current
            if not session or session.id != run_id:
                raise ValueError("Stale run")
            with session.condition:
                if not session.cancelled.is_set():
                    session.event("stop-handled")
                    session.state = "stopped"
                    session.abandon()
                    session.save()
            return session

    def speak(self, text: str, fault: str = "") -> Session:
        if not self.speech_enabled:
            raise ValueError("Launch speech-demo.ps1 to enable local TTS")
        if fault and (
            not self.diagnostics
            or fault not in ("tts", "media", "tts-delay", "buffer-delay", "dispatch-delay")
        ):
            raise ValueError("Fault injection requires the explicit diagnostics launcher flag")
        phrases = segments(text)
        with self.condition:
            session = self.start()
            session.text = phrases
            session.fault = fault
            session.progressive = True
            session.event("text-submitted", text=text, segments=len(phrases))
            return session

    def prepare_speech(self, session: Session) -> None:
        with session.condition:
            if session.cancelled.is_set():
                return
            session.state = "synthesising"
        pending = bytearray()
        total = 0
        digest = hashlib.sha256()
        self.voice.begin_turn(session.cancelled)
        for index, text in enumerate(self.phrases(session)):
            # Do not prepare another phrase while a previous phrase still has
            # queued windows. This bounds lookahead and keeps synthesis demand-driven.
            with session.condition:
                deadline = time.monotonic() + 300
                while session.input and not session.cancelled.is_set():
                    if time.monotonic() > deadline:
                        raise TimeoutError("Speech lookahead blocked for five minutes")
                    session.condition.wait(0.1)
            if session.cancelled.is_set():
                return
            begun = time.perf_counter()
            session.event("tts-start", index=index)
            if session.fault == "tts-delay":
                # Diagnostic external operation returns late even after Stop.
                time.sleep(1)
            if session.fault == "tts":
                raise RuntimeError("Injected local TTS failure")
            pcm = self.speech_pcm(text, session.cancelled)
            if session.cancelled.is_set():
                return
            total += len(pcm)
            digest.update(pcm)
            if total > 120 * 32000:
                raise ValueError("Speech exceeds the two-minute limit")
            session.event(
                "tts-segment",
                index=index,
                text=text,
                samples=len(pcm) // 2,
                preparation_seconds=time.perf_counter() - begun,
                engine_metrics=self.voice.metadata.get("last_synthesis", {}),
            )
            pending.extend(pcm)
            # Keep the final partial window until actual end of text. Never pad a
            # phrase boundary or restart avatar/mux state between phrases.
            while len(pending) >= SAMPLES * 2:
                self.handoff(session, bytes(pending[: SAMPLES * 2]), False)
                del pending[: SAMPLES * 2]
        if session.cancelled.is_set():
            return
        tail = self.voice.finish_turn(session.cancelled)
        pending.extend(tail)
        digest.update(tail)
        total += len(tail)
        if total > 120 * 32000:
            raise ValueError("Speech exceeds the two-minute limit")
        if tail:
            session.event("tts-tail", samples=len(tail) // 2)
        self.handoff(session, bytes(pending), True)
        session.event("tts-complete", samples=total // 2, sha256=digest.hexdigest())

    def speech_pcm(self, text: str, cancelled: threading.Event) -> bytes:
        if self.test_backend:
            cancelled.wait(0.15)
            return b"\x01\x00" * 16000
        return self.voice.speak(text, cancelled)

    def phrases(self, session: Session) -> Iterator[str]:
        yield from session.text

    def readiness(self) -> dict[str, Any]:
        return self.status()

    @staticmethod
    def handoff(session: Session, chunk: bytes, final: bool) -> None:
        with session.condition:
            deadline = time.monotonic() + 300
            while len(session.input) >= 2 and not session.cancelled.is_set():
                if time.monotonic() > deadline:
                    raise TimeoutError("Speech handoff blocked for five minutes")
                session.condition.wait(0.1)
            if not session.cancelled.is_set():
                session.receive(session.input_index, chunk, final)

    def begin_speech(self, session: Session) -> threading.Thread | None:
        if not session.text:
            return None

        def produce() -> None:
            if session.fault == "dispatch-delay":
                session.event("dispatch-delay")
                session.cancelled.wait(1)
            try:
                self.prepare_speech(session)
            except Exception as error:
                with session.condition:
                    if not session.cancelled.is_set():
                        session.error = f"{type(error).__name__}: {error}"
                        session.state = "failed"
                        session.event("failure", error=session.error)
                        session.abandon()

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()
        return producer

    def finish_speech(self, session: Session, producer: threading.Thread | None) -> None:
        if producer:
            producer.join(timeout=30)
            if producer.is_alive():
                raise TimeoutError("Speech producer did not release within thirty seconds")
            session.event("tts-released")
        session.save()

    def prepare_assets(self, pipeline: Any, inference: Any) -> None:
        if self.speech_enabled and not self.test_backend:
            self.voice.prepare(self.shutdown)
            self.loading["tts"] = self.voice.metadata

    def load_assets(self, pipeline: Any, inference: Any) -> None:
        self.prepare_assets(pipeline, inference)
        with self.condition:
            self.ready = True
            self.state = "idle"
            self.condition.notify_all()

    def wait_for_session(self, pipeline: Any, inference: Any) -> Session | None:
        while not self.shutdown.is_set():
            with self.condition:
                self.condition.wait_for(
                    lambda: self.state in ("generating", "selecting") or self.shutdown.is_set()
                )
                if self.shutdown.is_set():
                    return None
                if self.state == "generating":
                    return self.current
            self.load_assets(pipeline, inference)
        return None

    def work(self) -> None:
        try:
            if self.test_backend:
                self.load_assets(None, None)
                self.loading["ready_seconds"] = time.perf_counter() - self.startup
                while not self.shutdown.is_set():
                    session = self.wait_for_session(None, None)
                    if session is None:
                        return
                    producer = self.begin_speech(session)
                    session.event("diagnostic-delay")
                    chunks = session.chunks() if session.progressive else iter([b"diagnostic"])
                    for _ in chunks:
                        time.sleep(0.3)  # Simulated non-preemptible external inference.
                        if session.fault == "media":
                            session.state = "failed"
                            session.error = "Injected media failure"
                            session.event("failure", error=session.error)
                            session.abandon()
                            break
                        session.output(b"CPU diagnostic result; not playable media")
                    if session.cancelled.is_set():
                        session.event("generation-abandoned")
                    elif session.diagnostic_failure:
                        session.state = "failed"
                        session.error = "Injected external inference failure"
                        session.event("failure", error=session.error)
                    elif session.state != "failed":
                        session.state = "complete"
                    self.finish_speech(session, producer)
                    session.event("resources-released")
                    session.save()
                    self.state = "idle"
                return
            with wave.open(str(self.inputs / "english.wav"), "rb") as audio:
                if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (
                    16000,
                    1,
                    2,
                ):
                    raise ValueError("Expected mono 16 kHz PCM16 audio")
                samples = audio.getnframes()
            if not 0 < samples <= 30 * 16000:
                raise ValueError("Expected speech lasting at most 30 seconds")
            pipeline, inference, torch = load_pipeline(
                RUNTIME / "models", RUNTIME / "FlashHead", self.loading
            )
            np = importlib.import_module("numpy")
            self.load_assets(pipeline, inference)
            with self.condition:
                self.loading["ready_seconds"] = time.perf_counter() - self.startup
                (self.directory / "readiness.json").write_text(
                    json.dumps(self.readiness(), indent=2) + "\n", encoding="utf-8"
                )
                self.condition.notify_all()
            while not self.shutdown.is_set():
                session = self.wait_for_session(pipeline, inference)
                if session is None:
                    return
                producer = self.begin_speech(session)
                self.generate(session, pipeline, inference, torch, np)
                self.finish_speech(session, producer)
                session.event(
                    "resources-released",
                    allocated_bytes=torch.cuda.memory_allocated(),
                    reserved_bytes=torch.cuda.memory_reserved(),
                    rss_bytes=importlib.import_module("psutil").Process().memory_info().rss,
                    queued_audio=len(session.input),
                )
                session.save()
                with self.condition:
                    self.state = "idle"
                    self.condition.notify_all()
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self.state = "failed"
        finally:
            self.voice.close()
            (self.directory / "readiness.json").write_text(
                json.dumps(self.readiness(), indent=2) + "\n", encoding="utf-8"
            )

    def generate(
        self, session: Session, pipeline: Any, inference: Any, torch: Any, np: Any
    ) -> None:
        mux = None
        try:
            if session.cancelled.is_set():
                return
            with session.condition:
                if session.cancelled.is_set():
                    return
                session.state = "generating"
            session.event("generation-start", progressive=session.progressive, clip=session.clip)
            session.event(
                "transport-profile",
                fragment_frames=self.fragment_frames,
                fragment_seconds=session.fragment_seconds,
                max_pending_fragments=session.max_pending,
            )
            torch.cuda.reset_peak_memory_stats()
            inference.get_base_data(pipeline, str(self.portrait_path), 42, False)
            params = inference.get_infer_params()
            if (
                params["frame_num"],
                params["motion_frames_num"],
                params["tgt_fps"],
                params["sample_rate"],
                params["height"],
                params["width"],
            ) != (33, 9, 25, 16000, 512, 512):
                raise RuntimeError("Pinned streaming profile changed")
            session.event("portrait-ready", settings=params)
            if session.fault == "media":
                raise RuntimeError("Injected media failure")
            lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
            ffmpeg = RUNTIME / "media" / lock["media"]["directory"] / "bin/ffmpeg.exe"
            mux = Mux(
                ffmpeg,
                session.output,
                session.directory / "ffmpeg.log",
                session.cancelled,
                self.fragment_frames,
            )
            history: deque[float] = deque([0.0] * 128000, maxlen=128000)
            if session.progressive:
                chunks = session.chunks()
            else:
                pcm = self.audio(session.clip)
                session.event(
                    "complete-input",
                    duration=len(pcm) / 32000,
                    sha256=hashlib.sha256(pcm).hexdigest(),
                )
                chunks = (pcm[i : i + SAMPLES * 2] for i in range(0, len(pcm), SAMPLES * 2))
            sample_count = 0
            for index, chunk in enumerate(chunks):
                if session.cancelled.is_set():
                    return
                session.event(
                    "chunk-generation-start",
                    index=index,
                    received_samples=session.input_samples if session.progressive else None,
                )
                sample_count += len(chunk) // 2
                speech = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
                history.extend(np.pad(speech, (0, SAMPLES - len(speech))).tolist())
                begun = time.perf_counter()
                embedding = inference.get_audio_embedding(pipeline, np.asarray(history), 167, 200)
                session.event("inference-start", index=index)
                frames = inference.run_pipeline(pipeline, embedding)[9:]
                frames = frames.to(torch.uint8).cpu().numpy()
                if session.cancelled.is_set():
                    return
                count = math.ceil(len(chunk) / 1280)
                session.event(
                    "frames-ready",
                    index=index,
                    frames=count,
                    generation_seconds=time.perf_counter() - begun,
                )
                mux.write(frames[:count].tobytes(), chunk)
            if session.cancelled.is_set():
                return
            torch.cuda.synchronize()
            session.event(
                "render-complete",
                samples=sample_count,
                allocated_bytes=torch.cuda.memory_allocated(),
                peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                reserved_bytes=torch.cuda.memory_reserved(),
                rss_bytes=importlib.import_module("psutil").Process().memory_info().rss,
            )
            mux.finish()
            with session.condition:
                if not session.cancelled.is_set():
                    session.state = "complete"
                    session.event("transport-complete")
        except Exception as error:
            if not session.cancelled.is_set():
                session.state = "failed"
                session.error = f"{type(error).__name__}: {error}"
                session.event("failure", error=session.error)
                session.abandon()
        finally:
            if mux:
                try:
                    mux.close()
                except Exception as error:
                    session.state = "failed"
                    session.error = f"Encoder cleanup failed: {type(error).__name__}: {error}"
                    session.event("failure", error=session.error)
            if session.cancelled.is_set():
                session.event("generation-abandoned")
            session.save()

    def audio(self, clip: str) -> bytes:
        if clip not in ("six", "long", "short"):
            raise ValueError("Unknown declared audio clip")
        path = self.inputs / ("english-long.wav" if clip == "long" else "english.wav")
        with wave.open(str(path), "rb") as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError("Expected mono 16 kHz PCM16 audio")
            count = 5600 if clip == "short" else audio.getnframes()
            if not 0 < count <= 30 * 16000:
                raise ValueError("Expected at most 30 seconds")
            return audio.readframes(count)


def handler(demo: Demonstration) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def parse_request(self) -> bool:
            if not super().parse_request():
                return False
            assert isinstance(self.server, ThreadingHTTPServer)  # nosec B101
            allowed = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if self.headers.get("Host") not in allowed:
                self.send_error(403, "Use the loopback application address")
                return False
            return True

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def reply(self, code: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self.reply(200, (ROOT / "scripts" / demo.page).read_bytes(), "text/html")
            elif parsed.path == "/player.js":
                self.reply(200, (ROOT / "scripts/streaming.js").read_bytes(), "text/javascript")
            elif parsed.path == "/status":
                self.reply(200, json.dumps(demo.status()).encode())
            elif parsed.path == "/portrait":
                # Resolve only declared assets; never accept a filesystem path from the URL.
                try:
                    identity = query.get("avatar", query.get("pair", [""]))[0]
                    if hasattr(demo, "portrait"):
                        picture = demo.portrait(identity)
                    else:
                        pair = configured_pair(identity)
                        picture = (demo.inputs / str(pair.portrait["filename"])).read_bytes()
                    self.reply(
                        200,
                        picture,
                        "image/png" if picture.startswith(b"\x89PNG") else "image/jpeg",
                    )
                except ValueError:
                    self.reply(400, b'{"error":"Unknown avatar"}')
                except OSError:
                    self.reply(404, b'{"error":"Portrait unavailable; rerun preparation"}')
            elif parsed.path == "/audio":
                try:
                    self.reply(
                        200, demo.audio(query.get("clip", ["six"])[0]), "application/octet-stream"
                    )
                except (ValueError, OSError) as error:
                    self.reply(400, json.dumps({"error": str(error)}).encode())
            elif parsed.path == "/segment":
                session = demo.current
                if not session or query.get("run") != [session.id] or session.cancelled.is_set():
                    self.reply(410, b"{}")
                    return
                index = int(query.get("index", ["-1"])[0])
                with session.condition:
                    if 0 <= index < session.parts:
                        self.reply(
                            200, (session.directory / f"{index}.mp4").read_bytes(), "video/mp4"
                        )
                    elif session.state in ("failed", "complete"):
                        self.reply(410 if session.state == "failed" else 204, b"")
                    else:
                        self.reply(202, b"{}")
            else:
                self.reply(404, b"{}")

        def do_POST(self) -> None:
            # Browser-only loopback experiment: reject cross-origin mutation and oversized bodies.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                self.reply(403, b"{}")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                limit = 7 * 1024 * 1024 if self.path in ("/avatars", "/avatars/update") else 65536
                if not 0 <= size <= limit:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/shutdown" and demo.diagnostics:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    result = {"ok": True}
                elif self.path == "/experimental" and getattr(demo, "experimental_enabled", False):
                    result = demo.command(self.path, data)
                elif self.path in (
                    "/ask",
                    "/reset",
                    "/cancel",
                    "/select",
                    "/avatars",
                    "/avatars/update",
                    "/avatars/delete",
                    "/settings",
                ):
                    result = demo.command(self.path, data)
                elif demo.page == "conversation.html" and self.path in (
                    "/speak",
                    "/start",
                    "/input",
                ):
                    raise ValueError("Use the conversation controls")
                elif self.path == "/speak":
                    result = demo.speak(data.get("text", ""), str(data.get("fault", ""))).snapshot()
                elif self.path == "/start":
                    result = demo.start(
                        bool(data.get("diagnosticFailure")),
                        bool(data.get("progressive")),
                        str(data.get("clip", "six")),
                    ).snapshot()
                elif self.path == "/input":
                    session = demo.current
                    if not session or data.get("run") != session.id or session.text:
                        raise ValueError("Stale run")
                    session.receive(
                        int(data["index"]),
                        base64.b64decode(data["pcm"], validate=True),
                        bool(data.get("final")),
                    )
                    result = {"ok": True}
                elif self.path == "/stop":
                    stopped = demo.stop(str(data.get("run", "")))
                    stopped.event("client-paused", milliseconds=data.get("clientPauseMilliseconds"))
                    if isinstance(data.get("digitalSilence"), dict):
                        stopped.event("digital-silence", **data["digitalSilence"])
                    stopped.save()
                    result = stopped.snapshot()
                elif self.path == "/telemetry":
                    session = demo.current
                    if not session or data.get("run") != session.id or session.cancelled.is_set():
                        raise ValueError("Stale run")
                    with session.condition:
                        if session.cancelled.is_set():
                            raise ValueError("Stale run")
                        position = float(data.get("currentTime", 0))
                        if not math.isfinite(position) or position < 0:
                            raise ValueError("Expected a finite nonnegative playback position")
                        session.played = max(session.played, min(120, position))
                        session.event("player", **{k: v for k, v in data.items() if k != "run"})
                        session.condition.notify_all()
                        session.save()
                    result = {"ok": True}
                else:
                    self.reply(404, b"{}")
                    return
                self.reply(200, json.dumps(result).encode())
            except BlockingIOError as error:
                self.reply(429, json.dumps({"error": str(error)}).encode())
            except (ValueError, TypeError, KeyError) as error:
                self.reply(409, json.dumps({"error": str(error)}).encode())

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--inputs", type=Path, default=RUNTIME / "demo-inputs")
    parser.add_argument("--output", type=Path, default=RUNTIME / "streaming")
    parser.add_argument("--test-backend", action="store_true", help="CPU protocol probe; no media")
    parser.add_argument("--fragment-frames", type=int, choices=(8, 24), default=8)
    parser.add_argument("--speech", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    demo = Demonstration(
        args.inputs.resolve(),
        args.output.resolve(),
        args.test_backend,
        args.fragment_frames,
        args.speech,
        args.diagnostics,
    )
    server = LoopbackServer(("127.0.0.1", args.port), handler(demo))
    lifetime = threading.Timer(7200, server.shutdown)
    lifetime.daemon = True
    lifetime.start()
    print(f"LISTEN http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        lifetime.cancel()
        server.server_close()
        demo.shutdown.set()
        if demo.current:
            demo.stop(demo.current.id)
        with demo.condition:
            demo.condition.notify_all()
        demo.worker.join(timeout=120)


if __name__ == "__main__":
    main()
