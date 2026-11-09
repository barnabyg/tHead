"""Saved-avatar transactions at the public storage boundary."""

import base64
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from avatars import AvatarStore  # noqa: E402


class AvatarStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.store = AvatarStore(self.directory)
        self.image = (ROOT / "tests/fixtures/portrait.jpg").read_bytes()
        self.encoded = base64.b64encode(self.image).decode("ascii")
        self.avatar = self.store.create("Saved", "zira", self.encoded)

    def test_update_preserves_identity_and_other_records_after_reopen(self) -> None:
        other = self.store.create("Other", "zira", self.encoded)
        updated = self.store.update(self.avatar.id, "Renamed", "hazel")
        reopened = AvatarStore(self.directory)
        self.assertEqual(updated.id, self.avatar.id)
        self.assertEqual(reopened.get(updated.id).voice, "hazel")
        self.assertEqual(reopened.get(updated.id).name, "Renamed")
        self.assertEqual(reopened.portrait(updated.id), self.image)
        reopened.delete(updated.id, "Renamed")
        with self.assertRaises(ValueError):
            AvatarStore(self.directory).get(updated.id)
        self.assertEqual(reopened.portrait(other.id), self.image)

    def test_relative_user_data_stays_anchored_when_working_directory_changes(self) -> None:
        previous = Path.cwd()
        try:
            os.chdir(self.directory)
            store = AvatarStore(Path("relative-avatars"))
            avatar = store.create("Anchored", "zira", self.encoded)
            os.chdir(ROOT)
            self.assertEqual(store.get(avatar.id).name, "Anchored")
            self.assertEqual(store.portrait(avatar.id), self.image)
            self.assertEqual(store.update(avatar.id, "Still anchored", "hazel").voice, "hazel")
        finally:
            os.chdir(previous)

    def test_failed_update_and_delete_preserve_previous_valid_record(self) -> None:
        # A real database failure after UPDATE begins proves transaction rollback.
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_update AFTER UPDATE ON avatars "
                "BEGIN SELECT RAISE(ABORT, 'fixture disk failure'); END"
            )
            connection.execute(
                "CREATE TRIGGER reject_delete AFTER DELETE ON avatars "
                "BEGIN SELECT RAISE(ABORT, 'fixture disk failure'); END"
            )
        with self.assertRaisesRegex(ValueError, "storage unavailable"):
            self.store.update(self.avatar.id, "Changed", "hazel", self.encoded)
        with self.assertRaisesRegex(ValueError, "storage unavailable"):
            self.store.delete(self.avatar.id, "Saved")
        reopened = AvatarStore(self.directory)
        self.assertEqual(reopened.get(self.avatar.id), self.avatar)
        self.assertEqual(reopened.portrait(self.avatar.id), self.image)

    def test_validation_and_built_in_protection(self) -> None:
        for name, voice, image in (
            ("", "zira", None),
            ("JFK", "zira", None),
            ("Saved", "unknown", None),
            ("Saved", "zira", "broken"),
        ):
            with self.assertRaises(ValueError):
                self.store.update(self.avatar.id, name, voice, image)
        for identity in ("jfk-zira", "hopper-hazel"):
            with self.assertRaisesRegex(ValueError, "Built-in"):
                self.store.update(identity, "Changed", "hazel", self.encoded)
            with self.assertRaisesRegex(ValueError, "Built-in"):
                self.store.delete(identity, self.store.get(identity).name)
        with self.assertRaisesRegex(ValueError, "confirm deletion again"):
            self.store.delete(self.avatar.id, "wrong name")
        self.assertEqual(self.store.get(self.avatar.id), self.avatar)
        self.assertEqual(self.store.portrait(self.avatar.id), self.image)
