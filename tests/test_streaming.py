"""Exercise streaming sessions through the local HTTP demonstration boundary."""

import json
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StreamingTests(unittest.TestCase):
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
