"""Isolated, opt-in Chatterbox audition; never used by the normal application."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import random
import re
import subprocess  # nosec B404
import sys
import time
import uuid
import warnings
import wave
from pathlib import Path
from typing import Any

# B404: fixed shell-free candidate commands only; review if commands become external.

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_network(event: str, arguments: tuple[object, ...]) -> None:
    """Fail on Python socket attempts, including unexpected lazy model downloads."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise OSError(f"Offline audition blocked network operation: {event}")


def synthesize(args: argparse.Namespace, lock: dict[str, Any]) -> None:
    started = time.perf_counter()
    report: dict[str, Any] = {
        "status": "failed",
        "source_revision": lock["upstream_revision"],
        "model_revision": lock["model"]["revision"],
        "reference_sha256": sha256(args.reference),
        "text": args.text,
        "seed": args.seed,
        "device": args.device,
        "threads": 8,
        "network_policy": "offline environment flags and Python socket audit hook",
        "streaming": False,
    }
    try:
        if sys.version_info[:3] != tuple(int(part) for part in lock["python"].split(".")):
            raise ValueError("Python differs from the evaluated pin; prepare a fresh state")
        os.environ.update(
            HF_HOME=str(args.state / "hf-cache"),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
            GRADIO_ANALYTICS_ENABLED="False",
            DO_NOT_TRACK="1",
        )
        sys.addaudithook(reject_network)
        # Upstream's pinned S3Gen still uses this compatibility layer. The warning
        # does not affect inference; revisit/remove this exact filter when either
        # the model/source or diffusers pin changes. All other warnings remain errors
        # when callers enable that policy.
        warnings.filterwarnings(
            "ignore",
            message=re.escape(
                "`LoRACompatibleLinear` is deprecated and will be removed in version 1.0.0. "
                "Use of `LoRACompatibleLinear` is deprecated. Please switch to PEFT backend "
                "by installing PEFT: `pip install peft`."
            )
            + "$",
            category=FutureWarning,
            module=r"diffusers\.models\.lora",
        )
        torch = importlib.import_module("torch")
        np = importlib.import_module("numpy")
        soundfile = importlib.import_module("soundfile")
        candidate = importlib.import_module("chatterbox.tts_turbo")
        if torch.__version__ != lock["torch"] or torch.version.cuda != lock["cuda"]:
            raise ValueError(
                "PyTorch/CUDA differs from the evaluated CPU pin; prepare a fresh state"
            )
        if args.device != "cpu":
            raise ValueError("GPU configuration has not been evaluated; no automatic fallback")
        torch.set_num_threads(8)
        torch.set_num_interop_threads(1)
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        report["import_seconds"] = time.perf_counter() - started
        model = candidate.ChatterboxTurboTTS.from_local(args.state / "model", "cpu", nano=True)
        report["ready_seconds"] = time.perf_counter() - started
        conditioning = time.perf_counter()
        model.prepare_conditionals(str(args.reference), exaggeration=0.0, norm_loudness=True)
        report["conditioning_seconds"] = time.perf_counter() - conditioning
        generation = time.perf_counter()
        with torch.inference_mode():
            audio = model.generate(args.text, temperature=0.8, top_p=0.95, top_k=1000)
        report["synthesis_seconds"] = time.perf_counter() - generation
        report["first_pcm_seconds"] = time.perf_counter() - started
        samples = audio.squeeze(0).numpy()
        if samples.ndim != 1 or not np.isfinite(samples).all() or not np.any(samples):
            raise ValueError("Synthesis returned invalid or silent mono audio")
        output = args.output / "speech.wav"
        soundfile.write(str(output), samples, model.sr, subtype="PCM_16")
        report.update(
            status="generated_unreviewed",
            sample_rate=model.sr,
            channels=1,
            duration_seconds=len(samples) / model.sr,
            real_time_factor=report["synthesis_seconds"] / (len(samples) / model.sr),
            output_sha256=sha256(output),
            watermark="upstream PerthImplicitWatermarker, unmodified",
        )
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["total_seconds"] = time.perf_counter() - started
        (args.output / "result.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--text", required=True)
    parser.add_argument("--state", type=Path, default=ROOT / ".runtime/chatterbox-eval")
    parser.add_argument("--prepare", action="store_true", help="Download pinned evaluation assets")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument(
        "--output", type=Path, help="New directory for this attempt's WAV and evidence"
    )
    parser.add_argument(
        "--play", action="store_true", help="Open the WAV in the Windows audio player"
    )
    parser.add_argument("--device", choices=["cpu"], default="cpu")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        args.state = args.state.resolve()
        args.reference = args.reference.resolve()
        if not args.text.strip() or len(args.text) > 1200:
            raise ValueError("Enter 1–1200 characters of English text")
        if not 0 <= args.seed < 2**32:
            raise ValueError("Seed must be between 0 and 4294967295")
        if not args.reference.is_file():
            raise ValueError("Reference WAV does not exist")
        if args.reference.stat().st_size > 12 * 1024 * 1024:
            raise ValueError("Reference WAV must be at most 12 MiB")
        with wave.open(str(args.reference), "rb") as reference:
            if reference.getnframes() / reference.getframerate() <= 5:
                raise ValueError("Reference WAV must be longer than 5 seconds")
            if (
                reference.getnchannels() != 1
                or reference.getsampwidth() != 2
                or reference.getframerate() not in {16000, 22050, 24000, 44100, 48000}
                or reference.getnframes() / reference.getframerate() > 30
                or len(reference.readframes(reference.getnframes())) != reference.getnframes() * 2
            ):
                raise ValueError("Use a complete mono PCM16 WAV, 16–48 kHz, at most 30 seconds")
        lock = json.loads((ROOT / "chatterbox-lock.json").read_text(encoding="utf-8"))
        if args.prepare and not args.worker:
            from prepare import run

            run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts/prepare-chatterbox.ps1"),
                    "-State",
                    str(args.state),
                ],
                10800,
            )
        for asset in lock["model"]["files"]:
            path = args.state / "model" / asset["name"]
            if not path.is_file():
                raise ValueError(f"Missing pinned model asset: {path}. Run with --prepare.")
            if sha256(path) != asset["sha256"]:
                raise ValueError(f"Pinned model asset hash differs: {path}")
        if list((args.state / "model").glob("*.pt")):
            raise ValueError("Unexpected pickle model asset; use only the pinned safetensors set")
        if args.worker:
            synthesize(args, lock)
        else:
            from prepare import run

            python = args.state / "venv/Scripts/python.exe"
            if not python.is_file():
                raise ValueError("Evaluation environment is not prepared. Run with --prepare.")
            args.output = (args.output or args.state / "auditions" / uuid.uuid4().hex).resolve()
            args.output.mkdir(parents=True, exist_ok=False)
            command = [
                str(python),
                "-I",
                str(Path(__file__).resolve()),
                "--worker",
                "--reference",
                str(args.reference),
                "--text",
                args.text,
                "--state",
                str(args.state),
                "--output",
                str(args.output),
                "--seed",
                str(args.seed),
                "--device",
                args.device,
            ]
            # -I excludes inherited Python paths/home from the application's other interpreter.
            try:
                run(command, 1800)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                if not (args.output / "result.json").exists():
                    (args.output / "result.json").write_text(
                        json.dumps({"status": "failed", "error": str(error)}) + "\n",
                        encoding="utf-8",
                    )
                raise
            print(f"Audition WAV and evidence: {args.output}")
            if args.play:
                # B606: opt-in OS playback of our fixed WAV; review if the file type changes.
                os.startfile(args.output / "speech.wav")  # nosec B606
        return 0
    except (wave.Error, EOFError) as error:
        print(f"Invalid reference WAV: {error}", file=sys.stderr)
        return 1
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
