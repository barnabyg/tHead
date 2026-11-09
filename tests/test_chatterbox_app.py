"""Experimental reference-voice acceptance through loopback HTTP; no models or paid calls."""

# B404/B603/B607: fixed local scripts and task-owned process-tree cleanup only.
# Review if executables/commands become externally supplied.
import json
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class ChatterboxAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.url = ""
        self.addCleanup(self.temporary.cleanup)
        self.process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                str(ROOT / "scripts/chatterbox_app.py"),
                "--test-backend",
                "--port",
                "0",
                "--output",
                self.temporary.name,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(self.stop_process)
        assert self.process.stdout is not None  # nosec B101
        line = self.process.stdout.readline()
        self.assertTrue(line.startswith("LISTEN "), line)
        self.url = line.strip().split(" ")[1]
        self.wait(lambda s: s["ready"])

    def stop_process(self) -> None:
        if self.process.poll() is None and self.url:
            try:
                self.request("/shutdown", {})
            except OSError:
                self.kill_process()
        try:
            self.process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            self.kill_process()
            self.process.communicate(timeout=30)

    def kill_process(self) -> None:
        if sys.platform == "win32":
            subprocess.run(  # nosec B603 B607
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        else:
            self.process.kill()

    def request(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(self.url + path, data=body, timeout=30) as response:  # nosec B310
            value: dict[str, Any] = json.load(response)
            return value

    def wait(self, predicate: Any) -> dict[str, Any]:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            status = self.request("/status")
            if predicate(status):
                return status
            time.sleep(0.05)
        self.fail(f"Application condition timed out: {status}")

    def select_clone(self) -> dict[str, Any]:
        status = self.request("/status")
        self.request("/select", {"session": status["session"], "avatar": "chatterbox-nano-1089"})
        return self.wait(lambda s: s["ready"] and s["activeAvatar"] == "chatterbox-nano-1089")

    def ask(self, text: str = "short-1") -> dict[str, Any]:
        status = self.request("/status")
        return self.request(
            "/ask", {"session": status["session"], "question": text, "request": uuid.uuid4().hex}
        )

    def test_stop_retains_warm_worker_and_discards_late_pcm_before_replacement(self) -> None:
        selected = self.select_clone()
        self.assertEqual(selected["experimental"]["reference_id"], "librispeech-1089-10s")
        self.request("/experimental", {"session": selected["session"], "fault": "delay"})
        old = self.ask()
        self.wait(lambda s: any(e["event"] == "tts-start" for e in s["run"]["events"]))
        self.request("/stop", {"run": old["id"]})
        stopped = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(stopped["run"]["state"], "stopped")
        self.assertTrue(stopped["experimental"]["worker_alive"])
        self.assertEqual(
            stopped["experimental"]["voice"]["worker_pid"],
            selected["experimental"]["voice"]["worker_pid"],
        )
        with self.assertRaises(urllib.error.HTTPError) as stale:
            self.request(f"/segment?run={old['id']}&index=0")
        self.assertEqual(stale.exception.code, 410)
        replacement = self.ask()
        done = self.wait(lambda s: s["state"] == "idle")
        self.assertNotEqual(replacement["id"], old["id"])
        self.assertEqual(done["run"]["state"], "complete")
        self.assertEqual(done["run"]["pair"], "chatterbox-nano-1089")
        self.assertTrue(done["experimental"]["worker_alive"])
        self.assertEqual(
            done["experimental"]["voice"]["worker_pid"],
            selected["experimental"]["voice"]["worker_pid"],
        )
        self.assertEqual(done["experimental"]["voice"]["lifecycle_state"], "ready")

    def test_reset_during_synthesis_reuses_reference_without_reviving_old_turn(self) -> None:
        selected = self.select_clone()
        self.request("/experimental", {"session": selected["session"], "fault": "delay"})
        old = self.ask()
        self.wait(lambda s: any(e["event"] == "tts-start" for e in s["run"]["events"]))
        began = time.monotonic()
        self.request("/reset", {"session": selected["session"]})
        stopped = self.wait(lambda s: s["state"] == "idle")
        self.assertLess(time.monotonic() - began, 1)
        self.assertNotEqual(stopped["session"], selected["session"])
        self.assertEqual(stopped["transcript"], [])
        self.assertIsNone(stopped["run"])
        self.ask("short-2")
        complete = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(complete["run"]["state"], "complete")
        self.assertEqual(
            complete["experimental"]["voice"]["worker_pid"],
            selected["experimental"]["voice"]["worker_pid"],
        )
        self.assertEqual(len(complete["transcript"]), 1)
        with self.assertRaises(urllib.error.HTTPError) as stale:
            self.request(f"/segment?run={old['id']}&index=0")
        self.assertEqual(stale.exception.code, 410)

    def test_worker_crash_is_explicit_and_new_conversation_recovers_without_fallback(self) -> None:
        selected = self.select_clone()
        self.request("/experimental", {"session": selected["session"], "fault": "crash"})
        self.ask()
        failed = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(failed["run"]["state"], "failed")
        self.assertIn("worker exited", failed["run"]["error"])
        self.assertFalse(failed["experimental"]["worker_alive"])
        self.request("/reset", {"session": failed["session"]})
        self.ask()
        recovered = self.wait(lambda s: s["state"] == "idle")
        self.assertEqual(recovered["run"]["state"], "complete")
        self.assertEqual(recovered["experimental"]["reference_id"], "librispeech-1089-10s")
        self.assertNotEqual(
            recovered["experimental"]["voice"]["worker_pid"],
            selected["experimental"]["voice"]["worker_pid"],
        )

    def test_unknown_reference_paths_are_rejected_and_missing_assets_fail_explicitly(self) -> None:
        selected = self.select_clone()
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.request(
                "/experimental",
                {"session": selected["session"], "reference_path": "C:/private.wav"},
            )
        self.assertEqual(invalid.exception.code, 409)
        for fault in ("missing-reference", "missing-model"):
            current = self.request("/status")
            self.request("/experimental", {"session": current["session"], "fault": fault})
            self.ask()
            failed = self.wait(lambda s: s["state"] == "idle")
            self.assertEqual(failed["run"]["state"], "failed")
            self.assertIn(fault, failed["run"]["error"])
            self.assertEqual(failed["selectedAvatar"], "chatterbox-nano-1089")
            self.request("/reset", {"session": failed["session"]})

    def test_reference_identity_is_reused_after_server_restart(self) -> None:
        selected = self.select_clone()
        self.assertEqual(selected["activeAvatar"], "chatterbox-nano-1089")
        self.stop_process()
        self.process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                str(ROOT / "scripts/chatterbox_app.py"),
                "--test-backend",
                "--port",
                "0",
                "--output",
                self.temporary.name,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert self.process.stdout is not None  # nosec B101
        self.url = self.process.stdout.readline().strip().split(" ")[1]
        restarted = self.wait(lambda s: s["ready"])
        self.assertEqual(restarted["activeAvatar"], "chatterbox-nano-1089")
        self.assertEqual(restarted["experimental"]["reference_id"], "librispeech-1089-10s")


if __name__ == "__main__":
    unittest.main()
