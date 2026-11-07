"""Exercise the documented command without substitutes for the model."""

import json

# Fixed shell-free CLI test; review B404 if commands become external.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SmokeCommandTests(unittest.TestCase):
    def test_missing_models_reports_failure_and_never_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.json"
            # Only this interpreter and the repository's smoke script can be executed.
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/smoke.py"),
                    "--models",
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
            self.assertNotIn("READY", result.stdout)
            evidence = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "blocked")
            self.assertEqual(evidence["stage"], "model-files")
            self.assertIn("Model_Lite", evidence["error"])


if __name__ == "__main__":
    unittest.main()
