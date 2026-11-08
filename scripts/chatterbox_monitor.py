"""Read-only task process-tree and GPU sampling for the native bounded benchmark."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess  # nosec B404
import time
from pathlib import Path

# B404/B603/B607: fixed installed diagnostic executable and numeric process IDs.
# Review if commands become externally supplied.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.seconds <= 7200:
        raise ValueError("Supply a new output and a bounded 1–7200-second interval")
    psutil = importlib.import_module("psutil")
    deadline = time.monotonic() + args.seconds
    psutil.cpu_percent()
    with args.output.open("w", encoding="utf-8") as stream:
        while time.monotonic() < deadline and not args.stop_file.exists():
            started = time.monotonic()
            processes = {}
            for identity in args.pid:
                try:
                    root = psutil.Process(identity)
                    for process in [root, *root.children(recursive=True)]:
                        if process.pid == os.getpid():
                            continue
                        with process.oneshot():
                            cpu = process.cpu_times()
                            processes[process.pid] = {
                                "pid": process.pid,
                                "rss_bytes": process.memory_info().rss,
                                "cpu_seconds": cpu.user + cpu.system,
                            }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            gpu = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    timeout=30,
                )
                .strip()
                .split(",")
            )
            sample = {
                "epoch_seconds": time.time(),
                "system_cpu_percent": psutil.cpu_percent(),
                "gpu_memory_mib": int(gpu[0]),
                "gpu_percent": int(gpu[1]),
                "processes": list(processes.values()),
            }
            stream.write(json.dumps(sample) + "\n")
            stream.flush()
            time.sleep(max(0.05, 0.5 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
