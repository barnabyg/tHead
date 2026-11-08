"""Private bounded JSON-lines worker for the opt-in experimental application."""

from __future__ import annotations

import argparse
import base64
import contextlib
import importlib
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chatterbox_eval import ReferenceAlignmentDiagnostic, configure_warning_policy, reject_network  # noqa: E402
from chatterbox_voice import reference_file, reference_record  # noqa: E402


def send(value: dict[str, Any]) -> None:
    print(json.dumps(value), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--reference-id", required=True)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--configuration", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    reference = reference_file(args.state, args.reference_id)
    record = reference_record(args.reference_id)
    started = time.perf_counter()
    model: Any = None
    torch: Any = None
    np: Any = None
    soxr: Any = None
    resampler: Any = None
    diagnostics: list[str] = []
    if not args.fixture:
        os.environ.update(
            HF_HOME=str(args.state / "hf-cache"),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            GRADIO_ANALYTICS_ENABLED="False",
        )
        sys.addaudithook(reject_network)
        logging.getLogger().addFilter(ReferenceAlignmentDiagnostic(diagnostics))
        configure_warning_policy()
        lock = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / (
                    "chatterbox-gpu-lock.json"
                    if args.configuration == "cuda"
                    else "chatterbox-lock.json"
                )
            ).read_text()
        )
        if sys.version_info[:3] != tuple(int(x) for x in lock["python"].split(".")):
            raise RuntimeError("Candidate Python differs from its pin")
        torch = importlib.import_module("torch")
        np = importlib.import_module("numpy")
        soxr = importlib.import_module("soxr")
        if torch.__version__ != lock["torch"] or torch.version.cuda != lock["cuda"]:
            raise RuntimeError("Candidate PyTorch/CUDA differs from the selected pin")
        if args.configuration == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA configuration requires an available GPU; no fallback")
            free, _ = torch.cuda.mem_get_info()
            if free < 8 * 1024**3:
                raise RuntimeError("CUDA experiment requires 8 GiB free VRAM; no fallback")
        torch.set_num_threads(8)
        torch.set_num_interop_threads(1)
        random.seed(17)
        np.random.seed(17)
        torch.manual_seed(17)
        with contextlib.redirect_stdout(sys.stderr):
            candidate = importlib.import_module("chatterbox.tts_turbo")
            model = candidate.ChatterboxTurboTTS.from_local(
                args.state / "model", args.configuration, nano=True
            )
            model.prepare_conditionals(str(reference), exaggeration=0.0, norm_loudness=True)
    send(
        {
            "ready": True,
            "reference_id": args.reference_id,
            "reference_sha256": record["sha256"],
            "worker_pid": os.getpid(),
            "sample_rate": 16000,
            "source_rate": 24000,
            "configuration": args.configuration,
            "fixture": args.fixture,
            "preparation_seconds": time.perf_counter() - started,
            "conditioning_diagnostics": diagnostics,
        }
    )
    for line in sys.stdin:
        try:
            if len(line) > 10000:
                raise ValueError("Speech request exceeded its bound")
            request = json.loads(line)
            operation = request["operation"]
            fault = request.get("fault", "")
            if fault == "crash":
                os._exit(12)
            if fault == "delay":
                time.sleep(4)
            if fault in ("missing-reference", "missing-model"):
                raise ValueError(f"Experimental {fault}; restore the pinned asset and retry")
            begun = time.perf_counter()
            if operation == "begin":
                if not args.fixture:
                    torch.manual_seed(17)
                    resampler = soxr.ResampleStream(24000, 16000, 1, dtype="float32", quality="HQ")
                pcm = b""
            elif operation == "speak":
                text = request["text"]
                if not isinstance(text, str) or not text.strip() or len(text) > 1200:
                    raise ValueError("Expected 1–1200 characters of English text")
                if args.fixture:
                    pcm = b"\x01\x00" * 16000
                    samples = 24000
                else:
                    with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                        audio = model.generate(text, temperature=0.8, top_p=0.95, top_k=1000)
                    source = audio.detach().cpu().squeeze(0).numpy().astype("float32")
                    if source.ndim != 1 or not len(source) or not np.isfinite(source).all():
                        raise ValueError("Candidate returned invalid mono audio")
                    samples = len(source)
                    output = resampler.resample_chunk(source, last=False)
                    pcm = np.rint(np.clip(output, -1, 1) * 32767).astype("<i2").tobytes()
                elapsed = time.perf_counter() - begun
                send(
                    {
                        "pcm": base64.b64encode(pcm).decode(),
                        "metrics": {
                            "synthesis_seconds": elapsed,
                            "source_samples": samples,
                            "source_rate": 24000,
                            "output_samples": len(pcm) // 2,
                            "real_time_factor": elapsed / (samples / 24000),
                            "reference_id": args.reference_id,
                            "worker_pid": os.getpid(),
                            "whole_phrase": True,
                            "resampler": "continuous soxr HQ",
                        },
                    }
                )
                continue
            elif operation == "finish":
                if args.fixture:
                    pcm = b""
                else:
                    output = resampler.resample_chunk(np.empty(0, dtype="float32"), last=True)
                    pcm = np.rint(np.clip(output, -1, 1) * 32767).astype("<i2").tobytes()
                    resampler = None
            else:
                raise ValueError("Unknown speech operation")
            send({"pcm": base64.b64encode(pcm).decode()})
        except Exception as error:
            send({"error": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        send({"error": f"{type(error).__name__}: {error}"})
