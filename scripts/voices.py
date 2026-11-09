"""Private, atomic reference-audio library; never accepts server paths or URLs."""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess  # nosec B404
import tempfile
import threading
import time
import uuid
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from prepare import ROOT, RUNTIME

MAX_UPLOAD = 20 * 1024 * 1024
MAX_INPUT_BYTES = MAX_UPLOAD
MAX_SECONDS = 30
SAMPLE_RATE = 24000
MAX_SAMPLES = SAMPLE_RATE * MAX_SECONDS
DECODE_TIMEOUT = 180
IMPORT_LIFETIME = 3600
MAX_CANDIDATES = 4
ENGINE = "chatterbox-nano"
BUILTIN_NAMES = {
    "zira",
    "hazel",
    "zira — english (united states)",
    "hazel — english (united kingdom)",
}


def validated_name(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
        raise ValueError("Enter a Voice name of 1–80 characters")
    name = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("Voice names cannot contain control characters")
    if name.casefold() in BUILTIN_NAMES:
        raise ValueError("A voice with this name already exists; choose another name")
    return name


def check_cancelled(cancelled: threading.Event | None) -> None:
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError("Voice import cancelled")


def lock_lease(stream: BinaryIO) -> None:
    stream.seek(0)
    if os.name == "nt":
        locking = importlib.import_module("msvcrt")
        locking.locking(stream.fileno(), locking.LK_NBLCK, 1)
    else:
        locking = importlib.import_module("fcntl")
        locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)


def record_metadata(identity: str, name: Any, encoded: Any) -> dict[str, Any]:
    error = "Voice metadata is corrupt or unsupported; repair this voice or restore a backup"
    try:
        metadata = json.loads(encoded)
        if (
            not re.fullmatch(r"(?:voice|import)-[a-f0-9]{32}", identity)
            or not isinstance(metadata, dict)
            or validated_name(name) != name
            or metadata.get("id") != identity
            or metadata.get("name") != name
            or metadata.get("engine") != ENGINE
            or metadata.get("permission") != "owner-or-authorised"
            or type(metadata.get("sample_rate")) is not int
            or metadata["sample_rate"] != SAMPLE_RATE
            or type(metadata.get("channels")) is not int
            or metadata["channels"] != 1
        ):
            raise ValueError(error)
        for key in ("sha256", "source_sha256"):
            if not isinstance(metadata.get(key), str) or not re.fullmatch(
                r"[a-f0-9]{64}", metadata[key]
            ):
                raise ValueError(error)
        for key in ("duration", "created"):
            number = metadata.get(key)
            if (
                isinstance(number, bool)
                or not isinstance(number, (float, int))
                or not math.isfinite(number)
                or number <= 0
            ):
                raise ValueError(error)
        if not 5 < metadata["duration"] <= MAX_SECONDS:
            raise ValueError(error)
        # Expose the supported schema only, preserving all original bytes in storage.
        return {
            key: metadata[key]
            for key in (
                "id",
                "name",
                "engine",
                "permission",
                "sha256",
                "source_sha256",
                "sample_rate",
                "channels",
                "duration",
                "created",
            )
        }
    except (ValueError, TypeError, KeyError, OverflowError) as problem:
        raise ValueError(error) from problem


def validated_reference(metadata: dict[str, Any], audio: Any) -> bytes:
    error = "Voice reference changed or corrupt; repair this voice"
    if (
        not isinstance(audio, bytes)
        or not 44 < len(audio) <= MAX_SAMPLES * 2 + 44
        or hashlib.sha256(audio).hexdigest() != metadata["sha256"]
    ):
        raise ValueError(error)
    try:
        with wave.open(io.BytesIO(audio), "rb") as reference:
            samples = reference.getnframes()
            if (
                (
                    reference.getnchannels(),
                    reference.getframerate(),
                    reference.getsampwidth(),
                    reference.getcomptype(),
                )
                != (1, SAMPLE_RATE, 2, "NONE")
                or not 5 * SAMPLE_RATE < samples <= MAX_SAMPLES
                or abs(samples / SAMPLE_RATE - metadata["duration"]) > 1 / SAMPLE_RATE
                or len(reference.readframes(MAX_SAMPLES + 1)) != samples * 2
                or len(audio) != samples * 2 + 44
            ):
                raise ValueError(error)
    except (wave.Error, EOFError) as problem:
        raise ValueError(error) from problem
    return audio


class AudioDecoder:
    """Pinned local FFmpeg, restricted to file/pipe protocols and finite work."""

    def __init__(self, directory: Path | None = None) -> None:
        lock = json.loads((ROOT / "voice-media-lock.json").read_text(encoding="utf-8"))
        self.directory = (directory or RUNTIME / "media" / lock["directory"] / "bin").resolve()
        self.hashes: dict[str, str] = lock["executables"]
        self.verified: dict[str, tuple[int, int]] = {}

    def executable(self, name: str) -> Path:
        path = self.directory / name
        if not path.is_file():
            raise ValueError("Local audio tools unavailable; prepare the pinned FFmpeg tools")
        stat = path.stat()
        fingerprint = (stat.st_size, stat.st_mtime_ns)
        if self.verified.get(name) != fingerprint:
            if hashlib.sha256(path.read_bytes()).hexdigest() != self.hashes[name]:
                raise ValueError("Local audio tool hash changed; restore the pinned FFmpeg tools")
            self.verified[name] = fingerprint
        return path

    def run(self, command: list[str], directory: Path, cancelled: threading.Event | None) -> bytes:
        # Only hash-verified local executables and generated private paths are used.
        # B603: no shell, user paths, URLs or externally supplied command options.
        output = directory / "tool-output"
        diagnostics = directory / "tool-error"
        with output.open("wb") as stdout, diagnostics.open("wb") as stderr:
            with subprocess.Popen(command, stdout=stdout, stderr=stderr) as process:  # nosec B603
                deadline = time.monotonic() + DECODE_TIMEOUT
                try:
                    while process.poll() is None:
                        check_cancelled(cancelled)
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Audio decoding exceeded three minutes; try a new file"
                            )
                        if output.stat().st_size > 65536 or diagnostics.stat().st_size > 65536:
                            raise ValueError("Audio file produced excessive decoder diagnostics")
                        if cancelled is None:
                            time.sleep(0.05)
                        else:
                            cancelled.wait(0.05)
                    check_cancelled(cancelled)
                    if process.returncode:
                        raise ValueError(
                            "Audio is corrupt or unsupported; choose a valid WAV, MP3 or M4A"
                        )
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=30)
        if output.stat().st_size > 65536:
            raise ValueError("Audio metadata exceeded its limit")
        return output.read_bytes()

    def decode(
        self, raw: bytes, filename: str, directory: Path, cancelled: threading.Event | None
    ) -> bytes:
        extension = Path(filename.replace("\\", "/")).suffix.lower()
        if extension not in (".wav", ".mp3", ".m4a"):
            raise ValueError("Choose one WAV, MP3 or M4A recording")
        source = directory / "source"
        destination = directory / "reference.wav"
        source.write_bytes(raw)
        probe = self.run(
            [
                str(self.executable("ffprobe.exe")),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(source),
            ],
            directory,
            cancelled,
        )
        try:
            data = json.loads(probe)
            streams = data["streams"]
            if len(streams) != 1 or streams[0]["codec_type"] != "audio":
                raise ValueError("Choose a recording containing one audio stream and no video")
            stream = streams[0]
            formats = set(data["format"]["format_name"].split(","))
            expected = {".wav": {"wav"}, ".mp3": {"mp3"}, ".m4a": {"mov", "mp4", "m4a"}}
            if not formats.intersection(expected[extension]):
                raise ValueError("The file contents do not match its WAV, MP3 or M4A extension")
            if extension == ".m4a" and stream["codec_name"] not in ("aac", "alac"):
                raise ValueError("M4A recordings must contain AAC or Apple Lossless audio")
            if not 1 <= int(stream["channels"]) <= 2:
                raise ValueError("Recording must have one or two audio channels")
            if not 8000 <= int(stream["sample_rate"]) <= 96000:
                raise ValueError("Recording sample rate must be between 8 and 96 kHz")
            duration = float(data["format"].get("duration", stream.get("duration", 0)))
            if not 5 < duration <= 30.1:
                raise ValueError("Recording must be longer than 5 seconds and at most 30 seconds")
        except (KeyError, TypeError, OverflowError, json.JSONDecodeError) as error:
            raise ValueError(
                "Cannot read audio metadata; choose a valid WAV, MP3 or M4A"
            ) from error
        self.run(
            [
                str(self.executable("ffmpeg.exe")),
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-t",
                "30.01",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                "-y",
                str(destination),
            ],
            directory,
            cancelled,
        )
        if not destination.is_file() or destination.stat().st_size > MAX_SAMPLES * 2 + 4096:
            raise ValueError("Decoded recording exceeds the 30 second sample limit")
        try:
            with wave.open(str(destination), "rb") as audio:
                if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()) != (
                    1,
                    SAMPLE_RATE,
                    2,
                ):
                    raise ValueError("Audio decoder returned an unsupported recording")
                samples = audio.getnframes()
                if not 5 * SAMPLE_RATE < samples <= MAX_SAMPLES:
                    raise ValueError(
                        "Recording must be longer than 5 seconds and at most 30 seconds"
                    )
                pcm = audio.readframes(MAX_SAMPLES + 1)
                if len(pcm) != samples * 2:
                    raise ValueError("Decoded recording is incomplete")
        except (wave.Error, EOFError) as error:
            raise ValueError("Audio decoding failed; choose a different recording") from error
        canonical = io.BytesIO()
        with wave.open(canonical, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(SAMPLE_RATE)
            target.writeframes(pcm)
        return canonical.getvalue()


class VoiceStore:
    def __init__(self, directory: Path, media_directory: Path | None = None) -> None:
        directory = directory.resolve()
        self.directory = directory
        self.path = directory / "avatars.sqlite3"
        self.decoder = AudioDecoder(media_directory)
        self.temporary = directory / "voice-imports"
        self.owner = uuid.uuid4().hex
        self.lease: BinaryIO | None = None
        self.guard = threading.RLock()
        self.closed = False
        self.error = ""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.cleanup_temporary()
            self.initialize()
        except (OSError, ValueError) as error:
            self.error = (
                "Voice storage unavailable; preserve the database and restore a backup or retry. "
                f"Built-in voices remain available. ({error})"
            )

    def initialize(self) -> None:
        with self.connect(write=True, create=True) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS avatars (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
                voice TEXT NOT NULL, portrait BLOB NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS voices (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
                metadata TEXT NOT NULL, audio BLOB NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS voice_imports (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata TEXT NOT NULL,
                audio BLOB, previewed INTEGER NOT NULL DEFAULT 0,
                saved_id TEXT, expires REAL NOT NULL, owner TEXT NOT NULL DEFAULT '')""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(voice_imports)")}
            if "owner" not in columns:
                connection.execute(
                    "ALTER TABLE voice_imports ADD COLUMN owner TEXT NOT NULL DEFAULT ''"
                )
            self.prune_imports(connection)
            # Defend against concurrent avatar assignment/deletion in the shared DB.
            # Existing avatar columns and built-in voice identities remain unchanged.
            for statement in (
                """CREATE TRIGGER IF NOT EXISTS require_saved_voice_insert
                    BEFORE INSERT ON avatars WHEN NEW.voice LIKE 'voice-%'
                    AND NOT EXISTS (SELECT 1 FROM voices WHERE id=NEW.voice)
                    BEGIN SELECT RAISE(ABORT, 'Saved voice no longer exists'); END""",
                """CREATE TRIGGER IF NOT EXISTS require_saved_voice_update
                    BEFORE UPDATE OF voice ON avatars WHEN NEW.voice LIKE 'voice-%'
                    AND NOT EXISTS (SELECT 1 FROM voices WHERE id=NEW.voice)
                    BEGIN SELECT RAISE(ABORT, 'Saved voice no longer exists'); END""",
            ):
                connection.execute(statement)
            connection.execute("""CREATE TRIGGER IF NOT EXISTS protect_used_voice
                BEFORE DELETE ON voices WHEN EXISTS (SELECT 1 FROM avatars WHERE voice=OLD.id)
                BEGIN SELECT RAISE(ABORT, 'Voice is used by an avatar'); END""")

    @contextmanager
    def connect(self, *, write: bool = False, create: bool = False) -> Iterator[sqlite3.Connection]:
        if self.error:
            raise ValueError(self.error)
        connection: sqlite3.Connection | None = None
        try:
            # Only initialization may create a database. A moved/deleted database
            # must never be silently replaced by an empty file during a read.
            uri = self.path.as_uri() + ("?mode=rwc" if create else "?mode=rw")
            connection = sqlite3.connect(uri, uri=True, timeout=30)
            connection.execute("PRAGMA secure_delete=ON")
            with connection:
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                yield connection
        except sqlite3.Error as error:
            raise ValueError(
                "Voice storage unavailable; preserve the database and retry or restore a backup"
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def cleanup_temporary(self) -> None:
        # The two bounded decoder calls need at most six minutes in total.
        # A ten-minute-old generated directory cannot belong to a live import.
        for path in self.temporary.glob("import-*"):
            if (
                not path.is_symlink()
                and path.is_dir()
                and path.resolve().parent == self.temporary.resolve()
                and path.stat().st_mtime < time.time() - 600
            ):
                shutil.rmtree(path)

    def ensure_owner(self) -> None:
        if self.closed:
            raise ValueError("Voice library is closed; restart the application")
        if self.lease is not None:
            return
        directory = self.temporary / "leases"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (self.owner + ".lock")
        stream = path.open("x+b")
        try:
            stream.write(b"0")
            stream.flush()
            lock_lease(stream)
        except BaseException:
            stream.close()
            path.unlink(missing_ok=True)
            raise
        self.lease = stream

    def prune_imports(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM voice_imports WHERE expires < ?", (time.time(),))
        # Ownerless candidates predate leases and cannot belong to a current session.
        # Preserve saved receipts and every released saved voice record.
        connection.execute("DELETE FROM voice_imports WHERE owner='' AND saved_id IS NULL")
        owners = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT owner FROM voice_imports WHERE saved_id IS NULL"
            )
        }
        owners.update(path.stem for path in (self.temporary / "leases").glob("*.lock"))
        for owner in owners:
            if owner == self.owner:
                continue
            if (
                not isinstance(owner, str)
                or len(owner) != 32
                or any(c not in "0123456789abcdef" for c in owner)
            ):
                connection.execute(
                    "DELETE FROM voice_imports WHERE owner=? AND saved_id IS NULL", (owner,)
                )
                continue
            path = self.temporary / "leases" / (owner + ".lock")
            stream: BinaryIO | None = None
            try:
                try:
                    stream = path.open("r+b")
                    lock_lease(stream)
                except FileNotFoundError:
                    pass
                except OSError:
                    # A held OS lock proves another session is alive. Unknown I/O
                    # failures are conservative: never delete another live import.
                    continue
                connection.execute(
                    "DELETE FROM voice_imports WHERE owner=? AND saved_id IS NULL", (owner,)
                )
                for temporary in self.temporary.glob("import-" + owner + "-*"):
                    if (
                        not temporary.is_symlink()
                        and temporary.is_dir()
                        and temporary.resolve().parent == self.temporary.resolve()
                    ):
                        shutil.rmtree(temporary)
            finally:
                if stream is not None:
                    stream.close()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # Another cleaner may have opened the released lease; retry next time.

    def close(self) -> None:
        with self.guard:
            self.closed = True
            stream, self.lease = self.lease, None
            if stream is None:
                return
            try:
                with self.connect(write=True) as connection:
                    connection.execute(
                        "DELETE FROM voice_imports WHERE owner=? AND saved_id IS NULL",
                        (self.owner,),
                    )
            finally:
                stream.close()
                try:
                    (self.temporary / "leases" / (self.owner + ".lock")).unlink(missing_ok=True)
                except OSError:
                    pass  # A concurrent cleaner may still hold the file; reap it next startup.

    def import_audio(
        self,
        name: Any,
        filename: Any,
        raw: bytes,
        permission: Any,
        cancelled: threading.Event | None = None,
    ) -> dict[str, Any]:
        name = validated_name(name)
        if permission is not True:
            raise ValueError("Confirm that you own or have permission to use this recording")
        if not isinstance(filename, str) or len(filename) > 1024:
            raise ValueError("Choose one WAV, MP3 or M4A recording")
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_UPLOAD:
            raise ValueError("Choose a recording of at most 20 MiB")
        check_cancelled(cancelled)
        self.cleanup_temporary()
        identity = "import-" + uuid.uuid4().hex
        with self.guard, self.connect(write=True) as connection:
            self.ensure_owner()
            self.prune_imports(connection)
            count = connection.execute(
                "SELECT COUNT(*) FROM voice_imports WHERE saved_id IS NULL"
            ).fetchone()[0]
            if count >= MAX_CANDIDATES:
                raise ValueError("Finish or cancel another voice import before starting a new one")
            connection.execute(
                "INSERT INTO voice_imports (id,name,metadata,expires,owner) VALUES (?,?,?,?,?)",
                (identity, name, "{}", time.time() + IMPORT_LIFETIME, self.owner),
            )
        try:
            self.temporary.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="import-" + self.owner + "-", dir=self.temporary
            ) as temporary:
                audio = self.decoder.decode(raw, filename, Path(temporary), cancelled)
            check_cancelled(cancelled)
        except BaseException:
            self.cancel(identity)
            raise
        with wave.open(io.BytesIO(audio), "rb") as reference:
            duration = reference.getnframes() / SAMPLE_RATE
        metadata = {
            "id": identity,
            "name": name,
            "engine": ENGINE,
            "sha256": hashlib.sha256(audio).hexdigest(),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "duration": duration,
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "permission": "owner-or-authorised",
            "created": time.time(),
        }
        try:
            with self.guard, self.connect(write=True) as connection:
                if self.closed:
                    raise InterruptedError("Voice library closed during import")
                check_cancelled(cancelled)
                connection.execute(
                    "UPDATE voice_imports SET metadata=?,audio=? WHERE id=?",
                    (json.dumps(metadata), audio, identity),
                )
        except BaseException:
            self.cancel(identity)
            raise
        return {**metadata, "available": True, "error": "", "previewed": False}

    def candidate(self, identity: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT metadata,previewed,saved_id,name FROM voice_imports "
                "WHERE id=? AND expires>=?",
                (identity, time.time()),
            ).fetchone()
        if not row:
            raise ValueError("Voice import expired or cancelled; choose the recording again")
        if row[2]:
            return self.read(str(row[2]))
        metadata = record_metadata(identity, row[3], row[0])
        return {**metadata, "previewed": bool(row[1]), "available": True, "error": ""}

    def reference(self, identity: str) -> bytes:
        if not isinstance(identity, str):
            raise ValueError("Voice identity is corrupt; restore the voice database from a backup")
        with self.connect() as connection:
            if identity.startswith("import-"):
                row = connection.execute(
                    "SELECT metadata,audio,name FROM voice_imports "
                    "WHERE id=? AND expires>=? AND saved_id IS NULL",
                    (identity, time.time()),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT metadata,audio,name FROM voices WHERE id=?", (identity,)
                ).fetchone()
        if not row or not isinstance(row[1], bytes):
            raise ValueError(
                "Voice reference unavailable; choose the recording again or repair this voice"
            )
        return validated_reference(record_metadata(identity, row[2], row[0]), row[1])

    def mark_previewed(self, identity: str, sha256: str) -> dict[str, Any]:
        self.reference(identity)
        candidate = self.candidate(identity)
        if candidate["sha256"] != sha256:
            raise ValueError("Recording changed; preview the current recording before saving")
        with self.connect(write=True) as connection:
            cursor = connection.execute(
                "UPDATE voice_imports SET previewed=1 "
                "WHERE id=? AND saved_id IS NULL AND expires>=?",
                (identity, time.time()),
            )
            if cursor.rowcount != 1:
                raise ValueError("Voice import expired or cancelled; choose the recording again")
        return self.candidate(identity)

    def save(self, identity: str, name: Any = None) -> dict[str, Any]:
        with self.connect(write=True) as connection:
            row = connection.execute(
                "SELECT metadata,audio,previewed,saved_id,name FROM voice_imports "
                "WHERE id=? AND expires>=?",
                (identity, time.time()),
            ).fetchone()
            if not row:
                raise ValueError("Voice import expired or cancelled; choose the recording again")
            if row[3]:
                saved_id = str(row[3])
            else:
                if not row[2]:
                    raise ValueError("Preview the synthetic voice before saving")
                metadata = record_metadata(identity, row[4], row[0])
                name = validated_name(metadata["name"] if name is None else name)
                if connection.execute(
                    "SELECT 1 FROM voices WHERE name_key=?", (name.casefold(),)
                ).fetchone():
                    raise ValueError("A voice with this name already exists; choose another name")
                saved_id = "voice-" + uuid.uuid4().hex
                metadata["id"] = saved_id
                metadata["name"] = name
                validated_reference(metadata, row[1])
                connection.execute(
                    "INSERT INTO voices VALUES (?,?,?,?,?)",
                    (saved_id, name, name.casefold(), json.dumps(metadata), row[1]),
                )
                connection.execute(
                    "UPDATE voice_imports SET saved_id=?,audio=NULL WHERE id=?",
                    (saved_id, identity),
                )
        return self.read(saved_id)

    def cancel(self, identity: str) -> None:
        with self.connect(write=True) as connection:
            connection.execute("DELETE FROM voice_imports WHERE id=?", (identity,))

    def repair(self, identity: str, candidate_id: str) -> dict[str, Any]:
        with self.connect(write=True) as connection:
            saved = connection.execute("SELECT name FROM voices WHERE id=?", (identity,)).fetchone()
            candidate = connection.execute(
                "SELECT metadata,audio,previewed,saved_id,name FROM voice_imports "
                "WHERE id=? AND expires>=?",
                (candidate_id, time.time()),
            ).fetchone()
            if not saved:
                raise ValueError("Saved voice not found; reload Voices")
            if not candidate:
                raise ValueError("Voice import expired or cancelled; choose the recording again")
            if candidate[3]:
                if candidate[3] != identity:
                    raise ValueError("This recording was already saved as another voice")
            else:
                if not candidate[2]:
                    raise ValueError("Preview the synthetic voice before repairing")
                metadata = record_metadata(candidate_id, candidate[4], candidate[0])
                audio = validated_reference(metadata, candidate[1])
                metadata.update(id=identity, name=validated_name(saved[0]))
                connection.execute(
                    "UPDATE voices SET metadata=?,audio=? WHERE id=?",
                    (json.dumps(metadata), audio, identity),
                )
                connection.execute(
                    "UPDATE voice_imports SET saved_id=?,audio=NULL WHERE id=?",
                    (identity, candidate_id),
                )
        return self.read(identity)

    def read(self, identity: str) -> dict[str, Any]:
        if not isinstance(identity, str):
            raise ValueError(
                "Voice identity is corrupt; preserve the database and restore a backup"
            )
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name,metadata,audio FROM voices WHERE id=?", (identity,)
            ).fetchone()
        if not row:
            raise ValueError("Saved voice not found; reload Voices")
        error = ""
        name = row[0] if isinstance(row[0], str) else "Unavailable saved voice"
        metadata: dict[str, Any] = {"id": identity, "name": name, "engine": ENGINE}
        try:
            checked = record_metadata(identity, row[0], row[1])
            validated_reference(checked, row[2])
            metadata.update(checked)
        except (ValueError, TypeError) as problem:
            error = str(problem)
        return {**metadata, "id": identity, "name": name, "available": not error, "error": error}

    def rename(self, identity: str, name: Any) -> dict[str, Any]:
        name = validated_name(name)
        with self.connect(write=True) as connection:
            row = connection.execute(
                "SELECT metadata,name FROM voices WHERE id=?", (identity,)
            ).fetchone()
            if not row:
                raise ValueError("Saved voice not found; reload Voices")
            if connection.execute(
                "SELECT 1 FROM voices WHERE name_key=? AND id<>?", (name.casefold(), identity)
            ).fetchone():
                raise ValueError("A voice with this name already exists; choose another name")
            metadata = record_metadata(identity, row[1], row[0])
            metadata["name"] = name
            connection.execute(
                "UPDATE voices SET name=?,name_key=?,metadata=? WHERE id=?",
                (name, name.casefold(), json.dumps(metadata), identity),
            )
        return self.read(identity)

    def usage(self, identity: str) -> list[dict[str, str]]:
        with self.connect() as connection:
            return [
                {"id": row[0], "name": row[1]}
                for row in connection.execute(
                    "SELECT id,name FROM avatars WHERE voice=? ORDER BY name_key", (identity,)
                )
            ]

    def delete(self, identity: str, name: Any) -> None:
        with self.connect(write=True) as connection:
            row = connection.execute("SELECT name FROM voices WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ValueError("Saved voice not found; reload Voices")
            if row[0] != name:
                raise ValueError("Voice name changed; reload and confirm deletion again")
            uses = connection.execute(
                "SELECT name FROM avatars WHERE voice=? ORDER BY name_key", (identity,)
            ).fetchall()
            if uses:
                raise ValueError(
                    "Voice is used by: "
                    + ", ".join(str(use[0]) for use in uses)
                    + "; change those avatars before deleting"
                )
            connection.execute("DELETE FROM voices WHERE id=?", (identity,))
            connection.execute("DELETE FROM voice_imports WHERE saved_id=?", (identity,))

    def list(self) -> list[dict[str, Any]]:
        if self.error:
            return []
        try:
            with self.connect() as connection:
                records = connection.execute(
                    "SELECT rowid,id,name FROM voices ORDER BY name_key"
                ).fetchall()
        except ValueError as problem:
            self.error = (
                "Voice storage unavailable; preserve the database, restore it or a backup, "
                f"and restart. Built-in voices remain available. ({problem})"
            )
            return []
        result = []
        for rowid, identity, name in records:
            if not isinstance(identity, str) or not isinstance(name, str):
                result.append(
                    {
                        "id": "unavailable-record-" + str(rowid),
                        "name": name
                        if isinstance(name, str)
                        else "Unavailable saved voice " + str(rowid),
                        "engine": ENGINE,
                        "available": False,
                        "error": "Saved voice identity/name is corrupt; "
                        "preserve the database and restore a backup",
                    }
                )
            else:
                try:
                    result.append(self.read(identity))
                except ValueError as problem:
                    result.append(
                        {
                            "id": identity,
                            "name": name,
                            "engine": ENGINE,
                            "available": False,
                            "error": str(problem),
                        }
                    )
        return result
