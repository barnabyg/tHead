"""Bounded continuous H.264/AAC fragmented MP4 transport for the local demo."""

from __future__ import annotations

import queue
import socket
import struct
import subprocess  # nosec B404
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import IO


class Mux:
    """One encoder per run; two loopback PCM/RGB feeds, one continuous MP4 timeline."""

    def __init__(
        self,
        ffmpeg: Path,
        output: Callable[[bytes], None],
        log: Path,
        cancelled: threading.Event,
        fragment_frames: int = 8,
    ) -> None:
        self.output = output
        self.error: Exception | None = None
        self.stopped = threading.Event()
        self.cancelled = cancelled
        self.queues: list[queue.Queue[bytes | None]] = [queue.Queue(2), queue.Queue(2)]
        self.sockets: list[socket.socket] = []
        self.threads: list[threading.Thread] = []
        with ExitStack() as cleanup:
            ports = []
            for _ in range(2):
                listener = socket.socket()
                cleanup.callback(listener.close)
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(1)
                ports.append(listener.getsockname()[1])
                self.sockets.append(listener)
            self.log = log.open("wb")
            cleanup.callback(self.log.close)
            # B603: hash-verified executable, fixed codec flags and task-owned loopback ports.
            # Review if executable/codec selection is ever exposed to HTTP clients.
            self.process = subprocess.Popen(  # nosec B603
                [
                    str(ffmpeg),
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-probesize",
                    "32",
                    "-analyzeduration",
                    "0",
                    "-f",
                    "rawvideo",
                    "-pixel_format",
                    "rgb24",
                    "-video_size",
                    "512x512",
                    "-framerate",
                    "25",
                    "-i",
                    f"tcp://127.0.0.1:{ports[0]}",
                    "-probesize",
                    "32",
                    "-analyzeduration",
                    "0",
                    "-f",
                    "s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-i",
                    f"tcp://127.0.0.1:{ports[1]}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-tune",
                    "zerolatency",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-g",
                    str(fragment_frames),
                    "-keyint_min",
                    str(fragment_frames),
                    "-sc_threshold",
                    "0",
                    "-bf",
                    "0",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "empty_moov+default_base_moof+frag_keyframe",
                    "-flush_packets",
                    "1",
                    "-f",
                    "mp4",
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=self.log,
            )
            cleanup.callback(self.close)
            for index, listener in enumerate(tuple(self.sockets)):
                thread = threading.Thread(
                    target=self.feed, args=(listener, self.queues[index]), daemon=True
                )
                thread.start()
                self.threads.append(thread)
            reader = threading.Thread(target=self.read, daemon=True)
            reader.start()
            self.threads.append(reader)
            cleanup.pop_all()

    def feed(self, listener: socket.socket, items: queue.Queue[bytes | None]) -> None:
        try:
            deadline = time.monotonic() + 300
            while not self.stopped.is_set() and not self.cancelled.is_set():
                if time.monotonic() > deadline:
                    raise TimeoutError("Encoder did not connect within five minutes")
                try:
                    connection, _ = listener.accept()
                    break
                except TimeoutError:
                    continue
            else:
                return
            with connection:
                connection.settimeout(1)
                self.sockets.append(connection)
                while not self.stopped.is_set():
                    try:
                        data = items.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if data is None:
                        break
                    # A timeout is a failure rather than retrying possibly partial writes.
                    connection.settimeout(120)
                    connection.sendall(data)
        except Exception as error:
            if not self.stopped.is_set():
                self.error = error

    def put(self, items: queue.Queue[bytes | None], value: bytes | None) -> None:
        deadline = time.monotonic() + 300
        while not self.stopped.is_set() and not self.cancelled.is_set():
            if time.monotonic() > deadline:
                raise TimeoutError("Encoder input queue blocked for five minutes")
            if self.error:
                raise self.error
            if self.process.poll() is not None:
                raise RuntimeError("Encoder exited before input ended; inspect ffmpeg.log")
            try:
                items.put(value, timeout=0.2)
                return
            except queue.Full:
                continue
        raise RuntimeError("Encoder abandoned")

    def write(self, frames: bytes, pcm: bytes) -> None:
        self.put(self.queues[0], frames)
        self.put(self.queues[1], pcm)

    @staticmethod
    def exact(stream: IO[bytes], count: int) -> bytes:
        data = bytearray()
        while len(data) < count:
            block = stream.read(count - len(data))
            if not block:
                break
            data.extend(block)
        return bytes(data)

    def read(self) -> None:
        try:
            assert self.process.stdout is not None  # nosec B101
            pending = bytearray()
            while header := self.exact(self.process.stdout, 8):
                if len(header) != 8:
                    raise RuntimeError("Truncated MP4 header")
                size, kind = struct.unpack(">I4s", header)
                if not 8 <= size <= 32 * 1024 * 1024:
                    raise RuntimeError(f"Unexpected MP4 box size: {size}")
                payload = self.exact(self.process.stdout, size - 8)
                if len(payload) != size - 8:
                    raise RuntimeError("Truncated MP4 box")
                if kind == b"mfra":
                    continue
                pending.extend(header + payload)
                if kind in (b"moov", b"mdat"):
                    self.output(bytes(pending))
                    pending.clear()
        except Exception as error:
            if not self.stopped.is_set():
                self.error = error

    def finish(self) -> None:
        for items in self.queues:
            self.put(items, None)
        try:
            deadline = time.monotonic() + 300
            while self.process.poll() is None:
                if self.cancelled.is_set() or self.stopped.is_set():
                    raise RuntimeError("Encoder abandoned while draining")
                if self.error:
                    raise self.error
                if time.monotonic() > deadline:
                    raise TimeoutError("Encoder did not finish within five minutes")
                self.stopped.wait(0.1)
            if self.process.returncode:
                raise RuntimeError("Encoder failed; inspect ffmpeg.log")
            for thread in self.threads:
                thread.join(timeout=15)
                if thread.is_alive():
                    raise TimeoutError("Media transport did not drain")
            if self.error:
                raise self.error
        finally:
            self.close()

    def close(self) -> None:
        self.stopped.set()
        try:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=30)
        finally:
            try:
                for connection in self.sockets:
                    connection.close()
                for thread in self.threads:
                    if thread is not threading.current_thread():
                        thread.join(timeout=5)
                if not any(thread.is_alive() for thread in self.threads):
                    if self.process.stdout:
                        self.process.stdout.close()
                else:
                    raise TimeoutError("Media thread did not stop after encoder shutdown")
            finally:
                self.log.close()
