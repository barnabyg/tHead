"""Warm failover through the existing conversation HTTP boundary and real fixture IPC."""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from chatterbox_app import REFERENCES, ExperimentalConversation  # noqa: E402
from chatterbox_engine import ChatterboxEngine  # noqa: E402
from pairs import Avatar  # noqa: E402
from speech import SpeechVoice  # noqa: E402
from streaming import LoopbackServer, handler  # noqa: E402

# B404/B603/B607: fixed local fixture server and task-owned process cleanup.
# Review if executable names, scripts or fault operations become external.


class EngineConversation(ExperimentalConversation):
    def make_voice(self, avatar: Avatar) -> SpeechVoice:
        if avatar.id in REFERENCES:
            return ChatterboxEngine(self.evaluation_state, REFERENCES[avatar.id], fixture=True)
        return super().make_voice(avatar)

    def prepare_voice(self, voice: SpeechVoice) -> None:
        if isinstance(voice, ChatterboxEngine):
            voice.prepare(self.shutdown)
        else:
            super().prepare_voice(voice)

    def speech_pcm(self, text: str, cancelled: threading.Event) -> bytes:
        if isinstance(self.voice, ChatterboxEngine):
            return self.voice.speak(text, cancelled)
        return super().speech_pcm(text, cancelled)

    def command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if path == "/experimental" and isinstance(self.voice, ChatterboxEngine):
            if data.get("session") != self.identity or data.get("fault") not in ("delay", "crash"):
                raise ValueError("Expected an explicit fixture diagnostic")
            self.voice.fault = data["fault"]
            return {"ok": True}
        return super().command(path, data)


def serve(directory: Path) -> None:
    inputs = directory / "inputs"
    inputs.mkdir(parents=True)
    for name in ("portrait.jpg", "hopper.jpg"):
        (inputs / name).write_bytes((ROOT / "tests/fixtures/portrait.jpg").read_bytes())
    app = EngineConversation(inputs, directory, directory / "engine", True, "chatterbox-nano-1089")
    server = LoopbackServer(("127.0.0.1", 0), handler(app))
    lifetime = threading.Timer(180, server.shutdown)
    lifetime.daemon = True
    lifetime.start()
    print(f"LISTEN http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        lifetime.cancel()
        app.shutdown.set()
        if app.current:
            app.stop(app.current.id)
        with app.condition:
            app.condition.notify_all()
        app.voice.close()
        app.worker.join(timeout=120)
        server.server_close()
        if app.worker.is_alive():
            raise TimeoutError("Fixture conversation worker did not stop")


class EngineRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.url = ""
        self.process = subprocess.Popen(  # nosec B603
            [sys.executable, str(Path(__file__).resolve()), "--serve", self.temporary.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(self.close)
        assert self.process.stdout is not None  # nosec B101
        line = self.process.stdout.readline()
        self.assertTrue(line.startswith("LISTEN "), line)
        self.url = line.split()[1]
        self.wait(lambda value: value["ready"])

    def close(self) -> None:
        if self.url and self.process.poll() is None:
            self.request("/shutdown", {})
        try:
            self.process.communicate(timeout=150)
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                subprocess.run(  # nosec B603 B607
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    check=False,
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                self.process.kill()
            self.process.communicate(timeout=30)
            raise

    def request(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = None if data is None else json.dumps(data).encode()
        with urllib.request.urlopen(self.url + path, data=raw, timeout=30) as response:  # nosec B310
            value: dict[str, Any] = json.load(response)
            return value

    def wait(self, predicate: Any) -> dict[str, Any]:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = self.request("/status")
            if predicate(value):
                return value
            time.sleep(0.025)
        self.fail(f"Fixture condition did not complete: {value}")

    def ask(self) -> dict[str, Any]:
        value = self.request("/status")
        return self.request(
            "/ask",
            {
                "session": value["session"],
                "question": "short-1",
                "request": uuid.uuid4().hex,
            },
        )

    def test_cancelled_synthesis_promotes_warm_standby_without_waiting_for_late_pcm(self) -> None:
        initial = self.request("/status")
        worker = initial["experimental"]["voice"]["worker_pid"]
        self.assertEqual(initial["experimental"]["voice"]["worker_count"], 2)
        self.request("/experimental", {"session": initial["session"], "fault": "delay"})
        old = self.ask()
        self.wait(lambda value: value["experimental"]["voice"]["lifecycle_state"] == "synthesising")
        self.request("/stop", {"run": old["id"]})
        self.wait(lambda value: value["state"] == "idle")
        self.ask()
        done = self.wait(lambda value: value["state"] == "idle")
        self.assertEqual(done["run"]["state"], "complete")
        self.assertNotEqual(done["experimental"]["voice"]["worker_pid"], worker)
        onset = next(e["seconds"] for e in done["run"]["events"] if e["event"] == "tts-segment")
        self.assertLess(onset, 2)
        with self.assertRaises(urllib.error.HTTPError) as stale:
            self.request(f"/segment?run={old['id']}&index=0")
        self.assertEqual(stale.exception.code, 410)
        self.wait(lambda value: value["experimental"]["voice"]["ready_workers"] == 2)

    def test_crash_promotes_existing_survivor_and_replenishes_one_replacement(self) -> None:
        initial = self.request("/status")
        worker = initial["experimental"]["voice"]["worker_pid"]
        self.request("/experimental", {"session": initial["session"], "fault": "crash"})
        self.ask()
        failed = self.wait(lambda value: value["state"] == "idle")
        self.assertEqual(failed["run"]["state"], "failed")
        self.assertEqual(failed["session"], initial["session"])
        self.ask()
        done = self.wait(lambda value: value["state"] == "idle")
        self.assertEqual(done["run"]["state"], "complete")
        self.assertNotEqual(done["experimental"]["voice"]["worker_pid"], worker)
        self.assertEqual(done["experimental"]["reference_id"], "librispeech-1089-10s")
        self.wait(lambda value: value["experimental"]["voice"]["ready_workers"] == 2)

    def test_two_cancelled_workers_fail_clearly_without_allocating_a_third(self) -> None:
        initial = self.request("/status")
        for _ in range(2):
            self.request("/experimental", {"session": initial["session"], "fault": "delay"})
            old = self.ask()
            self.wait(
                lambda value: value["experimental"]["voice"]["lifecycle_state"] == "synthesising"
            )
            self.request("/stop", {"run": old["id"]})
            self.wait(lambda value: value["state"] == "idle")
        self.ask()
        unavailable = self.wait(lambda value: value["state"] == "idle")
        self.assertEqual(unavailable["run"]["state"], "failed")
        self.assertIn("Both speech workers", unavailable["run"]["error"])
        self.assertEqual(unavailable["experimental"]["voice"]["worker_count"], 2)
        self.wait(lambda value: value["experimental"]["voice"]["ready_workers"] == 2)
        self.ask()
        complete = self.wait(lambda value: value["state"] == "idle")
        self.assertEqual(complete["run"]["state"], "complete")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]))
    else:
        unittest.main()
