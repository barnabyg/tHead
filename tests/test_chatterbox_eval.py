"""Evaluation CLI contract; no model downloads, native speech or network needed."""

import subprocess  # nosec B404
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ChatterboxCommandTests(unittest.TestCase):
    def test_invalid_wav_has_actionable_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            reference = Path(temporary) / "reference.wav"
            reference.write_bytes(b"not a wave recording")
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_eval.py"),
                    "--reference",
                    str(reference),
                    "--text",
                    "Hello.",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid reference WAV", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_missing_assets_fail_without_downloading_or_creating_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            reference = Path(temporary) / "reference.wav"
            state = Path(temporary) / "evaluation"
            with wave.open(str(reference), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\1\0" * 160000)
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_eval.py"),
                    "--reference",
                    str(reference),
                    "--text",
                    "This is new text.",
                    "--state",
                    str(state),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing pinned model asset", result.stderr)
            self.assertFalse(state.exists())

    def test_empty_text_fails_before_environment_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            reference = Path(temporary) / "reference.wav"
            with wave.open(str(reference), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\1\0" * 160000)
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_eval.py"),
                    "--reference",
                    str(reference),
                    "--text",
                    " ",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Enter 1–1200 characters", result.stderr)

    def test_reference_must_exceed_five_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            reference = Path(temporary) / "reference.wav"
            with wave.open(str(reference), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\0\0" * 80000)
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_eval.py"),
                    "--reference",
                    str(reference),
                    "--text",
                    "Hello.",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("longer than 5", result.stderr)

    def test_missing_reference_fails_before_environment_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    str(ROOT / "scripts/chatterbox_eval.py"),
                    "--reference",
                    str(Path(temporary) / "missing.wav"),
                    "--text",
                    "Hello, this is a new sentence.",
                    "--state",
                    str(Path(temporary) / "evaluation"),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Reference WAV does not exist", result.stderr)
            self.assertFalse((Path(temporary) / "evaluation").exists())


if __name__ == "__main__":
    unittest.main()
