# Chatterbox maintenance review (#57)

Reviewed 9 November 2026. The exact remediated profile is approved for optional
native Windows / RTX 3090 use; see the [normal-app release evidence](../chatterbox-release.md).
`scripts/chatterbox_release.py` binds approval to the runtime, dependency and
source-patch digests. Any change fails closed pending renewed verification.
Historical experimental profiles and earlier failed attempts retain their original status.

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

The maintainers of `barnabyg/tHead` own this patch series and its dependency/model
pins as part of maintaining the application. Review upstream/archive/fork
changes and advisories monthly and before every release; triage newly published
critical advisories immediately; create a separate updated state/lock; rerun
strict imports, the concise two-reference preview, offline synthesis,
FlashHead compatibility and release recovery sequence; then review notices and
the enablement decision. Never mutate an installed working environment in place.
Any future risk exception must name the exact advisory/version, technical
mitigation, review condition and accountable acceptance. The current updated
package profile has no advisory exceptions and needs no separate ownership
permission step.

## Reproducible candidate

`chatterbox-maintained-lock.json` pins upstream/Perth/model revisions, exact model
sizes/SHA-256, Python 3.12.16, CUDA 13.0, Torch 2.14.1+cu130, and the local source
patch plus its expected changed-file hashes. Preparation rejects any other source
changes or mismatched assets and preserves them for diagnosis. The new
`requirements-maintained.lock` contains hashes for every acquired dependency;
source builds use the already locked build backends without dependency resolution.

Repeat preparation checks the complete installed distribution inventory against
all locked wheels and the two pinned source projects, and compares installed
Chatterbox/Perth package files with the verified source trees. A checkpoint binds
that verification to both current lock files; it is insufficient by itself.
Matching states skip sync/rebuild, while missing/extra/changed distributions,
changed pins or altered source content require strict sync and re-verification.
No `--inexact` allowance retains unwanted dependencies. An older state without a
checkpoint needs one initial verification/preparation under the new command.
Stop an application using the selected state before repairing its environment;
run only one preparation per state.
Retry resumes incomplete source acquisition from the exact pinned origin without
overwriting local edits, and re-extracts verified Python archives in fresh marked
staging while retaining legacy/unrecognized staging.
The acquisition-only diagnostic switches `-SourcesOnly` (maintained preparation)
and `-ExtractOnly` (Python preparation) stop before installation/runtime approval.

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
[Candidate inventory](maintenance-candidate-inventory.json) now records the exact
final CPython 3.12.16 installation used by the completed native normal-app
sequence: 83 distributions, 222 licence/notice files, 283 package DLL/PYD hashes,
55 interpreter native binary/executable hashes and 72 verified source-package
files. The final read-only source check preserves the preparation checkpoint.
The current [81-version advisory refresh](maintenance-candidate-audit.json)
again reports zero package advisories, with both source projects reviewed
separately. Earlier 3.12.10 observations remain in the initial native preview
reports and Git history.
The current delivery keeps those upstream notices in the acquired environment;
it does not redistribute a runtime bundle.

The current interpreter is independently acquired from Astral's immutable
`20261026` Python-build-standalone release. Preparation verifies the 22,014,416-byte
Windows x86-64 archive's SHA-256 before extraction or execution, preserves the
Python licence files, and builds the venv with that exact executable. There is
no system installation, PATH mutation or silent use of an installed Python.
`uv 0.11.7` predates this release, so acquisition uses the explicit pinned archive
rather than its older embedded download manifest.

[Interpreter security evidence](maintenance-python-security.json) records the
actual CPython 3.12.16 / OpenSSL 3.5.9 / Expat 2.9.0 probe and successful fresh
venv creation. The [Python security release](https://www.python.org/downloads/release/python-31216/)
includes the compromised-CA, Expat, archive-filter, Windows mimetypes and temporary
directory fixes missing from the old 3.12.10 installer. The current OpenSSL
advisory page lists fixes through 3.5.9. The same `cp312` wheel ABI is retained;
final native inference/release checks with this new interpreter are still
required. The original two preview measurements below used 3.12.10 and are
preserved as historical observations. Existing states with that interpreter fail
the new exact-version check; choose a fresh state rather than upgrading it in place.

Python package advisory queries do not audit the NVIDIA driver, all native DLLs,
model weights or Windows. The maintenance cycle checks the relevant upstream
release/security sources in addition to the package feed; zero package advisories
alone is never the whole security assessment.

[Native component review](maintenance-native-security.json) checks the current
NVIDIA primary bulletin index against the actual candidate tree. The November
2026 nvJPEG advisory and January 2026 Nsight advisories affect components absent
from this inference profile; no vulnerable library is merely called unreachable
because synthesis is offline. The installed cuDNN DLL version is 9.24.0.43, and
the measured host driver is 621.14. Component/profile changes trigger another
review; the review does not claim absence of unknown vulnerabilities.

## Licences and notices

Source/model/recording and binary obligations are distinct:

- Chatterbox and Perth declare MIT. Retain their copyright/licence notices and
  record local modifications. Attributed Apache/BSD/MIT source derivatives need
  their own notices; the top-level MIT declaration does not replace them. The
  distributed patch's Chatterbox copyright/licence is retained at
  `third_party/Chatterbox-LICENSE`, alongside `third_party/Perth-LICENSE` for the
  pinned watermark source. Downloaded sources retain all their original notices.
- The [exact Nano model metadata](maintenance-model-metadata.json) declares MIT
  and an ungated public model. Retain the model card/revision and applicable
  notices when distributing weights; do not infer that all dependencies are MIT.
- The two bundled LibriSpeech reference excerpts are CC BY 4.0. Keep
  [ATTRIBUTION.md](ATTRIBUTION.md), the source attribution and change description.
  Personal imports require the user's ownership/permission record and are never
  committed or included in diagnostic logs.
- [soxr](https://python-soxr.readthedocs.io/en/latest/#credit-and-license) is
  LGPL-2.1-or-later; [SoundFile](https://python-soundfile.readthedocs.io/en/latest/)
  is BSD-3-Clause and its wheel includes LGPL libsndfile. Their wheel-provided
  COPYING/licence files remain installed. Local use does not require publishing
  the application's source or a new source offer. If tHead later distributes
  these libraries' binaries, preserve their notices and LGPL terms, provide the
  corresponding source or permitted source offer, and preserve the user's
  ability to replace/relink the library as required by the chosen arrangement.
  That future binary-bundling change is separate from the current direct-upstream
  acquisition route. The removed pykakasi package was GPL-3.0-or-later.
- Torch's BSD declaration does not license all bundled CUDA/cuDNN/numerical DLLs.
  The [CUDA](https://docs.nvidia.com/cuda/eula/index.html) and
  [cuDNN](https://docs.nvidia.com/deeplearning/cudnn/backend/latest/reference/eula.html)
  agreements permit installation/use subject to their terms and separately limit
  redistribution to identified redistributable components and conditions. The
  current preparation acquires the official wheel directly on the user's PC;
  tHead does not republish the CUDA/cuDNN DLLs. Future bundling must check that
  specific component list, retain the notices and comply with the distribution
  conditions. NumPy/SciPy wheels similarly contain separate numerical
  library notices. `maintenance-candidate-inventory.json` identifies installed
  binaries and their notice files. Python's PSF and incorporated-library licences
  are retained with the independently acquired interpreter.

The repository distributes a reviewed patch, acquisition code and licensed
reference excerpts, while acquisition preserves upstream runtime licence files.
No concrete unmet licence obligation has been identified for this current route;
this is not a blanket authorisation to redistribute a future runtime bundle.
No new legal/security exception or separate licence approval step was added.

## Preparation, application launch and concise native preview

Prerequisites: Windows 11, PowerShell 7, Git, uv 0.11.7,
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
`generated_unreviewed` in their machine-generated reports. The user subsequently
confirmed both short previews acceptable in the tHead chat on 9 November 2026;
the historical accepted quality verdict remains valid. This is a human quality
check, not a physical-speaker latency measurement or a new broad sample gate.
[Raw attempts and two short synthetic WAVs](maintenance-attempts/)
retain failures alongside successful results. The accepted historical quality
verdict remains unchanged unless listening establishes a concrete regression.

5. Hypothesis: the supported current 3.12 security patch can be acquired without
   changing the model or wheel ABI. Change: pin Astral's immutable Python 3.12.16
   Windows archive, verify size/hash before execution, and use that exact Python
   for a fresh venv. Measurement: independent acquisition and strict native
   version/OpenSSL/Expat probes pass; a corrupt cached archive is rejected and
   preserved by the public preparation command. Conclusion: interpreter
   acquisition is reproducible without a preinstalled Python 3.12; final native
   speech/FlashHead release verification must use the new pin.
6. Hypothesis: avoiding source rebuilds for an exactly matching environment
   removes needless cache mutation during normal startup. The previous command
   strictly synced only wheel requirements, uninstalling both source projects,
   then rebuilt them on every invocation. The root's 10:28 native launch emitted
   a transient Windows cache-rename access denial; its cause is unknown. Change:
   check lock fingerprints, every distribution/version and the installed source
   package bytes, including Perth's checkpoint, before deciding to skip repair.
   Measurement: a fresh isolated venv passes in 57.124 s using copied verified
   caches; repeat preparation passes in 2.808 s without sync, build, reinstall or
   warnings. Deliberately added extra distribution and altered installed-source
   probes both trigger strict repair and return to the exact 83-package profile.
   Conclusion: normal matching preparation is idempotent without leaving drift
   unchecked. [Full observations and original warning](maintenance-attempts/idempotence-results.json)
   retain the controlled interrupted test-state preparation and the separate
   clean control. No warning filter or vulnerability exception was added.

Native synthesis results and every failed compatibility attempt are retained in
the accompanying maintenance evidence. Regular release additionally requires
clean-checkout reproduction of the delivered commit with the current interpreter, complete native
Stop/reset/crash/reference-switch measurements alongside FlashHead, and one
concise human listening/synchronisation confirmation. Until those pass, the
decision remains **no-go**. Browser digital onset must be reported separately
from physical-speaker latency; the latter has not been measured here.
