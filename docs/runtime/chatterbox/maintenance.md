# Chatterbox maintenance review (#57)

Reviewed 9 November 2026. **Regular availability remains no-go.**
The isolated remediated candidate is an experiment, not production clearance.
`scripts/chatterbox_release.py` keeps normal enablement closed independently of
editable JSON flags, successful imports, or fixture results.

## Current installed environments and refreshed advisories

[Installed inventory](maintenance-installed-inventory.json) records the actual
112-distribution CPU and 112-distribution CUDA environments. Their runtime Torch
versions are 2.6.0+cpu and 2.6.0+cu124, with CPython 3.12.10. The CPU distribution
metadata says 2.6.0 while `torch/version.py` says 2.6.0+cpu; neither is silently
treated as a different base release for advisory lookup.

[Per-advisory review](maintenance-audit.json) refreshes every installed PyPI
package version using its public PyPI JSON endpoint and the referenced OSV
record, retaining advisory aliases, affected installed version, reported fixes,
applicability, remediation and acceptance state. It has **109 feed records in six
packages, representing 76 alias-deduplicated advisories**. The historical count
of 90 is neither current clearance nor 90 distinct defects. No exclusions or
warning-count baseline were added. No risk exception has been accepted.

| Existing pin | Distinct advisories | Remediation in the separate candidate |
| --- | --- | --- |
| torch 2.6.0 | 22 | Official Windows torch 2.14.1+cu130 wheel; base version audited |
| diffusers 0.29.0 | 3 | 0.42.1; reported fix floor is 0.38.0 |
| transformers 5.2.0 | 4 | 5.22.2; recheck the full affected range, including records without `fixed_in` |
| pillow 12.3.0 | 39 | 13.0.0 |
| gradio 6.8.0 | 3 | Remove the unnecessary UI/serving graph |
| starlette 0.52.1 | 5 | Remove the unnecessary UI/serving graph |

The existing adapter does not launch Gradio, call DiffusionPipeline, or accept
arbitrary model repositories. That narrows exposure; it is not a proof that all
affected code is unreachable. The review explicitly leaves unproved operator and
loader reachability unresolved. In particular, offline operation does not fix a
vulnerable unpickler: Perth loads its pinned checkpoint. Upgrade rather than
accepting these old pins by assertion.

## Source and update strategy

The [pinned source README](https://github.com/resemble-ai/chatterbox/blob/ab55923c27757c90cfcc407baa57dc25a7d25217/README.md)
states that upstream retired Chatterbox in August 2026. Its conflicting marketing
claims do not establish maintenance. The candidate therefore uses a **tHead-owned
reviewable patch series over an immutable upstream revision**, rather than
claiming upstream will provide updates. No suitable maintained replacement fork
has been verified here.

`patches/chatterbox-maintained.patch` changes the package metadata to
`0.1.7+thead.1`, selects updated inference dependencies, and restricts package
initialization to the English Nano profile. It removes Gradio and the unused
multilingual pykakasi/spacy-pkuseg dependencies. It preserves model architecture,
conditioning parameters and the real Perth watermark. Its canonical-WAV loader
uses SoundFile and the same float32/resampling path, avoiding librosa's deprecated
generic audioread backend discovery without suppressing that diagnostic.
The original CPU/CUDA
environments and working FlashHead source, wheels and assets are untouched.

The repository maintainer must explicitly accept responsibility for this source
profile before regular release. **No accountable maintenance/security acceptance
has been invented.** Proposed operating process: review upstream/archive/fork
changes and advisories monthly and before every release; triage newly published
critical advisories immediately; create a separate updated state/lock; rerun
strict imports, the concise two-reference preview, offline synthesis,
FlashHead compatibility and release recovery sequence; then review notices and
the enablement decision. Never mutate an installed working environment in place.

## Reproducible candidate

`chatterbox-maintained-lock.json` pins upstream/Perth/model revisions, exact model
sizes/SHA-256, Python 3.12.10, CUDA 13.0, Torch 2.14.1+cu130, and the local source
patch plus its expected changed-file hashes. Preparation rejects any other source
changes or mismatched assets and preserves them for diagnosis. The new
`requirements-maintained.lock` contains hashes for every acquired dependency;
source builds use the already locked build backends without dependency resolution.

The [official CUDA 13.0 Windows wheel index](https://download.pytorch.org/whl/cu130/torch/)
provides the selected Torch wheel. CUDA 12.8 stops at Torch 2.11.0 on this platform
and cannot supply the advertised 2.13.0 fix for CVE-2025-3000. The official
[TorchAudio 2.11.1 metadata](https://pypi.org/pypi/torchaudio/2.11.1/json)
declares `torch>=2.11`; this is the maintained pure-Python future-Torch-compatible
release. Its runtime version string is `2.11.1+cpu`; that does not substitute the
selected CUDA Torch inference device. The candidate checks CUDA availability and
at least 8 GiB free VRAM and fails explicitly without fallback.

[Candidate audit](maintenance-candidate-audit.json) queries all 81 installed PyPI
base versions and currently reports zero advisories. Chatterbox and Perth are
source projects reviewed separately, not silently counted as no-advisory PyPI
packages. There are 83 installed distributions in total.
[Candidate inventory](maintenance-candidate-inventory.json) records package
licence declarations, 222 licence/notice files and 189 native binary hashes.
These are inventory results, not final clearance of every bundled binary.

Python 3.12.10 is currently a declared installed-host prerequisite. Its version is
checked, but an independently hash-pinned Python distribution acquisition and a
current interpreter security review remain release work. The Python advisory
feed also does not audit the NVIDIA driver, CUDA DLLs, model weights or Windows.

## Licences and notices

Source/model/recording and binary obligations are distinct:

- Chatterbox and Perth declare MIT. Retain their copyright/licence notices and
  record local modifications. Attributed Apache/BSD/MIT source derivatives need
  their own notices; the top-level MIT declaration does not replace them.
- The [exact Nano model metadata](maintenance-model-metadata.json) declares MIT
  and an ungated public model. Retain the model card/revision and applicable
  notices when distributing weights; do not infer that all dependencies are MIT.
- The two bundled LibriSpeech reference excerpts are CC BY 4.0. Keep
  [ATTRIBUTION.md](ATTRIBUTION.md), the source attribution and change description.
  Personal imports require the user's ownership/permission record and are never
  committed or included in diagnostic logs.
- soxr is LGPL-2.1-or-later; SoundFile wheels include libsndfile and its licences.
  Retain notices and the relevant LGPL source/relinking obligations for any
  intended redistribution. The removed pykakasi package was GPL-3.0-or-later.
- Torch's BSD declaration does not license all bundled CUDA/cuDNN/numerical DLLs.
  Review the exact wheel's third-party notices and applicable NVIDIA redistribution
  terms before bundling. NumPy/SciPy wheels similarly contain separate numerical
  library notices. `maintenance-candidate-inventory.json` identifies installed
  binaries and their notice files; intended-distribution clearance is still open.

The application currently acquires these artifacts explicitly instead of shipping
them in its repository. That does not waive their conditions or grant blanket
redistribution clearance. No new legal/security exception was added.

## Preparation, application launch and concise native preview

Prerequisites: Windows 11, PowerShell 7, Git, uv 0.11.7, installed CPython 3.12.10,
RTX 3090 with a CUDA-13-compatible NVIDIA driver, 20 GiB free disk, 8 GiB free RAM
and 8 GiB free VRAM. Allow explicit network access to official package/source/model
hosts during preparation. This research command does not invoke an LLM or a paid
service. After the normal FlashHead prerequisites in README.md, this is the one
preparation-and-launch command from `C:/docs/git/tHead`:

```powershell
pwsh -NoProfile -File ./scripts/chatterbox-app.ps1 -Configuration maintained -Avatar chatterbox-nano-1089 -Output .runtime/chatterbox-maintenance-manual
```

It opens the explicitly experimental no-cost application at
`http://127.0.0.1:8767`. Ask `short-1`, then `multi-2`; expect audible complete
speech and a moving portrait, or a clear readiness/failure reason. Stop during
another answer, ask a replacement, then switch to Nikolle and Zira/Hazel. Append
`-SkipPreparation` after preparation to repeat with network disconnected. This
does not enable the regular app or certify the recovery timing gate by itself.

For the isolated one-passage quality regression preview:

```powershell
uv run --locked python scripts/chatterbox_eval.py --configuration maintained --prepare --reference docs/runtime/chatterbox/reference-1089-10s.wav --text 'Hello. This is a local voice preview. The final words should sound clear and complete.' --play
```

It prepares `.runtime/chatterbox-maintained` separately, validates hashes, performs
local CUDA synthesis and opens the synthetic WAV. Omit `--prepare` and disconnect
network access to repeat offline. Repeat once with `reference-121-10s.wav` for the
other accepted reference; the 74 unreviewed clips are not a new gate. Listen for
complete words/endings and any concrete regression against the accepted quality
verdict. A generated waveform alone is not human listening confirmation.

The command is bounded to three hours for preparation and 30 minutes for synthesis,
with task process-tree termination. Individual preparation processes are bounded
to one hour, transfers to 30 minutes. These are hang bounds, not latency targets.
Run one preparation/audition per state directory. Normal Zira/Hazel startup stays
available through `run.bat`; regular cloning enablement remains gated. A moving
portrait and <=5 s browser onset require the separate integrated native release
sequence; this standalone WAV preview cannot certify either.

## Investigation record and remaining gates

Baseline: historical unmaintained 2.6.0 CPU/CUDA environments, 90 stale advisory
records and 14–16 s killed-worker replacement onset. Success requires a current
accepted maintenance/security/licence profile plus <=5 s normal replacement
speech with a decoded moving frame, preserving offline inference and old voices.

1. Hypothesis: current official inference wheels can remove the old advisory
   dependency graph without changing model assets. Change: isolate current
   CUDA-13 Torch and updated inference dependencies with an English-only source
   patch. Measurement: the initial resolver tried legacy OmegaConf 2.3's source
   dependency and failed because inherited development Python settings selected
   incompatible typing modules. Conclusion: retain that failed attempt; use the
   existing compatible OmegaConf 2.4 binary-only dependency and clear inherited
   Python home/path inside subprocesses.
2. Hypothesis: the patched exact source can be prepared reproducibly. Change:
   acquire sources/dependencies/models in fresh state. Measurement: a generated
   patch initially mishandled an upstream file without a final newline; failed
   preparation logs are retained. Git-generated binary patch formatting fixes
   this. The final source hashes, 83-package compatibility check and all 81 PyPI
   advisory queries pass. Conclusion: native generation remains the next gate.
3. Hypothesis: the updated packages can import the real Nano class on Windows.
   Measurement: strict-warning import passes with Torch 2.14.1+cu130, CUDA 13.0,
   TorchAudio 2.11.1+cpu and CUDA available. Conclusion: this proves import/device
   discovery, not audio quality, FlashHead compatibility or conversational timing.
4. Hypothesis: strict-warning local synthesis works with unchanged model assets.
   Measurement: the first two preview attempts fail on audioread importing the
   deprecated Python `aifc` backend; the second follows a failed source-edit
   attempt caused by the shell's default text encoding, so it is not a distinct
   compatibility hypothesis. Change: decode only canonical WAV through SoundFile
   and retain the same resampling/conditioning. The final native previews pass
   with Python socket operations blocked. The first successful install command
   emitted uv's hardlink-to-copy diagnostic; final idempotent preparation uses
   the declared `UV_LINK_MODE=copy` and is warning-free. No diagnostic was hidden.

| Reference | Audio (s) | Conditioning (s) | Synthesis (s) | First complete PCM from fresh process (s) | Peak allocated / reserved (GB) |
| --- | --- | --- | --- | --- | --- |
| Peter / 1089 | 5.40 | 16.00 | 1.536 | 35.651 | 2.300 / 2.361 |
| Nikolle / 121 | 5.44 | 1.688 | 1.125 | 14.335 | 2.300 / 2.361 |

These are standalone fresh-process timings, not warmed browser onsets. First-use
conditioning/JIT work affects the Peter observation. Both outputs are
`generated_unreviewed`: no new human quality or physical-speaker verdict is
claimed. [Raw attempts and two short synthetic WAVs](maintenance-attempts/)
retain failures alongside successful results. The accepted historical quality
verdict remains unchanged unless listening establishes a concrete regression.

Native synthesis results and every failed compatibility attempt are retained in
the accompanying maintenance evidence. Regular release additionally requires
accountable update/security acceptance, interpreter and native-binary/licence
review, clean-checkout reproduction of the delivered commit, complete native
Stop/reset/crash/reference-switch measurements alongside FlashHead, and one
concise human listening/synchronisation confirmation. Until those pass, the
decision remains **no-go**. Browser digital onset must be reported separately
from physical-speaker latency; the latter has not been measured here.
