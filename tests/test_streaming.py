"""Exercise streaming sessions through the local HTTP demonstration boundary."""

import base64
import json
import socket
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from streaming import LoopbackServer  # noqa: E402


class StreamingTests(unittest.TestCase):
    def test_loopback_accepts_browser_connection_burst_before_dispatch(self) -> None:
        # Model a descheduled accept loop on a busy host: browser polling, telemetry,
        # media and control connections must queue until request dispatch resumes.
        connections: list[socket.socket] = []
        with LoopbackServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as server:

            def connect() -> None:
                connections.append(
                    socket.create_connection(("127.0.0.1", server.server_port), timeout=10)
                )

            try:
                with ThreadPoolExecutor(max_workers=16) as pool:
                    results = [pool.submit(connect) for _ in range(16)]
                    for result in results:
                        result.result()
                self.assertEqual(len(connections), 16)
            finally:
                for connection in connections:
                    connection.close()

    def test_stopped_run_cannot_publish_delayed_results_and_replacement_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            # Explicit CPU-only system-boundary probe, never GPU/playback evidence.
            process = subprocess.Popen(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/streaming.py"),
                    "--port",
                    "0",
                    "--output",
                    temporary,
                    "--test-backend",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                assert process.stdout is not None  # nosec B101
                url = process.stdout.readline().strip().split(" ")[1]

                def request(path: str, data: dict[str, object] | None = None) -> dict[str, object]:
                    body = json.dumps(data).encode() if data is not None else None
                    # Task-owned loopback service only.
                    with urllib.request.urlopen(url + path, data=body, timeout=10) as response:  # nosec B310
                        value: dict[str, object] = json.load(response)
                        return value

                def idle() -> None:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if request("/status")["state"] == "idle":
                            return
                        time.sleep(0.02)
                    self.fail("GPU owner did not become available")

                idle()
                progressive = request("/start", {"progressive": True})
                time.sleep(0.4)
                awaiting = request("/status")["run"]
                assert isinstance(awaiting, dict)  # nosec B101
                self.assertEqual(awaiting["parts"], 0)
                request(
                    "/input",
                    {
                        "run": progressive["id"],
                        "index": 0,
                        "pcm": base64.b64encode(b"\x01\x00" * 800).decode(),
                        "final": True,
                    },
                )
                idle()
                with self.assertRaises(urllib.error.HTTPError):
                    request(
                        "/input", {"run": progressive["id"], "index": 1, "pcm": "", "final": True}
                    )
                abandoned = request("/start", {})
                request("/stop", {"run": abandoned["id"]})
                request("/stop", {"run": abandoned["id"]})
                idle()
                with self.assertRaises(urllib.error.HTTPError) as expired:
                    request(f"/segment?run={abandoned['id']}&index=0")
                self.assertEqual(expired.exception.code, 410)
                request("/start", {"diagnosticFailure": True})
                idle()
                failed = request("/status")["run"]
                assert isinstance(failed, dict)  # nosec B101
                self.assertEqual(failed["state"], "failed")
                replacement = request("/start", {})
                idle()
                status = request("/status")
                run = status["run"]
                self.assertIsInstance(run, dict)
                assert isinstance(run, dict)  # nosec B101
                self.assertEqual(run["id"], replacement["id"])
                self.assertEqual(run["state"], "complete")
                self.assertEqual(run["parts"], 1)
                with self.assertRaises(urllib.error.HTTPError):
                    request("/telemetry", {"run": abandoned["id"], "currentTime": 30})
            finally:
                process.terminate()
                process.communicate(timeout=30)

    def test_missing_inputs_exposes_failure_instead_of_ready(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Fixed repository CLI; B603 reviewed if executable selection becomes external.
        process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                str(ROOT / "scripts/streaming.py"),
                "--port",
                "0",
                "--inputs",
                "missing",
                "--output",
                temporary.name,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert process.stdout is not None  # nosec B101
            line = process.stdout.readline()
            self.assertTrue(line.startswith("LISTEN "), line)
            url = line.strip().split(" ")[1]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                # Loopback address emitted by the task-owned server, no external URL.
                with urllib.request.urlopen(url + "/status", timeout=5) as response:  # nosec B310
                    status = json.load(response)
                if status["state"] == "failed":
                    break
                time.sleep(0.05)
            self.assertEqual(status["state"], "failed")
            self.assertFalse(status["ready"])
            self.assertIn("english.wav", status["error"])
        finally:
            process.terminate()
            process.communicate(timeout=30)


if __name__ == "__main__":
    unittest.main()
