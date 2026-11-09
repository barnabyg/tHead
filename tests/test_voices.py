"""Voice import/storage behavior with real pinned local decoders and synthetic audio."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess  # nosec B404
import sys
import tempfile
import threading
import unittest
import wave
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from voices import MAX_INPUT_BYTES, VoiceStore  # noqa: E402

MEDIA = Path(
    os.environ.get(
        "THEAD_TEST_MEDIA", str(ROOT / ".runtime/media/ffmpeg-9.0.2-essentials_build/bin")
    )
)


def recording(seconds: float = 10, rate: int = 16000, channels: int = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x08" * int(seconds * rate) * channels)
    return output.getvalue()


class VoiceStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.store = VoiceStore(self.directory, MEDIA)
        self.addCleanup(self.store.close)

    def test_crashed_owner_is_reaped_without_cancelling_a_live_import(self) -> None:
        live = self.store.import_audio("Live import", "valid.wav", recording(), True)
        live_reference = self.store.reference(live["id"])
        source = self.directory / "crash-fixture.wav"
        source.write_bytes(recording())
        code = (
            "import os,sys; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); from voices import VoiceStore; "
            "store=VoiceStore(Path(sys.argv[2]),Path(sys.argv[3])); "
            "raw=Path(sys.argv[4]).read_bytes(); "
            "[store.import_audio('Abandoned '+str(n),'fixture.wav',raw,True) for n in range(3)]; "
            "os._exit(0)"
        )
        # The separate process dies without calling close: the OS must release its lease.
        subprocess.run(  # nosec B603
            [
                sys.executable,
                "-I",
                "-c",
                code,
                str(ROOT / "scripts"),
                str(self.directory),
                str(MEDIA),
                str(source),
            ],
            check=True,
            timeout=180,
        )
        reopened = VoiceStore(self.directory, MEDIA)
        try:
            replacement = reopened.import_audio("After crash", "valid.wav", recording(), True)
            self.assertTrue(replacement["available"])
            self.assertEqual(self.store.reference(live["id"]), live_reference)
            self.assertTrue(self.store.candidate(live["id"])["available"])
        finally:
            reopened.close()

    def test_relative_user_data_stays_anchored_when_working_directory_changes(self) -> None:
        previous = Path.cwd()
        store: VoiceStore | None = None
        try:
            os.chdir(self.directory)
            store = VoiceStore(Path("relative-voices"), MEDIA)
            imported = store.import_audio("Anchored", "valid.wav", recording(), True)
            store.mark_previewed(imported["id"], imported["sha256"])
            saved = store.save(imported["id"])
            reference = store.reference(saved["id"])
            os.chdir(ROOT)
            self.assertEqual(store.reference(saved["id"]), reference)
            self.assertEqual(store.list()[0]["id"], saved["id"])
            self.assertEqual(store.rename(saved["id"], "Still anchored")["name"], "Still anchored")
        finally:
            if store is not None:
                store.close()
            os.chdir(previous)

    def test_catalogue_failure_isolated_and_missing_database_is_not_recreated(self) -> None:
        imported = self.store.import_audio("Preserved", "valid.wav", recording(), True)
        self.store.mark_previewed(imported["id"], imported["sha256"])
        saved = self.store.save(imported["id"])
        self.store.close()
        original = self.directory / "avatars.sqlite3"
        backup = self.directory / "preserved.sqlite3"
        original.replace(backup)
        try:
            self.assertEqual(self.store.list(), [])
            self.assertIn("preserve", self.store.error.lower())
            self.assertFalse(original.exists())
        finally:
            original.unlink(missing_ok=True)
            backup.replace(original)
        reopened = VoiceStore(self.directory, MEDIA)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.list()[0]["id"], saved["id"])
        self.assertTrue(reopened.read(saved["id"])["available"])
        preserved = original.read_bytes()
        try:
            original.write_bytes(b"corrupt database fixture")
            self.assertEqual(reopened.list(), [])
            self.assertIn("restore", reopened.error.lower())
            self.assertEqual(original.read_bytes(), b"corrupt database fixture")
        finally:
            original.write_bytes(preserved)

    def test_close_after_known_storage_failure_releases_pending_session(self) -> None:
        imported = self.store.import_audio("Pending", "valid.wav", recording(), True)
        original = self.directory / "avatars.sqlite3"
        preserved = original.read_bytes()
        try:
            original.write_bytes(b"late storage failure fixture")
            self.assertEqual(self.store.list(), [])
            self.assertTrue(self.store.error)
            self.store.close()
        finally:
            original.write_bytes(preserved)
        reopened = VoiceStore(self.directory, MEDIA)
        self.addCleanup(reopened.close)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            reopened.candidate(imported["id"])
        replacement = reopened.import_audio("After repair", "valid.wav", recording(), True)
        self.assertTrue(replacement["available"])

    def test_source_removal_restart_rename_and_idempotent_save(self) -> None:
        source = self.directory / "original.wav"
        source.write_bytes(recording())
        imported = self.store.import_audio(
            "Personal reference", "../../untrusted/source.wav", source.read_bytes(), True
        )
        source.unlink()
        self.assertEqual(self.store.list(), [])
        with self.assertRaisesRegex(ValueError, "Preview"):
            self.store.save(imported["id"])
        canonical = self.store.reference(imported["id"])
        with wave.open(io.BytesIO(canonical), "rb") as audio:
            self.assertEqual(
                (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()), (1, 24000, 2)
            )
            self.assertEqual(audio.getnframes(), 240000)
        self.store.mark_previewed(imported["id"], imported["sha256"])
        saved = self.store.save(imported["id"])
        self.assertEqual(self.store.save(imported["id"]), saved)
        reopened = VoiceStore(self.directory, MEDIA)
        self.addCleanup(reopened.close)
        renamed = reopened.rename(saved["id"], "Renamed")
        self.assertEqual(renamed["id"], saved["id"])
        self.assertEqual(reopened.reference(saved["id"]), canonical)
        self.assertTrue(reopened.read(saved["id"])["available"])
        reopened.delete(saved["id"], "Renamed")
        self.assertEqual(reopened.list(), [])

    def test_supported_formats_are_decoded_and_mislabelled_audio_rejected(self) -> None:
        source = self.directory / "fixture.wav"
        source.write_bytes(recording())
        for extension, codec in (("mp3", "libmp3lame"), ("m4a", "aac")):
            target = self.directory / ("fixture." + extension)
            # Fixed local fixture encoder; no shell or private input is involved.
            subprocess.run(  # nosec B603
                [
                    str(MEDIA / "ffmpeg.exe"),
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-c:a",
                    codec,
                    "-y",
                    str(target),
                ],
                check=True,
                timeout=180,
            )
            with self.subTest(extension=extension):
                imported = self.store.import_audio(
                    extension, target.name, target.read_bytes(), True
                )
                self.assertAlmostEqual(imported["duration"], 10, delta=0.1)
                self.assertEqual(imported["sample_rate"], 24000)
                self.store.cancel(imported["id"])
                with self.assertRaisesRegex(ValueError, "do not match"):
                    self.store.import_audio(
                        "Wrong extension", "pretend.wav", target.read_bytes(), True
                    )

    def test_corrupt_excessive_and_invalid_recordings_never_save(self) -> None:
        cases = (
            ("corrupt.wav", b"RIFFbroken", "corrupt"),
            ("short.wav", recording(5), "longer than 5"),
            ("long.wav", recording(30.1), "30 seconds"),
            ("channels.wav", recording(channels=3), "one or two"),
            ("rate.wav", recording(rate=4000), "8 and 96"),
            ("file.ogg", recording(), "WAV, MP3 or M4A"),
            ("huge.wav", b"x" * (MAX_INPUT_BYTES + 1), "20 MiB"),
        )
        for filename, raw, message in cases:
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, message):
                self.store.import_audio("Invalid", filename, raw, True)
        for name in ("", " " * 5, "x" * 81, "ZIRA", "Hazel", "line\nname"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.import_audio(name, "valid.wav", recording(), True)
        with self.assertRaisesRegex(ValueError, "permission"):
            self.store.import_audio("Reference", "valid.wav", recording(), False)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(list((self.directory / "voice-imports").glob("import-*")), [])

    def test_cancel_and_bounded_pending_imports(self) -> None:
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            self.store.import_audio("Cancelled", "valid.wav", recording(), True, cancelled)
        pending = [
            self.store.import_audio(str(number), "valid.wav", recording(), True)
            for number in range(4)
        ]
        with self.assertRaisesRegex(ValueError, "Finish or cancel"):
            self.store.import_audio("Fifth", "valid.wav", recording(), True)
        self.store.cancel(pending[0]["id"])
        with self.assertRaisesRegex(ValueError, "cancelled"):
            self.store.save(pending[0]["id"])
        self.store.import_audio("Replacement", "valid.wav", recording(), True)
        for candidate in pending[1:]:
            self.store.cancel(candidate["id"])
        self.assertEqual(self.store.list(), [])

    def test_interrupted_save_rolls_back_and_can_be_retried(self) -> None:
        imported = self.store.import_audio("Reference", "valid.wav", recording(), True)
        self.store.mark_previewed(imported["id"], imported["sha256"])
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_save AFTER INSERT ON voices "
                "BEGIN SELECT RAISE(ABORT, 'simulated disk full'); END"
            )
        with self.assertRaisesRegex(ValueError, "storage unavailable"):
            self.store.save(imported["id"])
        self.assertEqual(VoiceStore(self.directory, MEDIA).list(), [])
        self.assertTrue(self.store.candidate(imported["id"])["previewed"])
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            connection.execute("DROP TRIGGER fail_save")
        self.assertTrue(self.store.save(imported["id"])["available"])

    def test_in_use_deletion_and_explicit_repair_preserve_identity(self) -> None:
        imported = self.store.import_audio("Shared voice", "valid.wav", recording(), True)
        self.store.mark_previewed(imported["id"], imported["sha256"])
        saved = self.store.save(imported["id"])
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            for identity, name in (
                ("avatar-first", "First avatar"),
                ("avatar-second", "Second avatar"),
            ):
                connection.execute(
                    "INSERT INTO avatars VALUES (?,?,?,?,?)",
                    (identity, name, name.casefold(), saved["id"], b"portrait fixture"),
                )
            connection.execute("UPDATE voices SET audio=? WHERE id=?", (b"corrupt", saved["id"]))
        reopened = VoiceStore(self.directory, MEDIA)
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.read(saved["id"])["available"])
        with self.assertRaisesRegex(ValueError, "First avatar.*Second avatar"):
            reopened.delete(saved["id"], "Shared voice")
        replacement = reopened.import_audio("Shared voice", "replacement.wav", recording(11), True)
        reopened.mark_previewed(replacement["id"], replacement["sha256"])
        repaired = reopened.repair(saved["id"], replacement["id"])
        self.assertTrue(repaired["available"])
        self.assertEqual(repaired["id"], saved["id"])
        self.assertEqual(reopened.repair(saved["id"], replacement["id"]), repaired)
        self.assertEqual(
            [use["name"] for use in reopened.usage(saved["id"])], ["First avatar", "Second avatar"]
        )
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            connection.execute("UPDATE avatars SET voice='zira'")
        reopened.delete(saved["id"], "Shared voice")
        self.assertEqual(reopened.list(), [])

    def test_temporary_name_can_be_corrected_at_atomic_save(self) -> None:
        first = self.store.import_audio("Saved", "source.wav", recording(), True)
        self.store.mark_previewed(first["id"], first["sha256"])
        saved = self.store.save(first["id"])
        second = self.store.import_audio("saved", "source.wav", recording(), True)
        self.store.mark_previewed(second["id"], second["sha256"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.store.save(second["id"])
        self.assertEqual([voice["id"] for voice in self.store.list()], [saved["id"]])
        corrected = self.store.save(second["id"], "Corrected")
        self.assertEqual(corrected["name"], "Corrected")
        self.assertNotEqual(corrected["id"], saved["id"])

    def test_corrupt_metadata_is_unavailable_without_hiding_healthy_voices(self) -> None:
        for name in ("Healthy", "Damaged"):
            imported = self.store.import_audio(name, "valid.wav", recording(), True)
            self.store.mark_previewed(imported["id"], imported["sha256"])
            saved = self.store.save(imported["id"])
        damaged_id = saved["id"]
        canonical = self.store.reference(damaged_id)
        mutations: tuple[dict[str, Any], ...] = (
            {"engine": []},
            {"duration": 5},
            {"duration": 11},
            {"sample_rate": 16000},
            {"channels": 2},
            {"permission": False},
            {"created": float("nan")},
            {"source_sha256": "changed"},
            {"id": "voice-wrong"},
            {"name": "Different"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                metadata = {**saved, **mutation}
                with (
                    closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection,
                    connection,
                ):
                    connection.execute(
                        "UPDATE voices SET metadata=?,audio=? WHERE id=?",
                        (json.dumps(metadata), canonical, damaged_id),
                    )
                catalogue = self.store.list()
                self.assertEqual(len(catalogue), 2)
                self.assertTrue(next(v for v in catalogue if v["name"] == "Healthy")["available"])
                self.assertFalse(self.store.read(damaged_id)["available"])
        metadata = {**saved, "sha256": hashlib.sha256(b"not a WAV").hexdigest()}
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            connection.execute(
                "UPDATE voices SET metadata=?,audio=? WHERE id=?",
                (json.dumps(metadata), b"not a WAV", damaged_id),
            )
        self.assertFalse(self.store.read(damaged_id)["available"])
        with closing(sqlite3.connect(self.directory / "avatars.sqlite3")) as connection, connection:
            connection.execute(
                "INSERT INTO voices VALUES (?,?,?,?,?)",
                (None, "Missing identity", "missing", "{}", b""),
            )
            connection.execute(
                "INSERT INTO voices VALUES (?,?,?,?,?)",
                (b"bad-id", b"bad-name", "binary", "{}", b""),
            )
        catalogue = self.store.list()
        self.assertEqual(len(catalogue), 4)
        self.assertIsInstance(json.dumps(catalogue), str)
        self.assertTrue(
            all(isinstance(v["id"], str) and isinstance(v["name"], str) for v in catalogue)
        )
        self.assertEqual(sum(bool(v["available"]) for v in catalogue), 1)


if __name__ == "__main__":
    unittest.main()
