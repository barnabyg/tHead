"""Explicitly prepare only the hash-pinned local reference-audio tools."""

from __future__ import annotations

import hashlib
import importlib
import json
import ssl
import time
import urllib.request
import zipfile
from pathlib import Path

from prepare import ROOT, RUNTIME
from voices import AudioDecoder


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    media = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))["media"]
    decoder = AudioDecoder()
    directory = RUNTIME / "media" / media["directory"]
    try:
        decoder.executable("ffmpeg.exe")
        decoder.executable("ffprobe.exe")
        if (directory / "LICENSE").is_file() and (directory / "README.txt").is_file():
            print("Pinned local audio tools ready; no model downloads or paid calls.")
            return
    except ValueError:
        pass
    archive = RUNTIME / "media/ffmpeg.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix(".partial")
        started = time.monotonic()
        # The URL is fixed in demo-lock.json, never supplied by an upload or HTTP client.
        # Use the development environment's hash-locked CA bundle, not disabled TLS checks.
        certificates = importlib.import_module("certifi")
        context = ssl.create_default_context(cafile=str(certificates.where()))
        request = urllib.request.Request(
            media["url"], headers={"User-Agent": "tHead-voice-tools/1"}
        )
        print(
            "Preparing pinned local audio tools (114 MB); no speech models are downloaded.",
            flush=True,
        )
        try:
            with urllib.request.urlopen(request, context=context, timeout=180) as response:  # nosec B310
                with temporary.open("wb") as output:
                    while block := response.read(1024 * 1024):
                        if time.monotonic() - started > 600:
                            raise TimeoutError(
                                "Audio-tool download exceeded ten minutes; retry preparation"
                            )
                        if output.tell() + len(block) > 200 * 1024 * 1024:
                            raise ValueError("Audio-tool archive exceeded its size limit")
                        output.write(block)
            if digest(temporary) != media["sha256"]:
                raise ValueError("Audio-tool archive hash mismatch; preparation refused")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if digest(archive) != media["sha256"]:
        raise ValueError("Cached audio-tool archive changed; preserve or remove it and retry")
    # Extract only the two named tools and their notices, never arbitrary archive paths.
    with zipfile.ZipFile(archive) as bundle:
        for name in ("bin/ffmpeg.exe", "bin/ffprobe.exe", "LICENSE", "README.txt"):
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".partial")
            try:
                temporary.write_bytes(bundle.read(media["directory"] + "/" + name))
                if name.startswith("bin/") and digest(temporary) != decoder.hashes[Path(name).name]:
                    raise ValueError(
                        "Audio-tool executable differs from its pin; preparation refused"
                    )
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    print("Pinned local audio tools ready. Licence and notices retained beside the binaries.")


if __name__ == "__main__":
    main()
