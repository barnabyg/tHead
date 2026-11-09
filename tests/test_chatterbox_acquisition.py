"""Offline public preparation CLI recovery using immutable local acquisitions."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess  # nosec B404
import tarfile
import tempfile
import unittest
from pathlib import Path

# B404/B603/B607: bounded fixed Git/PowerShell commands against task-owned fixtures;
# review if executable selection or arguments become externally controlled.
ROOT = Path(__file__).resolve().parents[1]


def command(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        list(arguments), capture_output=True, text=True, timeout=90, check=False
    )


def git(directory: Path, *arguments: str) -> str:
    result = command("git", "-C", str(directory), *arguments)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


class SourceAcquisitionTests(unittest.TestCase):
    def test_stale_journal_does_not_claim_a_later_manual_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "prepare-chatterbox-maintained.ps1"
            shutil.copyfile(ROOT / "scripts/prepare-chatterbox-maintained.ps1", script)
            patch = root / "fixture.patch"
            patch.write_bytes(b"")
            (root / "chatterbox-maintained-lock.json").write_text(
                json.dumps(
                    {
                        "source_patch": {
                            "file": patch.name,
                            "sha256": hashlib.sha256(b"").hexdigest(),
                        }
                    }
                )
            )
            state = root / "state"
            metadata = state / "source/.git"
            metadata.mkdir(parents=True)
            journal = state / "git-acquisition.json"
            journal.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source": "source",
                        "locks": ["config.lock"],
                        "owner_pid": 2147483647,
                        "owner_started": 1,
                        "child_pid": 2147483646,
                        "child_started": 1,
                        "finished": False,
                    }
                )
            )
            recorded = journal.read_bytes()
            # A later manual Git operation can reuse the potential lock name.
            manual = metadata / "config.lock"
            manual.write_bytes(b"manual configuration created after failed acquisition\n")
            result = command(
                "pwsh", "-NoProfile", "-File", str(script), "-State", str(state), "-SourcesOnly"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Git lock ownership is ambiguous", result.stderr)
            self.assertEqual(
                manual.read_bytes(), b"manual configuration created after failed acquisition\n"
            )
            self.assertEqual(journal.read_bytes(), recorded)
            self.assertFalse((state / "git-lock-quarantine").exists())

    def test_retry_finishes_interrupted_source_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copyfile(
                ROOT / "scripts/prepare-chatterbox-maintained.ps1",
                scripts / "prepare-chatterbox-maintained.ps1",
            )
            origin = root / "origin"
            origin.mkdir()
            git(origin, "init", "--quiet")
            git(origin, "config", "user.name", "Acquisition fixture")
            git(origin, "config", "user.email", "fixture@example.invalid")
            git(origin, "config", "core.autocrlf", "false")
            (origin / "reference.txt").write_bytes(b"original\n")
            (origin / "other.txt").write_bytes(b"remaining target file\n")
            git(origin, "add", "reference.txt", "other.txt")
            git(origin, "commit", "--quiet", "-m", "fixture")
            revision = git(origin, "rev-parse", "HEAD")
            patch = root / "fixture.patch"
            patch.write_bytes(
                b"diff --git a/reference.txt b/reference.txt\n"
                b"--- a/reference.txt\n+++ b/reference.txt\n"
                b"@@ -1 +1 @@\n-original\n+maintained\n"
            )
            lock = {
                "upstream_url": str(origin),
                "upstream_revision": revision,
                "perth_url": str(origin),
                "perth_revision": revision,
                "source_patch": {
                    "file": "fixture.patch",
                    "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
                    "patched_files": [
                        {
                            "file": "reference.txt",
                            "sha256": hashlib.sha256(b"maintained\n").hexdigest(),
                        }
                    ],
                },
            }
            (root / "chatterbox-maintained-lock.json").write_text(json.dumps(lock))
            state = root / "state"
            source = state / "source"
            source.mkdir(parents=True)
            # Cancellation after git init/add-origin, before fetch/checkout.
            git(source, "init", "--quiet")
            git(source, "remote", "add", "origin", str(origin))
            result = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((source / "reference.txt").read_text(), "maintained\n")
            self.assertEqual(git(source, "rev-parse", "HEAD"), revision)
            with (state / "preparation.lease").open("r+b"):
                concurrent = command(
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    str(scripts / "prepare-chatterbox-maintained.ps1"),
                    "-State",
                    str(state),
                    "-SourcesOnly",
                )
            self.assertNotEqual(concurrent.returncode, 0)
            self.assertIn("Another local voice preparation is active", concurrent.stderr)
            git_lock = source / ".git/config.lock"
            git_lock.write_bytes(b"interrupted Git configuration")
            owner = command(
                "pwsh",
                "-NoProfile",
                "-Command",
                f"(Get-Process -Id {os.getpid()}).StartTime.ToUniversalTime().Ticks",
            )
            self.assertEqual(owner.returncode, 0, owner.stdout + owner.stderr)
            record = {
                "version": 1,
                "source": "source",
                "locks": ["config.lock"],
                "owner_pid": os.getpid(),
                "owner_started": int(owner.stdout.strip()),
                "child_pid": 2147483646,
                "child_started": 1,
                "finished": False,
            }
            (state / "git-acquisition.json").write_text(json.dumps(record))
            active = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertNotEqual(active.returncode, 0)
            self.assertIn("recorded Git acquisition is still active", active.stderr)
            self.assertEqual(git_lock.read_bytes(), b"interrupted Git configuration")
            record.update(owner_pid=2147483647, owner_started=1)
            (state / "git-acquisition.json").write_text(json.dumps(record))
            recovered = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertNotEqual(recovered.returncode, 0)
            self.assertIn("Git lock ownership is ambiguous", recovered.stderr)
            self.assertEqual(git_lock.read_bytes(), b"interrupted Git configuration")
            self.assertFalse((state / "git-lock-quarantine").exists())
            # Remove only this test's synthetic journal/lock before exercising
            # a separate unjournaled manual lock; production preserves both.
            git_lock.unlink()
            (state / "git-acquisition.json").unlink()
            git_lock.write_bytes(b"unknown manual Git configuration")
            unknown_lock = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertNotEqual(unknown_lock.returncode, 0)
            self.assertIn("Unrecognized Git lock", unknown_lock.stderr)
            self.assertEqual(git_lock.read_bytes(), b"unknown manual Git configuration")
            git_lock.unlink()
            for interrupted_at in (
                "metadata",
                "init",
                "fetch",
                "checkout",
                "checkout-index-partial",
                "checkout-modified",
                "checkout-extra",
                "checkout-index-private",
            ):
                with self.subTest(interrupted_at=interrupted_at):
                    retry_state = root / interrupted_at
                    retry_source = retry_state / "source"
                    retry_source.mkdir(parents=True)
                    if interrupted_at == "metadata":
                        (retry_source / ".git").mkdir()
                    else:
                        git(retry_source, "init", "--quiet")
                    if interrupted_at == "fetch" or interrupted_at.startswith("checkout"):
                        git(retry_source, "remote", "add", "origin", str(origin))
                        git(retry_source, "fetch", "--quiet", "origin", revision)
                    if interrupted_at.startswith("checkout"):
                        # Git materialized one exact blob before its first index/HEAD commit.
                        (retry_source / "reference.txt").write_bytes(b"original\n")
                        # Recovery must override Windows checkout conversion as well.
                        git(retry_source, "config", "core.autocrlf", "true")
                    if interrupted_at == "checkout-index-partial":
                        git(retry_source, "-c", "core.autocrlf=false", "add", "reference.txt")
                    if interrupted_at == "checkout-modified":
                        (retry_source / "reference.txt").write_bytes(b"private local bytes\n")
                    if interrupted_at == "checkout-extra":
                        (retry_source / "private.txt").write_bytes(b"unrecognized local bytes\n")
                    if interrupted_at == "checkout-index-private":
                        (retry_source / "reference.txt").write_bytes(b"private staged bytes\n")
                        git(retry_source, "-c", "core.autocrlf=false", "add", "reference.txt")
                        (retry_source / "reference.txt").write_bytes(b"original\n")
                    retry = command(
                        "pwsh",
                        "-NoProfile",
                        "-File",
                        str(scripts / "prepare-chatterbox-maintained.ps1"),
                        "-State",
                        str(retry_state),
                        "-SourcesOnly",
                    )
                    if interrupted_at in (
                        "checkout-modified",
                        "checkout-extra",
                        "checkout-index-private",
                    ):
                        self.assertNotEqual(retry.returncode, 0)
                        self.assertIn("preserve this state", retry.stderr)
                        if interrupted_at == "checkout-modified":
                            self.assertEqual(
                                (retry_source / "reference.txt").read_bytes(),
                                b"private local bytes\n",
                            )
                        elif interrupted_at == "checkout-extra":
                            self.assertEqual(
                                (retry_source / "private.txt").read_bytes(),
                                b"unrecognized local bytes\n",
                            )
                        else:
                            self.assertEqual(
                                git(retry_source, "show", ":reference.txt"), "private staged bytes"
                            )
                            self.assertEqual(
                                (retry_source / "reference.txt").read_bytes(), b"original\n"
                            )
                        self.assertFalse((retry_source / "other.txt").exists())
                        continue
                    self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
                    self.assertEqual((retry_source / "reference.txt").read_text(), "maintained\n")
                    self.assertEqual(
                        (retry_source / "other.txt").read_bytes(), b"remaining target file\n"
                    )
            (source / "reference.txt").write_bytes(b"private local modification\n")
            changed = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn("Patched source hash differs", changed.stderr)
            self.assertEqual(
                (source / "reference.txt").read_bytes(), b"private local modification\n"
            )
            git(source, "remote", "set-url", "origin", str(root / "wrong-origin"))
            changed_origin = command(
                "pwsh",
                "-NoProfile",
                "-File",
                str(scripts / "prepare-chatterbox-maintained.ps1"),
                "-State",
                str(state),
                "-SourcesOnly",
            )
            self.assertNotEqual(changed_origin.returncode, 0)
            self.assertIn("Source origin differs", changed_origin.stderr)


class PythonAcquisitionTests(unittest.TestCase):
    def test_retry_extracts_verified_archive_and_preserves_unknown_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "prepare-chatterbox-python.ps1"
            shutil.copyfile(ROOT / "scripts/prepare-chatterbox-python.ps1", script)
            state = root / "state"
            state.mkdir()
            archive = state / "python-fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                content = b"immutable fixture; never executed"
                member = tarfile.TarInfo("python/install/python.exe")
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
            (root / "chatterbox-maintained-lock.json").write_text(
                json.dumps(
                    {
                        "python": "3.12.16",
                        "python_distribution": {
                            "archive": archive.name,
                            "bytes": archive.stat().st_size,
                            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                            "relative_executable": "python-runtime/python/install/python.exe",
                        },
                    }
                )
            )
            old_stage = state / "python-runtime.staging"
            old_stage.mkdir()
            (old_stage / "preserve.txt").write_bytes(b"unknown interrupted state")
            owned_stage = state / ("python-runtime.staging-" + "a" * 32)
            owned_stage.mkdir()
            (owned_stage / ".chatterbox-acquisition").write_text(
                hashlib.sha256(archive.read_bytes()).hexdigest(), encoding="ascii"
            )
            (owned_stage / "incomplete").write_bytes(b"interrupted archive member")
            unknown_stage = state / ("python-runtime.staging-" + "b" * 32)
            unknown_stage.mkdir()
            (unknown_stage / "preserve.txt").write_bytes(b"unmarked data")
            result = command(
                "pwsh", "-NoProfile", "-File", str(script), "-State", str(state), "-ExtractOnly"
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (state / "python-runtime/python/install/python.exe").read_bytes(), content
            )
            self.assertEqual(
                (old_stage / "preserve.txt").read_bytes(), b"unknown interrupted state"
            )
            self.assertFalse(owned_stage.exists())
            self.assertEqual((unknown_stage / "preserve.txt").read_bytes(), b"unmarked data")


if __name__ == "__main__":
    unittest.main()
