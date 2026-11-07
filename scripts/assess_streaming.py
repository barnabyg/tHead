"""Summarise real player reports and decode completed continuous MP4 streams."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess  # nosec B404
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare import ROOT, RUNTIME, run


def summarise(report: dict[str, Any]) -> dict[str, Any]:
    events = report["events"]

    def first(kind: str) -> dict[str, Any]:
        return next((e for e in events if e["event"] == kind), {})

    playing = first("playing").get("seconds")
    stalls = []
    waiting = None
    for event in events:
        if playing is None or event["seconds"] <= playing:
            continue
        if event["event"] in ("waiting", "stalled") and waiting is None:
            waiting = event["seconds"]
        if event["event"] in ("playing", "ended") and waiting is not None:
            stalls.append(event["seconds"] - waiting)
            waiting = None
    generated = [e for e in events if e["event"] == "frames-ready"]
    generation_seconds = sum(e["generation_seconds"] for e in generated)
    rendered = first("render-complete")
    complete_input = first("complete-input")
    duration = rendered.get("samples", 0) / 16000 or complete_input.get("duration")
    if not duration:
        duration = first("generation-start").get("duration")
    fragments = [e for e in events if e["event"] == "media-ready" and e["index"] > 0]
    arrived = first("audio-arrived").get("seconds")
    return {
        "id": report["id"],
        "state": report["state"],
        "input": first("generation-start"),
        "duration_seconds": duration,
        "transport": first("transport-profile") or {"fragment_frames": 24},
        "first_frames_seconds": first("frames-ready").get("seconds"),
        "first_playable_seconds": fragments[0]["seconds"] if fragments else None,
        "first_playing_seconds": playing,
        "first_presented_frame_seconds": first("first-frame-presented").get("seconds"),
        "render_complete_seconds": rendered.get("seconds"),
        "playback_before_render_complete": bool(
            playing is not None and rendered and playing < rendered["seconds"]
        ),
        "first_arrival_to_playing_seconds": playing - arrived if playing and arrived else None,
        "model_generation_seconds": generation_seconds,
        "model_speed_relative_to_playback": duration / generation_seconds
        if duration and generation_seconds
        else None,
        "max_pending_fragments": max((e.get("pending", 0) for e in fragments), default=0),
        "max_reported_browser_buffer_seconds": max(
            (e.get("buffered", 0) for e in events), default=0
        ),
        "post_start_stalls_seconds": stalls,
        "unresolved_stall": waiting is not None,
        "ended_media_time": first("ended").get("currentTime"),
        "memory": {k: v for k, v in rendered.items() if k.endswith("bytes")},
        "input_integrity": first("input-complete") or complete_input,
        "client_settings": first("client-settings"),
        "max_queued_input_chunks": max((e.get("queued", 0) for e in events), default=0),
        "media_published_after_stop": any(
            e["event"] == "media-ready" and e["seconds"] > first("stop-handled")["seconds"]
            for e in events
        )
        if first("stop-handled")
        else False,
        "stop": first("stop-handled"),
        "client_pause": first("client-paused"),
        "digital_silence": first("digital-silence"),
        "abandoned": first("generation-abandoned"),
        "error": report["error"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNTIME / "streaming")
    parser.add_argument("--output", type=Path, default=RUNTIME / "streaming-assessment.json")
    args = parser.parse_args()
    lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
    binaries = RUNTIME / "media" / lock["media"]["directory"] / "bin"
    summaries = []
    for path in sorted(args.runs.glob("*/result.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        summary = summarise(report)
        duration = summary["duration_seconds"]
        if duration:
            source = (
                RUNTIME / "demo-inputs" / ("english-long.wav" if duration == 20 else "english.wav")
            )
            with wave.open(str(source), "rb") as audio:
                pcm = audio.readframes(round(duration * 16000))
            summary["declared_pcm_sha256"] = hashlib.sha256(pcm).hexdigest()
            actual = summary["input_integrity"].get("sha256")
            summary["received_pcm_matches_source"] = (
                actual == summary["declared_pcm_sha256"] if actual else None
            )
            if actual and not summary["received_pcm_matches_source"]:
                raise RuntimeError(f"Received PCM differs from declared source: {path.parent}")
        if (
            summary["render_complete_seconds"] is not None
            and summary["ended_media_time"] is not None
        ):
            with tempfile.TemporaryDirectory(dir=RUNTIME) as temporary:
                media = Path(temporary) / "stream.mp4"
                with media.open("wb") as output:
                    for index in range(report["parts"]):
                        output.write((path.parent / f"{index}.mp4").read_bytes())
                # B603: pinned media tools and task-owned paths; no shell or remote input.
                probe = subprocess.check_output(  # nosec B603
                    [
                        str(binaries / "ffprobe.exe"),
                        "-v",
                        "error",
                        "-show_streams",
                        "-count_frames",
                        "-show_format",
                        "-of",
                        "json",
                        str(media),
                    ],
                    text=True,
                    timeout=60,
                )
                summary["media_probe"] = json.loads(probe)
                streams = summary["media_probe"]["streams"]
                video = next(s for s in streams if s["codec_type"] == "video")
                audio = next(s for s in streams if s["codec_type"] == "audio")
                if (
                    video["codec_name"],
                    video["width"],
                    video["height"],
                    video["r_frame_rate"],
                    audio["codec_name"],
                ) != ("h264", 512, 512, "25/1", "aac"):
                    raise RuntimeError(f"Unexpected media profile: {path.parent}")
                expected = summary["duration_seconds"]
                if expected:
                    if int(video["nb_read_frames"]) != math.ceil(expected * 25):
                        raise RuntimeError(f"Lost or duplicated video frames: {path.parent}")
                    if any(abs(float(s["duration"]) - expected) > 0.09 for s in (video, audio)):
                        raise RuntimeError(f"Unexpected final duration: {path.parent}")
                if abs(float(video["start_time"]) - float(audio["start_time"])) > 0.04:
                    raise RuntimeError(f"Audio/video start mismatch: {path.parent}")
                run(
                    [
                        str(binaries / "ffmpeg.exe"),
                        "-nostdin",
                        "-v",
                        "error",
                        "-xerror",
                        "-i",
                        str(media),
                        "-f",
                        "null",
                        "-",
                    ],
                    180,
                )
                summary["decode"] = "passed"
        summaries.append(summary)
    result = {
        "measurement_date": datetime.now(timezone.utc).date().isoformat(),
        "readiness": json.loads((args.runs / "readiness.json").read_text(encoding="utf-8")),
        "runs": summaries,
        "limits": "Browser events do not certify audible output or perceived lip sync.",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Assessed {len(summaries)} runs: {args.output}")


if __name__ == "__main__":
    main()
