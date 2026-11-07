# Issue #2: native Windows loading investigation

Date: 7 November 2026. Target: construct the **actual FlashHead Lite pipeline**
on the installed RTX 3090, synchronize CUDA and verify that all three networks'
parameters are resident on CUDA. Import success alone is not readiness. No
generation, portrait preparation, media playback or latency claim is made here.

## Environment

- Windows 11 Home, build **26300**, native x64 processes.
- AMD Ryzen 5 7600 (6 cores), about **102.7 GB** visible system memory.
- NVIDIA GeForce **RTX 3090**, **24,576 MiB** device memory, WDDM.
- NVIDIA driver **621.14**; `nvidia-smi` advertises driver CUDA capability **13.5**.
  This is distinct from the CUDA **12.8** runtime in the installed PyTorch wheels.
- PowerShell **7.6.9**, uv **0.11.7**, bootstrap Python **3.12.10**.
- Initial free space about **764 GB**; disk capacity was not a blocker.
- Source/model revisions and every Python dependency are pinned in the delivered
  lock files. No globally installed Python packages or ComfyUI installation are
  used by the smoke test.

## Baseline and bounded investigation

The repository initially contained agent guidance only: no application, tests,
environment or model files. The investigation is bounded to five substantive
adaptation attempts against the loading target, stopping earlier on a clear
blocker. Package resolution corrections and download progress are observations,
not successful runtime results. Each setup/load subprocess has a finite timeout
with headroom, and GPU work is serial to avoid memory/timing contention.

1. **Hypothesis:** the upstream installation recipe is usable on Windows.
   **Measurement:** a non-installing binary dependency resolution probe:

   ```powershell
   uv pip install --dry-run --only-binary :all: --python .runtime/venv-upstream/Scripts/python.exe nvidia-nccl-cu12==2.27.3
   ```

   Result (exit 1):

   ```text
   Because nvidia-nccl-cu12==2.27.3 has no wheels with a matching platform
   tag (e.g., win_amd64) ... requirements are unsatisfiable.
   ```

   Published wheel platforms are Linux aarch64/x86_64. An unmodified source
   import in the initial Python 3.10 / Diffusers 0.34 / Transformers 4.57.3
   environment also exits 1 at `flash_head_model.py:11`:

   ```text
   from xfuser.core.distributed import (...)
   ModuleNotFoundError: No module named 'xfuser'
   ```

   **Conclusion:** the upstream dependency recipe is unsuitable as-is. The
   single-GPU path does not need NCCL or distributed attention.

2. **Hypothesis:** an eager single-GPU profile can avoid that platform-specific
   stack while retaining actual upstream model loading.
   **Change:** conditional distributed imports, lazy face-crop import and eager
   model/VAE configuration, all recorded in the patch.
   **Measurement:** the adapted import progresses past xFuser, then fails at
   `flash_head/utils/utils.py:8`:

   ```text
   import pyloudnorm as pyln
   ModuleNotFoundError: No module named 'pyloudnorm'
   ```

   **Conclusion:** inspection found that `pyln` is never used in that file, so
   remove that unused import in the recorded patch. Avoid installing the
   unrelated upstream training/UI stack. A real CUDA probe in the initial environment reported
   `2.10.0+cu128 True NVIDIA GeForce RTX 3090`.

3. **Hypothesis:** current patched model-library versions can load this source
   without carrying the vulnerabilities in upstream's older dependency recipe.
   **Change:** use Python 3.12.10 and the separately locked Windows runtime.
   Resolution established that Diffusers 0.38 requires Hub <2 whereas current
   libraries use Hub 2; current Diffusers requires Python >=3.11. The final pins
   therefore use a consistent newer stack. Pin patched filelock and setuptools
   explicitly because the CUDA index also supplies older transitive versions.
   **Measurement:** the adapted pipeline imports successfully. Constructing the
   **actual downloaded LTX VAE** on CUDA succeeds (`Actual LTX VAE loaded on
   cuda:0`). This validates one real component, not full pipeline readiness.
   **Conclusion:** these APIs support VAE construction. The final pipeline result
   remains the required gate.

4. **Hypothesis:** the real wav2vec2 ASR checkpoint can supply FlashHead's encoder
   on the revised runtime.
   **Measurement:** actual checkpoint loading, feature-extractor freezing and
   CUDA synchronization succeed (`Actual wav2vec2 loaded on cuda:0`). Transformers
   reports unused `lm_head.weight`/`lm_head.bias` and missing `masked_spec_embed`.
   **Change:** declare those exact expected keys on the encoder subclass, rather
   than suppressing model-load diagnostics globally. The CTC head is not used;
   masking is training-only unless explicit mask indices are passed. Require all
   pipeline networks to be in evaluation mode in the smoke command.
   **Conclusion:** the re-run loads the real audio encoder without that load report;
   other checkpoint differences are still visible. Re-review before audio inference.

### Acquisition observations

The Lite transformer file is about **6.11 GB**, the LTX VAE about **1.68 GB**.
Initial Windows directory metadata reported zero-length open partial files,
prompting a transport comparison and a retry with the requests-based Hugging
Face CLI 0.36.2. A direct 10 MiB HTTP chunk took about **2.9 seconds**. On closing
the initial SDK's files, **765/818 MB** of transferred data became visible. Thus
the initial observation did **not** prove the current SDK was stalled or broken.
Opening the active partial files and seeking to EOF gave reliable live lengths.

The isolated older CLI is retained for its tested ability to **resume** the large
downloads across an interrupted invocation; its lock is audited independently.
The current SDK uses process-unique temporary files and discards partial content
on ordinary failure. Disabling progress bars makes captured logs smaller; it is
not a demonstrated Windows compatibility fix. Both use the same public CDN;
no host, GPU or inference service was substituted.

## Runtime evidence

The reproducible invocation is the PowerShell command in
[the runtime guide](windows-smoke.md). The launcher records full stdout/stderr in
`.runtime/setup.log` and structured readiness in `.runtime/readiness.json`.
**Result: PASS — real native Windows CUDA loading on the RTX 3090.** The final
invocation exited **0** at 11:09 UTC. The saved
[machine-readable report](rtx3090-readiness.json) records:

| Observation | Result |
| --- | --- |
| Torch / Torchvision | 2.11.0+cu128 / 0.26.0+cu128 |
| Diffusers / Transformers | 0.42.1 / 5.22.2 |
| Python / CUDA runtime | 3.12.10 / 12.8 |
| GPU | NVIDIA GeForce RTX 3090 |
| Actual pipeline construction, including CUDA synchronization | **3.420 s** |
| Smoke process elapsed, including imports and provenance/file checks | **7.792 s** |
| Peak allocated / reserved device memory (PyTorch allocator) | **4.295 / 4.578 GB** |
| Last preparation invocation, resuming downloads with installed wheels | **648.968 s** |

Final output:

```text
READY: FlashHead Lite, LTX VAE and wav2vec2 loaded on native Windows CUDA
```

The loader verified all three real networks' parameters are on CUDA and all
networks are in evaluation mode. This is a fresh model process with OS filesystem
caches warmed by acquisition/component probes; **not a pristine cold setup or an
inference benchmark**. The whole investigation included earlier wheel downloads
(5 min 40 s for the initial environment, 5 min 23 s for the revised environment)
and interrupted/resumed model acquisition. Peak memory covers this process's
Torch allocator, not unrelated WDDM/driver allocations.

Additional command-boundary checks passed:

- Temporarily removing the real VAE `config.json` produced exit **1**, stage
  `model-files`, its exact missing path and no READY; the file was restored.
- A fresh upstream checkout with the expected patch plus an **unrelated staged
  source edit** produced exit **1**, stage `source`, and
  `Existing upstream edits differ from the recorded Windows patch`, before CUDA
  model loading. The review finding that led to this check is resolved.
- The final patch passed `git apply --check` against a fresh pinned source checkout
  under the host's actual Git/line-ending settings (Git 2.56.0.windows.4).

There is no remaining **loading** blocker in this tested profile. Video
generation/playback, audio processing, attention-kernel execution, compilation,
throughput, streaming and other GPUs remain untested. The result authorizes no
automatic hardware/runtime migration and establishes no conversational latency.

## Verification boundaries

The command-boundary seam was explicitly agreed with the user. The CPU test
executes the actual smoke command with a missing model directory and checks its
nonzero exit, absence of READY, and structured missing-component report. It does
not mock a pipeline. Successful readiness is established by the separate real
GPU run and its saved evidence, not synthetic unit tests.

The canonical verification command and CI cover the script/tooling gates. They
do not assert GPU feasibility on a GitHub-hosted runner without an RTX 3090.
All narrow Bandit B404/B603/B607 exceptions are beside the shell-free process
calls; commands are fixed tooling with distinct argv entries and time limits.
Review these exceptions if commands or executable selection become externally
controlled.

Canonical verification passed with no unresolved diagnostics. The development
and acquisition dependencies have no reported advisories; the runtime has the
[three distinct documented advisory exceptions](security-exceptions.md).
The Standards review found one source-provenance defect, fixed and re-reviewed;
the Spec review found no actionable deviations, including its focused review of
checkpoint/diagnostic exceptions. No unrelated user files are part of this change.
