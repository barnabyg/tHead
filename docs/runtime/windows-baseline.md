# Phase 1: native Windows reproducibility baseline

Issue: [#4](https://github.com/barnabyg/tHead/issues/4). Measured 7 November 2026.
**Phase 1: PASS on the tested RTX 3090 profile.** Native CUDA generation and
clean-checkout startup with declared caches passed after the TLS fix below.
The user confirmed the new playback was audible, animated and approximately
in sync. Cache and measurement limitations remain explicit below.

## Reproduce and inspect

Working directory: the root of a normal checkout, such as `C:/docs/git/tHead`.
In PowerShell 7, run this single preparation-and-launch command:

```powershell
pwsh -NoProfile -File ./scripts/demo.ps1
```

Install Windows 11 x64, PowerShell 7, Git, a bootstrap Python, uv **0.11.7**,
the Microsoft Visual C++ x64 runtime and an NVIDIA CUDA-12.8-capable driver first.
Select the RTX 3090 as the default CUDA GPU. Allow at least 32 GB free disk and
network access to GitHub, PyPI, the PyTorch CUDA wheel index, Hugging Face and its
download CDN, `www.gyan.dev` and `upload.wikimedia.org`. Enable an audible output
device. Close previous players and GPU-heavy applications before running.

The launcher acquires the source, wheels, weights, FFmpeg and public-domain JFK
inputs declared in `runtime-lock.json`, `requirements-runtime.lock`,
`requirements-download.lock` and `demo-lock.json`. No personal input, Hugging Face
login, system FFmpeg, local CUDA compiler or external inference service is needed.
See [the demo guide](windows-demo.md) for provenance, licences and exact settings.

Manual scenario: watch and listen to the six-second synthetic JFK portrait.
Expect audible English speech, visible mouth/head animation and approximate
mouth/speech alignment at onset and end, without conspicuous lag or drift.
FFplay should close automatically. Exit 0 and successful decode establish
process/media validity; human observation establishes audible/visible quality.
The resulting file is `.runtime/demo/clip.mp4`; reports are
`.runtime/demo-result.json`, `.runtime/clip-result.json`, `.runtime/readiness.json`
and `.runtime/setup-result.json`, with `.runtime/demo.log` for diagnostics.

## Measurement method and cache boundaries

The clean checkout was cloned locally with `git clone --no-hardlinks --no-checkout`
and detached at `c1f9c5bf38c9cd52e27ebf2cf6c6f4833c5870bd` under
`.runtime/issue-4-clean`. Before launch, `git status --porcelain
--untracked-files=all` was empty and its `.runtime` directory did not exist.
Only committed files were cloned; neither the parent checkout's ignored runtime
nor its untracked `.scratch` and `docs/specs` directories were copied.

For that first attempt, preparation set checkout-local `UV_CACHE_DIR` (`.runtime/uv-cache`),
`UV_PYTHON_INSTALL_DIR` (`.runtime/python`) and `HF_HOME` (`.runtime/hf-cache`).
Weights and their local download metadata live in `.runtime/models`; runtime and
downloader environments in `.runtime/venv` and `.runtime/download-venv`; media and
inputs in `.runtime/media` and `.runtime/demo-inputs`. None was prepopulated or
linked to the earlier experiment. The host already had bootstrap Python 3.12.10,
which uv can use rather than downloading another interpreter. Windows filesystem,
DNS and remote CDN caches were not cleared; this is an empty application-cache
installation, not a reboot-cold disk or network measurement.

That attempt failed at FFmpeg acquisition after successful installation and model
readiness. To isolate generation, three media files from the earlier demonstration
were temporarily copied in: `ffmpeg.zip`, `portrait.jpg` and `speech.ogg`, each
checked against `demo-lock.json`. The seeded launcher generated, decoded and
played a clip successfully. These supplemental runs do not prove fresh acquisition.

After the TLS fix was committed as `7d9f32b937910020bdd2c95cc589c3a0797ccb5f`, a
second local clone, `.runtime/issue-4-final`, was detached at that commit. Its
initial `git status --porcelain --untracked-files=all` was empty. Only two caches
were supplied explicitly, as Windows directory junctions to the first experiment:

- `.runtime/uv-cache` targets `C:/docs/git/tHead/.runtime/issue-4-clean/.runtime/uv-cache`.
- `.runtime/models` targets `C:/docs/git/tHead/.runtime/issue-4-clean/.runtime/models`,
  including pinned weights and Hugging Face download metadata.

No source checkout, installed environment, media archive, extracted tools or input
files were copied into this final checkout. The normal launcher cloned/patched
upstream, created both environments, downloaded all three media/input assets,
generated, validated and launched playback. This establishes clean-checkout
startup **with declared wheel/model caches**. A single fully empty-cache run of
the final revision was not repeated: the earlier attempt already acquired the
unchanged runtime/model locks from empty application caches.

Timing boundaries:

- Cold preparation: `setup-result.json` elapsed time, including source acquisition,
  patching, environment creation, wheel/model downloads and a readiness process.
- Model loading: `load_seconds` surrounds actual upstream pipeline construction,
  CUDA synchronization and CUDA/evaluation checks. It excludes Python imports
  and source validation. The readiness process elapsed time includes those.
- Warm generation: three repeated fresh `generate_clip.py` processes in the final
  checkout, after successful
  preparation, with source, dependencies, models, media, inputs and OS file caches
  warm. Each process still loads the models. `inference_seconds` excludes model
  loading and image preparation, and includes audio embeddings, seven generation
  chunks, GPU-to-CPU frame copies, raw-file writing and final synchronization.
  It is not a persistent resident-model or steady-state streaming measurement.
- Generation process elapsed time additionally includes imports, provenance and
  input checks, model/image preparation, encoding, probing and full decode.
  Launcher elapsed time also includes preparation, asset checks and playback.
- Peak allocated/reserved bytes are this process's PyTorch CUDA allocator maxima
  since reset before loading. They exclude unrelated WDDM/driver allocations and
  do not measure whole-device peak consumption.

GPU runs are serialized because they share the RTX 3090 and memory/timing
measurements. No competing task-owned GPU workload is launched. The Windows
desktop remains active under WDDM; background desktop activity cannot be excluded.
CPU verification runs after GPU measurements to avoid additional contention.
The launcher already bounds preparation, generation and media subprocesses; the
outer cold-run wrapper additionally imposes a 24,000-second process-tree deadline.

## Host, inputs and software

| Component | Measured configuration |
| --- | --- |
| OS | Windows 11 Home x64, build 26300; native processes |
| CPU / RAM | AMD Ryzen 5 7600, 6 cores; 102.666 GB visible RAM |
| GPU | NVIDIA GeForce RTX 3090, 25.7698 GB / 24,576 MiB VRAM, WDDM |
| Driver / CUDA | NVIDIA 621.14; driver capability 13.5; Torch runtime 12.8 |
| Power limit | 280 W reported by `nvidia-smi` |
| External tools | PowerShell 7.6.9, Git 2.56.0.windows.4, uv 0.11.7, bootstrap Python 3.12.10 |
| Visual C++ runtime | x64 v14.51.36247.00, installed |
| Disk | Approximately 754 GB free before preparation |
| Runtime | Python 3.12.10; Torch 2.11.0+cu128; Torchvision 0.26.0+cu128 |
| Model libraries | Diffusers 0.42.1; Transformers 5.22.2 |
| Media tools | Gyan FFmpeg/FFprobe/FFplay 9.0.2 essentials x64 |
| Input | JFK portrait; inaugural address seconds 31–37, six seconds mono 16 kHz PCM16 |
| Generation | Lite, 512 × 512, 25 fps, four denoising steps, seed 42, bfloat16, eager, native Torch attention |
| Output | 150 H.264/yuv420p frames, six seconds, CRF 18, no B-frames, AAC mono 16 kHz, MP4 faststart |

The source revision is `9bc03de06bb0de82cd6bc477804512ae06144bf2`, with exactly
`patches/windows-eager-single-gpu.patch` applied. Model revisions and complete
transitive dependency pins/hashes remain in the tracked locks; the accompanying
machine-readable report embeds the runtime lock and actual installed versions.
CUDA 13.3 is also installed on this host but is not used to compile anything in
this workflow. The desktop and earlier experiment can warm OS caches. The parent
checkout's original demo runtime supplied media only for the explicitly seeded
supplement; none of its files supplied the final clean-startup check.

## Results and conclusion

Detailed machine-readable evidence: [RTX 3090 baseline](rtx3090-baseline.json).

| Attempt / boundary | Seconds | Result |
| --- | ---: | --- |
| Initial empty-cache preparation, including readiness | 1336.213 | Real models ready |
| Initial model construction / entire readiness process | 4.232 / 14.202 | CUDA/evaluation checks passed |
| Initial launcher | 1336.558 | Exit 1, media TLS validation failed |
| Supplemental seeded-media launcher, including playback | 32.729 | Exit 0; cached media, not fresh acquisition |
| Final clean-checkout preparation, wheel/model caches supplied | 25.865 | Environments/source prepared, models ready |
| Final readiness model construction / entire process | 4.302 / 14.100 | CUDA/evaluation checks passed |
| Final launcher, fresh media/input downloads and playback | 63.209 | Exit 0; generation, decode and player passed |

Do not add these attempt durations together and call the sum a measured cold
launch. The initial preparation took approximately 22 minutes, largely acquisition;
the final preparation benefited from the declared caches.

| Warm run | Model load (s) | Inference (s) | Generation process (s) | Peak allocated (GB) | Peak reserved (GB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 3.418 | 4.486 | 12.889 | 5.345 | 5.943 |
| 2 | 3.414 | 4.500 | 12.842 | 5.345 | 5.943 |
| 3 | 3.392 | 4.529 | 12.904 | 5.345 | 5.943 |

Warm inference median **4.500 s**, range **4.486–4.529 s**,
for six seconds of audio; each run generated 168 frames and muxed/decoded a
six-second, 150-frame clip. All runs passed codec, dimensions, duration, stream
start-time and full decode checks. Memory units above are decimal GB; exact bytes
and each pre-run GPU snapshot are in the report. These are process allocator peaks,
not an assertion that this much total device memory is sufficient.

### Diagnosed acquisition failure and fix

The original launcher exited 1 at `media-acquisition` with:

```text
URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired (_ssl.c:1010)>
```

Hypothesis: bootstrap Python's default CA selection includes an expired trust
path. Default-trust HEAD requests to Gyan and Wikimedia repeated the TLS error.
Using the hash-locked downloader's certifi bundle, Gyan returned HTTP 200.
Wikimedia rejected a generic HEAD with HTTP 403, but GET requests using the demo's
actual user agent returned HTTP 200 with the same validated CA bundle.
This isolates CA selection as the observed TLS difference; the exact expired
certificate in the host trust chain was not identified.

Change: `scripts/demo.py` supplies that existing bundle to
`ssl.create_default_context(cafile=...)` before media acquisition. Certificate
and hostname checks remain enabled. No new dependency, host certificate change,
TLS bypass or hash exception was introduced. The final committed clean-checkout
launcher then acquired all three assets from empty media/input directories and
completed generation, decode and FFplay playback. The technical blocker is resolved.

### Playback confirmation and conclusion

Both the seeded and final launchers opened real FFplay and exited 0.
The earlier issue #3 evidence records the user's direct confirmation on this host:
"Speech and animation are in sync." That applies to the earlier clip/profile;
it is not a fresh listening check for these baseline outputs. In response to the
new baseline playback check, the user confirmed on 7 November 2026:
"Audible, animated, approximately in sync." This completes the manual check for
this demonstration; it is not a separate qualitative assessment of every timed run.

**Conclusion: Phase 1 PASS with declared caches and confirmed playback.** The
tested native Windows profile generates and plays the talking-head demonstration
on the RTX 3090. No remaining native CUDA, media-acquisition or observed playback
blocker was reported. Phase 2 streaming feasibility can now be investigated;
the later conversational latency target remains unproven.

## Verification and retained artifacts

Focused formatting, lint, strict typing and both CPU command-boundary tests passed
for the TLS fix. The canonical verification command is
`uv run --locked python scripts/verify.py`; GPU evidence is separate because hosted
CI has no RTX 3090. No new suppression or advisory exception was added.

The two experiment clones, their caches, logs, generated MP4s and raw JSON reports
are retained under ignored `.runtime/issue-4-*` paths for replay and diagnostic
inspection. They are local evidence, not a delivery
dependency. The final clone has junctions into the first clone's caches; preserve
those targets until the experiment is no longer needed. Unrelated `.scratch`
and `docs/specs` files were left untouched. No remote branch was pushed.

## Limits and next decision

This is one host, portrait, recorded English passage, seed and eager single-GPU
profile. It does not validate another GPU, Windows build, driver, model revision,
long input, arbitrary resolution, distributed execution or compiled kernels.
The Windows adaptations avoid upstream's Linux-oriented NCCL/xFuser stack and
use newer pinned libraries; they are not proof that upstream's unmodified recipe
works. Model and dependency notices, including the narrowly scoped existing
security exceptions, remain in [the smoke guide](windows-smoke.md) and
[security exceptions](security-exceptions.md). No exception is introduced here.

Acquisition still requires externally reachable pinned URLs. A future missing
URL, changed asset hash, CDN failure or unavailable wheel is a reproducibility
blocker even when a cached run succeeds. This local clone tests committed content
and setup/startup; it does not independently test GitHub authentication or remote
cloning by another user. The only executable change is media acquisition's choice
of CA bundle; model locks, the upstream patch and inference code are unchanged.
The final checkout ran the committed executable tree; subsequent baseline
documentation does not alter it.

Decode and FFprobe checks detect container/codec/timing errors, not perceived
speech quality or lip synchronisation. Human playback inspection is qualitative,
not an instrumented lip-sync offset measurement. Three warmed samples describe
this session, not an SLA, a tail-latency distribution or a thermal endurance run.

Phase 2 must measure time to first playable synchronised segment, incremental
audio/state continuity, segment boundaries, longer clips, stalls and cancellation.
There is no TTS, LLM, browser conversation or persistent resident-model service in
this measurement. No conclusion about the later 3–5 second Submit-to-speech
target, or a need to move to the RTX 4090, follows from this offline clip timing.
