# Native Windows FlashHead Lite smoke test

## Run

Working directory: the root of a normal tHead checkout (on the measured host,
`C:/docs/git/tHead`). Prerequisites:

- Windows 11 x64, PowerShell 7, Git and Python available on `PATH`.
- uv **0.11.7** on `PATH`. The launcher uses the existing Python only to prepare
  a separate, pinned **Python 3.12.10** environment.
- An **RTX 3090 with 24 GB VRAM**, selected as the default CUDA device, with an
  NVIDIA driver supporting CUDA 12.8. Close GPU-heavy applications first.
- Internet access to GitHub, PyPI, the official PyTorch CUDA wheel index and
  Hugging Face. Allow at least 30 GB free disk space for wheels, extracted
  environments, source and weights. More is needed if preserving old attempts.
- A working Microsoft Visual C++ runtime for Python/PyTorch. No local CUDA
  compiler, Linux installation, WSL2 or hosted inference is used.

Run this one preparation-and-launch command in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/smoke.ps1
```

The launcher clones the pinned editable source, applies the recorded Windows
patch, installs hash-checked Windows binary wheels, downloads the pinned model
files, then constructs the real Lite pipeline on CUDA. It preserves existing
source edits and refuses unexpected revisions/patches. Model cards are downloaded
beside the weights. No Hugging Face login is needed for these public revisions.

Successful completion exits **0**, writes `.runtime/readiness.json` with
`"status": "ready"`, GPU name, package versions, load duration and peak allocated
and reserved CUDA memory, and ends with:

```text
READY: FlashHead Lite, LTX VAE and wav2vec2 loaded on native Windows CUDA
```

Failure exits **nonzero**, prints the exact error and stage and records diagnostics
in `.runtime/setup-result.json` (setup failure) or `.runtime/readiness.json`
(model-load failure). `.runtime/setup.log` contains the full command output.
Always check the current command's exit code and report: reports from earlier
runs are not evidence for a failed setup. Initial downloads can take many minutes;
installation/download stages have a 60-minute limit each, source/Python setup
10/15 minutes, and pipeline loading 15 minutes. A timed-out Windows subprocess
and its children are terminated. These are hang limits, not latency targets.

For manual verification, run the command above and confirm the final READY line,
exit code 0 and `gpu` naming the RTX 3090 in the JSON. Then temporarily move one
required model file aside and run the load-only command below; expect exit 1,
stage `model-files`, an exact missing-file path and no READY. Restore the file.
This failure check does not contact the network or reacquire weights:

```powershell
./.runtime/venv/Scripts/python.exe ./scripts/smoke.py
```

## Reproducibility and adaptations

`runtime-lock.json` pins source and model revisions and enumerates every acquired
file. `requirements-runtime.in` explains the selected top-level dependencies;
`requirements-runtime.lock` pins all transitives and wheel hashes. The installed
environment is local to `.runtime/venv`, with cache/model files under `.runtime`.
None of these large artifacts are committed.

Acquisition uses a separate `.runtime/download-venv` with the hash-locked
`requirements-download.lock` (Hugging Face CLI 0.36.2). The current runtime SDK
and its HTTP transport are isolated from this requests-based downloader. Both
dependency locks are audited by the canonical verification command.

The upstream source is Soul-AILab/SoulX-FlashHead at
`9bc03de06bb0de82cd6bc477804512ae06144bf2`. The loader calls upstream
`get_pipeline(world_size=1, model_type="lite")`; it does not substitute an empty,
mocked or alternative model. It checks that the transformer, VAE and audio encoder
parameters reside on CUDA and synchronizes CUDA before reporting readiness.

`patches/windows-eager-single-gpu.patch` records all source modifications:

- Avoid importing xFuser for an uninitialized single-GPU distributed context.
  Upstream otherwise imports its multi-GPU stack unconditionally, pulling in
  Linux-oriented NCCL/FlashAttention dependencies. Multi-GPU operation is outside
  this patched smoke-test profile.
- Disable model/VAE `torch.compile` for eager loading. This avoids assuming a
  working Windows Triton/compiler toolchain. Loading would not itself compile
  lazy kernels, so it cannot establish compiled inference compatibility.
- Import face cropping only if requested. Face detection is unnecessary for
  constructing the pipeline, so MediaPipe/OpenCV are excluded from this profile.
- Remove an unused `pyloudnorm` import from image/color utilities. No loudness
  processing call exists in that file; loading does not need the audio/UI stack.
- Mark only the unused CTC head and training-only mask embedding differences
  when loading the ASR checkpoint as an encoder. The readiness command requires
  evaluation mode for every network. See the exact exceptions below.

FlashAttention, SageAttention, xFormers, xFuser and NCCL are deliberately absent.
Upstream already has a native PyTorch scaled-dot-product-attention fallback.
This load test does not benchmark it or establish video quality/throughput.
FFmpeg, a portrait and sample audio are not needed until video generation.
PyTorch/Torchvision and the model libraries are newer than upstream's installation
recipe; their exact tested versions and outcomes belong in the evidence report.

## Notices

The editable checkout retains upstream's Apache-2.0 license, copyright headers
and acknowledgements. A copy of its license is in
`third_party/FlashHead-LICENSE`, and the local patch is identified above. The
upstream README credits Wan, LTX-Video, Self-Forcing, DMD and Self-Forcing++.
The source license does not replace separate weight/dependency terms. Preserve
the downloaded model cards and review their terms before redistribution; this
repository does not distribute model weights or binary dependency artifacts.
The pinned model card identifies the transformer and wav2vec2 as Apache-2.0 and
the **LTX-0.9 VAE as Open-RAIL-M**. Lite uses that VAE; preserve and comply with
its separate terms rather than relabeling the whole bundle Apache-2.0.

See [runtime security exceptions](security-exceptions.md) for three narrowly
scoped advisories in constrained Torch/setuptools versions. This load-only profile
does not use their affected compilation, packaging or installation operations.

## Evidence

See [the recorded investigation](investigation.md) for the actual host environment,
commands, errors, adaptations, timing and readiness result. Loading readiness is
the gate for this ticket; generated/played video and streaming remain untested.
