"""No-cost quality-pack command boundary; native synthesis is evaluated separately."""

# B404/B603: fixed interpreter and checked-in CLI; review if commands become external.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QualityPackCommandTests(unittest.TestCase):
    def test_missing_model_fails_before_creating_a_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "pack"
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_quality.py"),
                    "--pack",
                    str(pack),
                    "--state",
                    str(Path(temporary) / "state"),
                    "--generate",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing pinned model asset", result.stderr)
            self.assertFalse(pack.exists())

    def test_generate_never_overwrites_an_existing_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            sentinel = pack / "keep.txt"
            sentinel.write_text("existing listening evidence", encoding="utf-8")
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_quality.py"),
                    "--pack",
                    str(pack),
                    "--generate",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Choose a new pack directory", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing listening evidence")

    def test_open_missing_pack_fails_without_creating_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "missing"
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_quality.py"),
                    "--pack",
                    str(pack),
                    "--open",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Listening pack is missing", result.stderr)
            self.assertFalse(pack.exists())


if __name__ == "__main__":
    unittest.main()
