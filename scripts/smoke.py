"""Load the real Lite pipeline; emit a machine-readable readiness result."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import logging
import os
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from prepare import check_source

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=ROOT / ".runtime/models")
    parser.add_argument("--source", type=Path, default=ROOT / ".runtime/FlashHead")
    parser.add_argument("--report", type=Path, default=ROOT / ".runtime/readiness.json")
    args = parser.parse_args()
    args.models = args.models.resolve()
    args.report = args.report.resolve()
    started = time.perf_counter()
    result: dict[str, Any] = {
        "status": "blocked",
        "stage": "model-files",
        "platform": platform.platform(),
        "python": sys.version,
    }
    try:
        lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
        result["lock"] = lock
        for model in lock["models"]:
            for filename in model["files"]:
                path = args.models / model["directory"] / filename
                if not path.is_file():
                    raise FileNotFoundError(f"Missing model component: {path}")
        result["stage"] = "platform"
        if sys.platform != "win32":
            raise RuntimeError("Native Windows is required; no WSL/CPU fallback")
        result["stage"] = "source"
        source = args.source.resolve()
        revision = check_source(source, lock["upstream_revision"])
        result["upstream_revision"] = revision
        result["stage"] = "cuda"
        # This notice concerns unused multi-process stderr redirection, not single-GPU CUDA.
        # Review when PyTorch removes it or this profile gains distributed execution.
        logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").addFilter(
            lambda record: (
                record.getMessage()
                != "NOTE: Redirects are currently not supported in Windows or MacOs."
            )
        )
        # Diffusers 0.42.1 warns even for an empty keep-fp32 list. No modules are affected.
        # Remove on a Diffusers fix; re-review if either model gains nonempty fp32 requirements.
        empty_fp32_notices = {
            f"There are modules in {name} that should be kept in float32: []. "
            "Casting directly with `to()` can lead to inconsistent results; "
            "set `torch_dtype` in `from_pretrained()` instead to keep these modules in float32."
            for name in ("CausalVideoAutoencoder", "WanModelAudioProject")
        }
        logging.getLogger("diffusers.models.modeling_utils").addFilter(
            lambda record: record.getMessage() not in empty_fp32_notices
        )
        torch = importlib.import_module("torch")
        result["packages"] = {
            name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "diffusers", "transformers")
        }
        result["cuda_runtime"] = torch.version.cuda
        if not torch.cuda.is_available():
            raise RuntimeError("Native PyTorch CUDA is unavailable")
        device = torch.cuda.current_device()
        result["gpu"] = torch.cuda.get_device_name(device)
        if "RTX 3090" not in result["gpu"]:
            raise RuntimeError(f"Expected RTX 3090; found {result['gpu']}")
        result["gpu_memory_bytes"] = torch.cuda.get_device_properties(device).total_memory
        torch.cuda.reset_peak_memory_stats()
        result["stage"] = "pipeline-load"
        sys.path.insert(0, str(source))
        os.chdir(source)  # Upstream inference reads its YAML relative to CWD.
        inference = importlib.import_module("flash_head.inference")
        load_started = time.perf_counter()
        pipeline = inference.get_pipeline(
            world_size=1,
            ckpt_dir=str(args.models.resolve() / "FlashHead"),
            model_type="lite",
            wav2vec_dir=str(args.models.resolve() / "wav2vec2"),
        )
        torch.cuda.synchronize()
        # Readiness requires all three actual networks to reside on CUDA.
        for network in (pipeline.model, pipeline.vae.model, pipeline.audio_encoder):
            if not all(parameter.is_cuda for parameter in network.parameters()):
                raise RuntimeError("A loaded pipeline component is not resident on CUDA")
            if network.training:
                raise RuntimeError("A loaded pipeline component is not in evaluation mode")
        result["load_seconds"] = time.perf_counter() - load_started
        result["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        result["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        result["status"] = "ready"
        result["stage"] = "complete"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        traceback.print_exc()
    finally:
        result["elapsed_seconds"] = time.perf_counter() - started
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
    if result["status"] == "ready":
        print("READY: FlashHead Lite, LTX VAE and wav2vec2 loaded on native Windows CUDA")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
