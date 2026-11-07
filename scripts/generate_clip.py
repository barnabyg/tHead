"""Run real Lite inference and validate a muxed H.264/AAC demonstration clip."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import subprocess  # nosec B404
import time
import traceback
import wave
from collections import deque
from pathlib import Path
from typing import Any

from prepare import ROOT, RUNTIME, run
from smoke import load_pipeline

# B404/B603: fixed FFmpeg tools from the hash-verified build; review if made external.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=RUNTIME / "demo-inputs")
    parser.add_argument("--report", type=Path, default=RUNTIME / "clip-result.json")
    args = parser.parse_args()
    args.inputs = args.inputs.resolve()
    started = time.perf_counter()
    output = RUNTIME / "demo"
    result: dict[str, Any] = {"status": "blocked", "stage": "inputs"}
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result) + "\n", encoding="utf-8")
    try:
        lock = json.loads((ROOT / "demo-lock.json").read_text(encoding="utf-8"))
        binaries = RUNTIME / "media" / lock["media"]["directory"] / "bin"
        ffmpeg = str(binaries / "ffmpeg.exe")
        ffprobe = str(binaries / "ffprobe.exe")
        audio_path = args.inputs / "english.wav"
        with wave.open(str(audio_path), "rb") as audio_file:
            if (
                audio_file.getframerate(),
                audio_file.getnchannels(),
                audio_file.getsampwidth(),
            ) != (16000, 1, 2):
                raise RuntimeError("Expected mono 16 kHz PCM16 input")
            pcm = audio_file.readframes(audio_file.getnframes())
        result["stage"] = "media-tooling"
        version = subprocess.check_output(  # nosec B603
            [ffmpeg, "-version"], text=True, timeout=30
        )
        result["ffmpeg"] = version.splitlines()[0]
        pipeline, inference, torch = load_pipeline(
            RUNTIME / "models", RUNTIME / "FlashHead", result
        )
        np = importlib.import_module("numpy")
        speech = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        duration = len(speech) / 16000
        if not 0 < duration <= 30 or not np.isfinite(speech).all() or np.max(np.abs(speech)) < 0.01:
            raise RuntimeError("Input must contain non-silent finite speech, at most 30 seconds")
        result["input_duration_seconds"] = duration
        result["stage"] = "image-preparation"
        inference.get_base_data(pipeline, str(args.inputs / "portrait.jpg"), 42, False)
        params = inference.get_infer_params()
        result["settings"] = params
        if (params["height"], params["width"], params["tgt_fps"], params["sample_rate"]) != (
            512,
            512,
            25,
            16000,
        ):
            raise RuntimeError("Pinned 512x512 / 25 fps / 16 kHz profile changed")
        stride = params["frame_num"] - params["motion_frames_num"]
        samples_per_chunk = stride * 16000 // 25
        chunks = math.ceil(len(speech) / samples_per_chunk)
        speech = np.pad(speech, (0, chunks * samples_per_chunk - len(speech)))
        history: deque[float] = deque([0.0] * (8 * 16000), maxlen=8 * 16000)
        raw_path = output / "frames.rgb"
        result["stage"] = "inference"
        inference_started = time.perf_counter()
        output.mkdir(parents=True, exist_ok=True)
        with raw_path.open("wb") as raw:
            for index, chunk in enumerate(speech.reshape(chunks, samples_per_chunk)):
                history.extend(chunk.tolist())
                embedding = inference.get_audio_embedding(
                    pipeline, np.asarray(history), 8 * 25 - params["frame_num"], 8 * 25
                )
                frames = inference.run_pipeline(pipeline, embedding)[params["motion_frames_num"] :]
                frames = frames.to(torch.uint8).cpu().numpy()
                if frames.shape != (stride, 512, 512, 3):
                    raise RuntimeError(f"Unexpected generated frames: {frames.shape}")
                raw.write(frames.tobytes())
                print(f"Generated chunk {index + 1}/{chunks}", flush=True)
        torch.cuda.synchronize()
        result["inference_seconds"] = time.perf_counter() - inference_started
        result["generated_frames"] = chunks * stride
        result["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        result["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        result["stage"] = "mux"
        # Keep raw frames and partial media on failure. Only promote a validated output.
        candidate = output / "candidate.mp4"
        run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                "512x512",
                "-framerate",
                "25",
                "-i",
                str(raw_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-bf",
                "0",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(candidate),
            ],
            300,
        )
        result["stage"] = "media-validation"
        probe_output = subprocess.check_output(  # nosec B603
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(candidate),
            ],
            text=True,
            timeout=60,
        )
        probe = json.loads(probe_output)
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
        if (
            video["codec_name"],
            video["width"],
            video["height"],
            video["avg_frame_rate"],
            audio["codec_name"],
        ) != ("h264", 512, 512, "25/1", "aac"):
            raise RuntimeError("Unexpected output codecs, dimensions or frame rate")
        for stream in (video, audio):
            if (
                abs(float(stream["duration"]) - duration) > 0.08
                or abs(float(stream["start_time"])) > 0.04
            ):
                raise RuntimeError("Output timing differs from speech by more than two frames")
        run(
            [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(candidate), "-f", "null", "-"],
            180,
        )
        result["media"] = probe
        candidate.replace(output / "clip.mp4")
        result["output"] = str(output / "clip.mp4")
        result["status"] = "generated"
        result["stage"] = "complete"
        raw_path.unlink()  # Successful decode validated; retain bulky raw frames only on failure.
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
