"""Loopback browser demonstration with one persistent native Windows GPU owner."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import platform
import threading
import time
import uuid
import wave
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from prepare import ROOT, RUNTIME
from smoke import load_pipeline
from stream_media import Mux

SAMPLES = 15360


class Session:
    def __init__(self, directory: Path) -> None:
        self.id = uuid.uuid4().hex
        self.directory = directory / self.id
        self.directory.mkdir(parents=True)
        self.condition = threading.Condition()
        self.started = time.perf_counter()
        self.state = "queued"
        self.cancelled = threading.Event()
        self.parts = 0
        self.played = 0.0
        self.error = ""
        self.diagnostic_failure = False
        self.events: list[dict[str, Any]] = []
        self.event("accepted")

    def event(self, kind: str, **data: Any) -> None:
        with self.condition:
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
        (self.directory / "result.json").write_text(
            json.dumps(self.snapshot(), indent=2) + "\n", encoding="utf-8"
        )

    def output(self, data: bytes) -> None:
        with self.condition:
            deadline = time.monotonic() + 300
            while self.parts - 1 - int(self.played / 0.96) >= 3:
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
                pending=max(0, self.parts - int(self.played / 0.96)),
            )
            self.parts += 1
            self.condition.notify_all()


class Demonstration:
    def __init__(self, inputs: Path, directory: Path, test_backend: bool = False) -> None:
        self.inputs = inputs
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.condition = threading.Condition()
        self.state = "loading"
        self.ready = False
        self.error = ""
        self.current: Session | None = None
        self.test_backend = test_backend
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
                "run": self.current.snapshot() if self.current else None,
            }

    def start(self, diagnostic_failure: bool = False) -> Session:
        with self.condition:
            if not self.ready or self.state != "idle":
                raise ValueError("Wait until the model is ready and idle")
            self.current = Session(self.directory)
            self.current.diagnostic_failure = diagnostic_failure and self.test_backend
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
                    session.cancelled.set()
                    session.state = "stopped"
                    session.condition.notify_all()
                    session.save()
            return session

    def work(self) -> None:
        try:
            if self.test_backend:
                self.ready = True
                self.state = "idle"
                while not self.shutdown.is_set():
                    with self.condition:
                        self.condition.wait_for(
                            lambda: self.state == "generating" or self.shutdown.is_set()
                        )
                        if self.shutdown.is_set():
                            return
                        session = self.current
                    assert session is not None  # nosec B101
                    session.event("diagnostic-delay")
                    time.sleep(0.3)  # Simulated non-preemptible external inference.
                    session.output(b"CPU diagnostic result; not playable media")
                    if session.cancelled.is_set():
                        session.event("generation-abandoned")
                    elif session.diagnostic_failure:
                        session.state = "failed"
                        session.error = "Injected external inference failure"
                        session.event("failure", error=session.error)
                    else:
                        session.state = "complete"
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
                pcm = audio.readframes(audio.getnframes())
            if not 0 < len(pcm) <= 30 * 32000:
                raise ValueError("Expected speech lasting at most 30 seconds")
            self.loading["input_sha256"] = hashlib.sha256(pcm).hexdigest()
            pipeline, inference, torch = load_pipeline(
                RUNTIME / "models", RUNTIME / "FlashHead", self.loading
            )
            np = importlib.import_module("numpy")
            with self.condition:
                self.ready = True
                self.state = "idle"
                self.condition.notify_all()
            while not self.shutdown.is_set():
                with self.condition:
                    self.condition.wait_for(
                        lambda: self.state == "generating" or self.shutdown.is_set()
                    )
                    if self.shutdown.is_set():
                        return
                    session = self.current
                assert session is not None  # nosec B101
                self.generate(session, pcm, pipeline, inference, torch, np)
                with self.condition:
                    self.state = "idle"
                    self.condition.notify_all()
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self.state = "failed"
        finally:
            (self.directory / "readiness.json").write_text(
                json.dumps(self.status(), indent=2) + "\n", encoding="utf-8"
            )

    def generate(
        self, session: Session, pcm: bytes, pipeline: Any, inference: Any, torch: Any, np: Any
    ) -> None:
        mux = None
        try:
            session.state = "generating"
            session.event("generation-start", duration=len(pcm) / 32000)
            torch.cuda.reset_peak_memory_stats()
            inference.get_base_data(pipeline, str(self.inputs / "portrait.jpg"), 42, False)
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
            lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
            ffmpeg = RUNTIME / "media" / lock["media"]["directory"] / "bin/ffmpeg.exe"
            mux = Mux(ffmpeg, session.output, session.directory / "ffmpeg.log")
            history: deque[float] = deque([0.0] * 128000, maxlen=128000)
            for index, offset in enumerate(range(0, len(pcm), SAMPLES * 2)):
                if session.cancelled.is_set():
                    return
                chunk = pcm[offset : offset + SAMPLES * 2]
                speech = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
                history.extend(np.pad(speech, (0, SAMPLES - len(speech))).tolist())
                begun = time.perf_counter()
                embedding = inference.get_audio_embedding(pipeline, np.asarray(history), 167, 200)
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
            torch.cuda.synchronize()
            session.event(
                "render-complete",
                allocated_bytes=torch.cuda.memory_allocated(),
                peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                reserved_bytes=torch.cuda.memory_reserved(),
            )
            mux.finish()
            if not session.cancelled.is_set():
                session.state = "complete"
                session.event("transport-complete")
        except Exception as error:
            if not session.cancelled.is_set():
                session.state = "failed"
                session.error = f"{type(error).__name__}: {error}"
                session.event("failure", error=session.error)
        finally:
            if mux:
                mux.close()
            if session.cancelled.is_set():
                session.event("generation-abandoned")
            session.save()


def handler(demo: Demonstration) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
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
                self.reply(200, (ROOT / "scripts/streaming.html").read_bytes(), "text/html")
            elif parsed.path == "/status":
                self.reply(200, json.dumps(demo.status()).encode())
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
                if not 0 <= size <= 65536:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/start":
                    result = demo.start(bool(data.get("diagnosticFailure"))).snapshot()
                elif self.path == "/stop":
                    stopped = demo.stop(str(data.get("run", "")))
                    stopped.event("client-paused", milliseconds=data.get("clientPauseMilliseconds"))
                    stopped.save()
                    result = stopped.snapshot()
                elif self.path == "/telemetry":
                    session = demo.current
                    if not session or data.get("run") != session.id or session.cancelled.is_set():
                        raise ValueError("Stale run")
                    with session.condition:
                        session.played = max(
                            session.played, min(30, float(data.get("currentTime", 0)))
                        )
                        session.event("player", **{k: v for k, v in data.items() if k != "run"})
                        session.condition.notify_all()
                        session.save()
                    result = {"ok": True}
                else:
                    self.reply(404, b"{}")
                    return
                self.reply(200, json.dumps(result).encode())
            except (ValueError, TypeError) as error:
                self.reply(409, json.dumps({"error": str(error)}).encode())

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--inputs", type=Path, default=RUNTIME / "demo-inputs")
    parser.add_argument("--output", type=Path, default=RUNTIME / "streaming")
    parser.add_argument("--test-backend", action="store_true", help="CPU protocol probe; no media")
    args = parser.parse_args()
    demo = Demonstration(args.inputs.resolve(), args.output.resolve(), args.test_backend)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(demo))
    print(f"LISTEN http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        demo.shutdown.set()
        if demo.current:
            demo.stop(demo.current.id)
        with demo.condition:
            demo.condition.notify_all()
        demo.worker.join(timeout=120)


if __name__ == "__main__":
    main()
