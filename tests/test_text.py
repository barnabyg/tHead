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
        assert self.process.stdout is not None  # nosec B101
        self.url = self.process.stdout.readline().strip().split(" ")[1]
        self.idle()

    def tearDown(self) -> None:
        self.process.terminate()
        self.process.communicate(timeout=30)
        self.temporary.cleanup()

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


if __name__ == "__main__":
    unittest.main()
