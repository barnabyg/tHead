"""Text pipeline probes through the running HTTP application, without GPU claims."""

import json
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class TextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Fixed task-owned CLI and ephemeral loopback port, not external commands.
        self.process = subprocess.Popen(  # nosec B603
            [
                sys.executable,
                str(ROOT / "scripts/streaming.py"),
                "--port",
                "0",
                "--output",
                self.temporary.name,
                "--test-backend",
                "--speech",
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
        self.idle()

    def stop_process(self) -> None:
        self.process.terminate()
        self.process.communicate(timeout=30)

    def request(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(data).encode() if data is not None else None
        # URL from our loopback CLI, never user-provided external targets.
        with urllib.request.urlopen(self.url + path, data=body, timeout=10) as response:  # nosec B310
            value: dict[str, Any] = json.load(response)
            return value

    def idle(self) -> dict[str, Any]:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = self.request("/status")
            if status["state"] == "idle":
                return status
            time.sleep(0.02)
        self.fail("Application did not become idle")

    def wait_event(self, kind: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = self.request("/status")["run"]
            if any(e["event"] == kind for e in current["events"]):
                return
            time.sleep(0.02)
        self.fail(f"Expected application event: {kind}")

    def test_stop_before_producer_startup_remains_terminal(self) -> None:
        run = self.request("/speak", {"text": "Queued speech.", "fault": "dispatch-delay"})
        self.wait_event("dispatch-delay")
        self.request("/stop", {"run": run["id"]})
        result = self.idle()["run"]
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["parts"], 0)

    def test_entered_text_completes_and_invalid_input_is_rejected(self) -> None:
        for text in ("", " \n ", "a" * 1201):
            with self.assertRaises(urllib.error.HTTPError):
                self.request("/speak", {"text": text})
        run = self.request("/speak", {"text": "Hello world. A final sentence."})
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/speak", {"text": "Overlapping speech"})
        result = self.idle()["run"]
        self.assertEqual(result["id"], run["id"])
        self.assertEqual(result["state"], "complete")
        prepared = [event for event in result["events"] if event["event"] == "tts-segment"]
        self.assertEqual(
            [event["text"] for event in prepared], ["Hello world.", "A final sentence."]
        )

    def test_progressive_media_precedes_final_synthesis_and_preserves_samples(self) -> None:
        self.request("/speak", {"text": "One. Two. Three. Four. Five. Six. Seven. Eight."})
        result = self.idle()["run"]
        events = result["events"]
        media = next(e for e in events if e["event"] == "media-ready")
        complete = next(e for e in events if e["event"] == "tts-complete")
        self.assertLess(media["seconds"], complete["seconds"])
        arrived = [e for e in events if e["event"] == "audio-arrived"]
        self.assertEqual(sum(e["samples"] for e in arrived), 128000)
        received = next(e for e in events if e["event"] == "input-complete")
        self.assertEqual(received["sha256"], complete["sha256"])
        self.assertTrue(arrived[-1]["final"])
        self.assertLessEqual(max(e["queued"] for e in arrived), 2)

    def test_stop_during_synthesis_rejects_late_results_and_recovers_from_failures(self) -> None:
        run = self.request("/speak", {"text": "Delayed speech.", "fault": "tts-delay"})
        self.wait_event("tts-start")
        self.request("/stop", {"run": run["id"]})
        self.request("/stop", {"run": run["id"]})
        stopped = self.idle()["run"]
        self.assertEqual(stopped["state"], "stopped")
        self.assertFalse(
            any(e["event"] in ("tts-segment", "media-ready") for e in stopped["events"])
        )
        for fault in ("tts", "media"):
            self.request("/speak", {"text": "Failure probe.", "fault": fault})
            failed = self.idle()["run"]
            self.assertEqual(failed["state"], "failed")
            self.assertIn("Injected", failed["error"])
        replacement = self.request("/speak", {"text": "Recovered speech."})
        for path, body in (
            ("/telemetry", {"run": run["id"], "currentTime": 90}),
            ("/stop", {"run": run["id"]}),
        ):
            with self.assertRaises(urllib.error.HTTPError):
                self.request(path, body)
        self.assertEqual(self.idle()["run"]["id"], replacement["id"])
        self.assertEqual(self.request("/status")["run"]["state"], "complete")


if __name__ == "__main__":
    unittest.main()
