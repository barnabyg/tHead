"""Prepare the pinned demo and supervise the bounded browser server process."""

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

from avatars import AvatarStore, user_data_directory
from demo import acquire
from pairs import configured_pairs
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
    parser.add_argument("--user-data", type=Path)
    parser.add_argument("--candidate-chatterbox", action="store_true")
    parser.add_argument("--chatterbox-state", type=Path)
    parser.add_argument("--skip-preparation", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--avatar",
        "--pair",
        dest="pair",
        default=os.environ.get("THEAD_AVATAR", os.environ.get("THEAD_PAIR", "")),
    )
    args = parser.parse_args()
    if args.conversation:
        try:
            store = AvatarStore(args.user_data or user_data_directory())
            args.pair = args.pair or store.default_avatar()
            store.get(args.pair)
        except ValueError as error:
            parser.error(str(error))
    if not args.skip_preparation:
        run([sys.executable, str(ROOT / "scripts/demo.py"), "--prepare-only"], 18000)
    if args.conversation and not args.skip_preparation:
        for pair in configured_pairs().values():
            asset = pair.portrait
            acquire(asset["url"], RUNTIME / "demo-inputs" / asset["filename"], asset["sha256"])
    lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
    ffmpeg = RUNTIME / "media" / lock["media"]["directory"] / "bin/ffmpeg.exe"
    if not args.skip_preparation:
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
        threading.Timer(2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    # The server shuts down after two hours. Allow five more minutes for imports,
    # request teardown and its 120-second worker join before killing the tree.
    run(
        [
            str(RUNTIME / "venv/Scripts/python.exe"),
            str(
                ROOT / ("scripts/conversation.py" if args.conversation else "scripts/streaming.py")
            ),
            *([] if args.conversation else ["--fragment-frames", str(args.fragment_frames)]),
            "--port",
            str(args.port),
            *(["--pair", args.pair] if args.conversation else []),
            *(["--fixture-provider"] if args.fixture_provider and args.conversation else []),
            *(["--initialize-budget"] if args.initialize_budget else []),
            *(["--budget", args.budget] if args.budget else []),
            *(["--user-data", str(args.user_data)] if args.user_data else []),
            *(
                ["--output", str(args.user_data / "app-output")]
                if args.candidate_chatterbox and args.user_data
                else []
            ),
            *(
                ["--budget", str(args.user_data / "candidate-budget.sqlite3")]
                if args.candidate_chatterbox and args.user_data and not args.budget
                else []
            ),
            *(["--candidate-chatterbox"] if args.candidate_chatterbox else []),
            *(["--chatterbox-state", str(args.chatterbox_state)] if args.chatterbox_state else []),
            *(["--speech", "--output", str(RUNTIME / "speech")] if args.speech else []),
            *(["--diagnostics"] if args.diagnostics else []),
        ],
        7500,
    )


if __name__ == "__main__":
    main()
