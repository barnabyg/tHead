"""Prepare the pinned demo and supervise the bounded browser server process."""

import argparse
import sys
import threading
import webbrowser

from prepare import ROOT, RUNTIME, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run([sys.executable, str(ROOT / "scripts/demo.py"), "--prepare-only"], 18000)
    if not args.no_browser:
        threading.Timer(2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    # Two-hour server lifetime; prepare.run kills the process tree on expiry.
    run([str(RUNTIME / "venv/Scripts/python.exe"), str(ROOT / "scripts/streaming.py")], 7200)


if __name__ == "__main__":
    main()
