"""Atomic local avatar storage. Images and metadata share one SQLite transaction."""

from __future__ import annotations

import base64
import binascii
import importlib
import io
import os
import sqlite3
import threading
import uuid
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pairs import Avatar, configured_avatars, supported_voices
from speech import Voice
from voices import VoiceStore

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 4096 * 4096
MAX_NAME = 80


def user_data_directory() -> Path:
    override = os.environ.get("THEAD_USER_DATA")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "tHead"


def voice_catalogue(test_backend: bool, selected: str = "") -> list[dict[str, Any]]:
    result = []
    for identity, lock in supported_voices().items():
        if selected and selected != identity:
            continue
        voice = Voice(lock)
        error = ""
        try:
            if not test_backend:
                voice.prepare(threading.Event())
        except (OSError, RuntimeError, ValueError, TimeoutError) as problem:
            error = str(problem)
        finally:
            voice.close()
        result.append(
            {
                "id": identity,
                "name": {
                    "zira": "Zira — English (United States)",
                    "hazel": "Hazel — English (United Kingdom)",
                }[identity],
                "available": not error,
                "error": error,
            }
        )
    return result


def decode_portrait(encoded: Any) -> bytes:
    if not isinstance(encoded, str) or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("Choose a JPEG or PNG of at most 5 MiB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Choose a valid JPEG or PNG image") from error
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a JPEG or PNG of at most 5 MiB")
    image = importlib.import_module("PIL.Image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", image.DecompressionBombWarning)
            with image.open(io.BytesIO(raw)) as picture:
                if picture.format not in ("JPEG", "PNG"):
                    raise ValueError("Choose a JPEG or PNG image")
                width, height = picture.size
                if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
                    raise ValueError("Portrait dimensions must be at most 4096 × 4096 pixels")
                if width * height > MAX_PIXELS:
                    raise ValueError("Portrait exceeds 16,777,216 decoded pixels")
                picture.load()  # Force actual decoding before accepting the upload.
                return raw
    except (
        OSError,
        SyntaxError,
        image.DecompressionBombError,
        image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Image is corrupt or oversized; choose a valid JPEG or PNG") from error


class AvatarStore:
    def __init__(self, directory: Path, voices: VoiceStore | None = None) -> None:
        directory = directory.resolve()
        self.path = directory / "avatars.sqlite3"
        self.voices = voices
        self.error = ""
        self.record_error = ""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS avatars (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
                    voice TEXT NOT NULL, portrait BLOB NOT NULL)""")
        except (sqlite3.Error, OSError) as error:
            self.error = self.recovery(error)

    def recovery(self, error: Exception) -> str:
        return (
            f"Avatar storage unavailable ({error}). Preserve {self.path}, restore a backup "
            "or move the damaged database aside and restart. Built-in avatars remain available."
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def avatars(self) -> dict[str, Avatar]:
        result = configured_avatars()
        if self.error:
            return result
        try:
            with self.connect() as connection:
                for identity, name, voice in connection.execute(
                    "SELECT id, name, voice FROM avatars"
                ):
                    if (
                        not isinstance(identity, str)
                        or not identity.startswith("avatar-")
                        or not isinstance(name, str)
                        or not name.strip()
                        or not isinstance(voice, str)
                        or (voice not in supported_voices() and not voice.startswith("voice-"))
                    ):
                        self.record_error = (
                            "Invalid saved avatar record; restore avatar storage from backup"
                        )
                        continue
                    result[identity] = Avatar(identity, name, {"stored": True}, voice)
        except sqlite3.Error as error:
            self.error = self.recovery(error)
        return result

    def get(self, identity: str) -> Avatar:
        avatar = self.avatars().get(identity)
        if avatar is None:
            raise ValueError("Unknown avatar; select an available avatar")
        return avatar

    def portrait(self, identity: str) -> bytes:
        if self.error:
            raise ValueError(self.error)
        try:
            with self.connect() as connection:
                row = connection.execute(
                    "SELECT portrait FROM avatars WHERE id = ?", (identity,)
                ).fetchone()
                if not row or not isinstance(row[0], bytes):
                    raise ValueError(
                        "Saved portrait unavailable; restore avatar storage from backup"
                    )
                return row[0]
        except sqlite3.Error as error:
            raise ValueError(self.recovery(error)) from error

    def create(self, name: Any, voice: Any, encoded: Any) -> Avatar:
        return self.save(name, voice, encoded)

    def update(self, identity: str, name: Any, voice: Any, encoded: Any = None) -> Avatar:
        self.require_user_avatar(identity)
        return self.save(name, voice, encoded, identity)

    def require_user_avatar(self, identity: str) -> Avatar:
        if identity in configured_avatars():
            raise ValueError("Built-in avatars cannot be edited or deleted")
        return self.get(identity)

    def save(self, name: Any, voice: Any, encoded: Any, identity: str = "") -> Avatar:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
            raise ValueError("Enter an Avatar name of 1–80 characters")
        name = name.strip()
        if not isinstance(voice, str) or (
            voice not in supported_voices()
            and (self.voices is None or not self.voices.read(voice)["available"])
        ):
            raise ValueError("Choose an available supported local English voice")
        if any(a.name.casefold() == name.casefold() for a in configured_avatars().values()):
            raise ValueError("An avatar with this name already exists; choose another name")
        portrait = decode_portrait(encoded) if encoded is not None or not identity else None
        if self.error:
            raise ValueError(self.error)
        updating = bool(identity)
        identity = identity or "avatar-" + uuid.uuid4().hex
        try:
            with self.connect() as connection:
                if updating:
                    cursor = connection.execute(
                        "UPDATE avatars SET name=?, name_key=?, voice=?, "
                        "portrait=COALESCE(?, portrait) WHERE id=?",
                        (name, name.casefold(), voice, portrait, identity),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("Unknown avatar; reload Settings")
                else:
                    connection.execute(
                        "INSERT INTO avatars VALUES (?, ?, ?, ?, ?)",
                        (identity, name, name.casefold(), voice, portrait),
                    )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed: avatars.name_key" in str(error):
                raise ValueError(
                    "An avatar with this name already exists; choose another name"
                ) from error
            raise ValueError(self.recovery(error)) from error
        except sqlite3.Error as error:
            raise ValueError(self.recovery(error)) from error
        return Avatar(identity, name, {"stored": True}, voice)

    def delete(self, identity: str, name: Any) -> None:
        avatar = self.require_user_avatar(identity)
        if name != avatar.name:
            raise ValueError("Avatar name changed; reload and confirm deletion again")
        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM avatars WHERE id=? AND name=?", (identity, name)
                )
                if cursor.rowcount != 1:
                    raise ValueError("Avatar changed; reload Settings")
        except sqlite3.Error as error:
            raise ValueError(self.recovery(error)) from error
