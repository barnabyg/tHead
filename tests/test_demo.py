"""Test diagnostic failures through the generation command boundary."""

import json
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DemoCommandTests(unittest.TestCase):
    def test_missing_input_replaces_stale_success_with_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.json"
            report.write_text('{"status": "generated"}', encoding="utf-8")
            # Fixed shell-free repository CLI; review B603 if commands become external.
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/generate_clip.py"),
                    "--inputs",
                    temporary,
                    "--report",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            evidence = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "blocked")
            self.assertEqual(evidence["stage"], "inputs")
            self.assertIn("english.wav", evidence["error"])


if __name__ == "__main__":
    unittest.main()
