"""Prepare the pinned demo and supervise the bounded browser server process."""

import argparse
import json
import sys
import threading
import webbrowser

from prepare import ROOT, RUNTIME, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--fragment-frames", type=int, choices=(8, 24), default=8)
    args = parser.parse_args()
    run([sys.executable, str(ROOT / "scripts/demo.py"), "--prepare-only"], 18000)
    lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
    ffmpeg = RUNTIME / "media" / lock["media"]["directory"] / "bin/ffmpeg.exe"
    run(
        [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            "31",
            "-i",
            str(RUNTIME / "demo-inputs/speech.ogg"),
            "-t",
            "20",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(RUNTIME / "demo-inputs/english-long.wav"),
        ],
        180,
    )
    if not args.no_browser:
        threading.Timer(2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    # Two-hour server lifetime; prepare.run kills the process tree on expiry.
    run(
        [
            str(RUNTIME / "venv/Scripts/python.exe"),
            str(ROOT / "scripts/streaming.py"),
            "--fragment-frames",
            str(args.fragment_frames),
        ],
        7200,
    )


if __name__ == "__main__":
    main()
