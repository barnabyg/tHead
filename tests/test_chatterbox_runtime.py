"""Public optional-runtime preparation guards; no network, models or GPU required."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import unittest
import venv
from pathlib import Path

# B404/B603/B607: bounded fixed PowerShell preparation command only; review if
# the executable or script selection becomes externally controlled.

ROOT = Path(__file__).resolve().parents[1]


class ChatterboxPreparationTests(unittest.TestCase):
    def test_changed_pins_cannot_reuse_the_approved_release_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            files = [
                "scripts/chatterbox_release.py",
                "chatterbox-maintained-lock.json",
                "docs/runtime/chatterbox/requirements-maintained.lock",
                "patches/chatterbox-maintained.patch",
            ]
            for name in files:
                destination = checkout / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)

            def readiness() -> dict[str, object]:
                result = subprocess.run(  # nosec B603
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        "import json,runpy,sys;api=runpy.run_path(sys.argv[1]);"
                        "print(json.dumps(api['release_readiness']()))",
                        str(checkout / "scripts/chatterbox_release.py"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                return dict(json.loads(result.stdout))

            self.assertTrue(readiness()["available"])
            with (checkout / files[2]).open("a", encoding="utf-8") as changed:
                changed.write("\n# unreviewed changed pins\n")
            self.assertFalse(readiness()["available"])
            self.assertIn("changed", str(readiness()["error"]))

    def test_empty_environment_cannot_be_recorded_as_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            environment = state / "venv"
            venv.EnvBuilder(with_pip=False).create(environment)
            python = environment / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            result = subprocess.run(  # nosec B603
                [
                    str(python),
                    "-I",
                    str(ROOT / "scripts/chatterbox_environment.py"),
                    "--state",
                    str(state),
                    "--record",
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Candidate needs strict preparation", result.stdout)
            self.assertFalse((state / "prepared-environment.json").exists())

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
