"""Summarise measured local text/avatar runs; never infer perceptual feasibility."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess  # nosec B404
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from assess_streaming import summarise
from prepare import ROOT, RUNTIME


def decode(directory: Path, parts: int) -> dict[str, Any]:
    """Decode the exact published MP4 timeline, not synthetic substitutes."""
    lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
    binaries = RUNTIME / "media" / lock["media"]["directory"] / "bin"
    with tempfile.TemporaryDirectory() as temporary:
        media = Path(temporary) / "stream.mp4"
        with media.open("wb") as output:
            for index in range(parts):
                output.write((directory / f"{index}.mp4").read_bytes())
        # Fixed hash-verified local media tools and task-owned files only.
        subprocess.run(  # nosec B603
            [
                str(binaries / "ffmpeg.exe"),
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(media),
                "-f",
                "null",
                "-",
            ],
            check=True,
            timeout=600,
        )
        probe = subprocess.check_output(  # nosec B603
            [
                str(binaries / "ffprobe.exe"),
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=codec_type,start_time,duration,nb_read_frames,sample_rate,channels",
                "-of",
                "json",
                str(media),
            ],
            timeout=600,
        )
        value: dict[str, Any] = json.loads(probe)
        return value


def monitor(seconds: int, output: Path) -> None:
    psutil = importlib.import_module("psutil")
    samples = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        # B603/B607: fixed installed diagnostic tool and read-only query.
        gpu = subprocess.check_output(  # nosec B603 B607
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=30,
        )
        gpu = gpu.strip()
        processes = []
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                command = " ".join(process.info["cmdline"] or [])
                if "scripts/streaming.py" in command or "speech-worker.ps1" in command:
                    cpu = process.cpu_times()
                    processes.append(
                        {
                            "pid": process.pid,
                            "name": process.info["name"],
                            "rss_bytes": process.memory_info().rss,
                            "cpu_seconds": cpu.user + cpu.system,
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        samples.append(
            {
                "utc": datetime.now(timezone.utc).isoformat(),
                "system_cpu_percent": psutil.cpu_percent(),
                "gpu": gpu,
                "processes": processes,
            }
        )
        output.write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
        time.sleep(1)


def resources(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not measured"}
    samples = json.loads(path.read_text(encoding="utf-8"))
    if not samples:
        return {"status": "no samples"}
    gpu = [list(map(int, sample["gpu"].split(","))) for sample in samples]
    processes: dict[int, list[dict[str, Any]]] = {}
    for sample in samples:
        for process in sample["processes"]:
            processes.setdefault(process["pid"], []).append(process)
    return {
        "samples": len(samples),
        "first_utc": samples[0]["utc"],
        "last_utc": samples[-1]["utc"],
        "sampling": "one second plus diagnostic overhead; includes idle time and development load",
        "system_cpu_percent_range": [
            min(s["system_cpu_percent"] for s in samples),
            max(s["system_cpu_percent"] for s in samples),
        ],
        "gpu_utilization_percent_range": [min(s[0] for s in gpu), max(s[0] for s in gpu)],
        "gpu_used_mib_range": [min(s[1] for s in gpu), max(s[1] for s in gpu)],
        "processes": [
            {
                "pid": pid,
                "name": values[0]["name"],
                "rss_bytes_range": [
                    min(p["rss_bytes"] for p in values),
                    max(p["rss_bytes"] for p in values),
                ],
                "observed_cpu_seconds": values[-1]["cpu_seconds"] - values[0]["cpu_seconds"],
            }
            for pid, values in processes.items()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNTIME / "speech")
    parser.add_argument("--output", type=Path, default=RUNTIME / "speech-assessment.json")
    parser.add_argument("--monitor-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.monitor_seconds:
        if not 1 <= args.monitor_seconds <= 1800:
            raise ValueError("Resource monitor must be bounded to 1–1800 seconds")
        monitor(args.monitor_seconds, args.output)
        return
    runs = []
    for path in sorted(args.runs.glob("*/result.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        events = report["events"]
        if not any(e["event"] == "text-submitted" for e in events):
            continue

        def first(kind: str, source: list[dict[str, Any]] = events) -> dict[str, Any]:
            return next((e for e in source if e["event"] == kind), {})

        result = summarise(report)
        tts = [e for e in events if e["event"] == "tts-segment"]
        audible = first("digital-audio-onset").get("seconds")
        playing = result["first_playing_seconds"]
        samples = sum(e["samples"] for e in tts)
        preparation = sum(e["preparation_seconds"] for e in tts)
        result.update(
            {
                "text": first("text-submitted").get("text"),
                "tts_segments": tts,
                "first_tts_audio_seconds": tts[0]["seconds"] if tts else None,
                "tts_preparation_seconds": preparation,
                "tts_speed_relative_to_playback": samples / 16000 / preparation
                if preparation
                else None,
                "tts_complete": first("tts-complete"),
                "digital_audio_onset_seconds": audible,
                "audible_with_moving_video_seconds": max(
                    audible, result["first_presented_frame_seconds"]
                )
                if audible is not None and result["first_presented_frame_seconds"] is not None
                else None,
                "playback_before_last_phrase_synthesis": bool(
                    playing is not None and tts and playing < tts[-1]["seconds"]
                ),
                "pcm_handoff_matches_synthesis": first("input-complete").get("sha256")
                == first("tts-complete").get("sha256")
                if first("tts-complete").get("sha256")
                else None,
                "tts_released": first("tts-released"),
                "resources_released": first("resources-released"),
            }
        )
        if report["state"] == "complete" or (first("ended") and first("transport-complete")):
            result["decoded_media"] = decode(path.parent, report["parts"])
        runs.append(result)
    result = {
        "measurement": "server receipt times and real browser audio graph/presentation callbacks",
        "physical_speaker_latency": "not measured",
        "perceptual_confirmation": "record separately; metrics alone cannot establish lip sync",
        "runtime": json.loads((args.runs / "readiness.json").read_text(encoding="utf-8")),
        "avatar_pins": json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8")),
        "speech_pins": json.loads((ROOT / "speech-lock.json").read_text(encoding="utf-8")),
        "resource_observations": resources(RUNTIME / "speech-resources.json"),
        "runs": runs,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(runs)} measured text runs to {args.output}")


if __name__ == "__main__":
    main()
