"""Prepare the pinned runtime and inputs, generate a clip, and launch native playback."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from prepare import ROOT, RUNTIME, run


def acquire(url: str, path: Path, expected_hash: str) -> None:
    """Download only declared HTTPS assets, rejecting changed or partial content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        deadline = time.monotonic() + 600
        partial = path.with_suffix(path.suffix + ".partial")
        request = urllib.request.Request(url, headers={"User-Agent": "tHead-demo/0.1"})
        # URLs are fixed in demo-lock.json, not supplied by a remote caller.
        with urllib.request.urlopen(request, timeout=180) as response:  # nosec B310
            with partial.open("wb") as output:
                while block := response.read(1024 * 1024):
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"Download exceeded ten minutes: {path}")
                    output.write(block)
        partial.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise RuntimeError(f"Hash mismatch: {path}; preserve or remove it before retrying")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-play", action="store_true", help="Generate without opening a player")
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    report = RUNTIME / "demo-result.json"
    started = time.perf_counter()
    result: dict[str, Any] = {"status": "blocked", "stage": "setup"}
    report.write_text(json.dumps(result) + "\n", encoding="utf-8")
    try:
        run([sys.executable, str(ROOT / "scripts/prepare.py")], 18000)
        result["stage"] = "media-acquisition"
        lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
        media = lock["media"]
        archive = RUNTIME / "media/ffmpeg.zip"
        acquire(media["url"], archive, media["sha256"])
        # The verified archive contains a fixed build tree, including its license.
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                destination = RUNTIME / "media" / member.filename
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    expected = bundle.read(member)
                    if not destination.is_file() or destination.read_bytes() != expected:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(expected)
        binaries = RUNTIME / "media" / media["directory"] / "bin"
        for asset in lock["inputs"]:
            acquire(asset["url"], RUNTIME / "demo-inputs" / asset["filename"], asset["sha256"])
        result["stage"] = "audio-preparation"
        run(
            [
                str(binaries / "ffmpeg.exe"),
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-ss",
                str(lock["audio_start_seconds"]),
                "-i",
                str(RUNTIME / "demo-inputs/speech.ogg"),
                "-t",
                str(lock["audio_duration_seconds"]),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(RUNTIME / "demo-inputs/english.wav"),
            ],
            180,
        )
        result["stage"] = "generation"
        run(
            [str(RUNTIME / "venv/Scripts/python.exe"), str(ROOT / "scripts/generate_clip.py")], 3600
        )
        result["generation"] = json.loads(
            (RUNTIME / "clip-result.json").read_text(encoding="utf-8")
        )
        if result["generation"]["status"] != "generated":
            raise RuntimeError("Generation did not validate the output")
        result["stage"] = "playback"
        if not args.no_play:
            run(
                [
                    str(binaries / "ffplay.exe"),
                    "-autoexit",
                    "-window_title",
                    "tHead - synthetic JFK demonstration",
                    str(RUNTIME / "demo/clip.mp4"),
                ],
                180,
            )
        result["status"] = "generated"
        result["stage"] = "complete"
        result["playback"] = "not-requested" if args.no_play else "player-exited"
        result["manual_verification"] = (
            "Listen for speech and check mouth synchronisation; required"
        )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        traceback.print_exc()
    finally:
        result["elapsed_seconds"] = time.perf_counter() - started
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "generated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
