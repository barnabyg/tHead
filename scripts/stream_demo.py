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
    parser.add_argument("--speech", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--conversation", action="store_true")
    parser.add_argument("--fixture-provider", action="store_true")
    parser.add_argument("--initialize-budget", action="store_true")
    parser.add_argument("--budget")
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
    # The server shuts down after two hours. Allow five more minutes for imports,
    # request teardown and its 120-second worker join before killing the tree.
    run(
        [
            str(RUNTIME / "venv/Scripts/python.exe"),
            str(
                ROOT / ("scripts/conversation.py" if args.conversation else "scripts/streaming.py")
            ),
            *([] if args.conversation else ["--fragment-frames", str(args.fragment_frames)]),
            *(["--fixture-provider"] if args.fixture_provider and args.conversation else []),
            *(["--initialize-budget"] if args.initialize_budget else []),
            *(["--budget", args.budget] if args.budget else []),
            *(["--speech", "--output", str(RUNTIME / "speech")] if args.speech else []),
            *(["--diagnostics"] if args.diagnostics else []),
        ],
        7500,
    )


if __name__ == "__main__":
    main()
