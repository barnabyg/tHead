"""Public optional-runtime preparation guards; no network, models or GPU required."""

from __future__ import annotations

import json
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

# B404/B603/B607: bounded fixed PowerShell preparation command only; review if
# the executable or script selection becomes externally controlled.

ROOT = Path(__file__).resolve().parents[1]


class ChatterboxPreparationTests(unittest.TestCase):
    def test_mismatched_python_archive_is_preserved_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            lock = json.loads(
                (ROOT / "chatterbox-maintained-lock.json").read_text(encoding="utf-8")
            )
            archive = state / lock["python_distribution"]["archive"]
            archive.write_bytes(b"this is not the pinned Python distribution")
            result = subprocess.run(  # nosec B603 B607
                [
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts/prepare-chatterbox-python.ps1"),
                    "-State",
                    str(state),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python archive failed its pinned size/hash", result.stderr)
            self.assertEqual(archive.read_bytes(), b"this is not the pinned Python distribution")
            self.assertFalse((state / "python-runtime").exists())


if __name__ == "__main__":
    unittest.main()
