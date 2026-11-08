# Chatterbox evaluation (#52–#54)

Evaluated on native Windows 11 / RTX 3090, 8 November 2026. This is an
isolated research audition, not an application voice or approval to ship cloning.

## Gates

| Issue | Verdict | Evidence / remaining condition |
| --- | --- | --- |
| #52 native setup | Pass; issue closed 8 November 2026 | Fresh local clone, independent caches/venvs, identical output digest, offline synthesis and explicit user confirmation of an intelligible complete utterance |
| #53 voice quality | User judged the four-clip initial screen acceptable; broader gate scope pending | Scores A 2/4, B 3/4, C 3/4, D 3/4 (similarity/naturalness), all complete; [verdict and full evidence](chatterbox-quality.md) |
| #54 integration/adoption | Deferred | Requires #53 to close with a passing verdict; no adapter, GPU benchmark or production UI added |

Do not adopt on this evidence. Native setup alone establishes neither similarity
nor conversational performance. The candidate dependency audit has unresolved
security findings; normal tHead remains on its existing environment and voice path.

## Run the audition

Prerequisites: Windows 11, PowerShell 7, Git, uv 0.11.7, access to GitHub,
PyPI and Hugging Face during preparation, at least 20 GiB free disk and 8 GiB
free RAM. Python 3.12.10 is selected by uv, installed if absent. No account,
token, gated model approval, paid service or training is required. The CPU
configuration uses eight intra-op threads and one inter-op thread.

From **`C:/docs/git/tHead`**, one preparation-and-launch command:

```powershell
uv run --locked python scripts/chatterbox_eval.py --prepare --reference docs/runtime/chatterbox/reference-1089-10s.wav --text 'Hello. This is a local text to speech demonstration. The avatar should speak this passage clearly, then finish without repeating any words.' --play
```

Replace `--reference` with your own appropriately licensed/self-recorded WAV and
`--text` with new English text. Do not commit private recordings. Reference
preconditions: complete mono PCM16 WAV, one clean speaker, longer than 5 and
at most 30 seconds, 16/22.05/24/44.1/48 kHz, at most 12 MiB. This harness does
not detect noise, music, multiple speakers, clipping or non-English speech.
The selected upstream variant rejects exactly 5 seconds, resamples to 24/16 kHz,
uses up to 10 seconds for decoder conditioning and 15 seconds for speech tokens;
the voice encoder sees the full supplied recording. Longer input is not proof
that all conditioning uses 20 seconds.

Expected: preparation checks disk/RAM and source pins, creates a separate
`.runtime/chatterbox-eval/venv`, verifies asset hashes, generates a mono 24 kHz
PCM16 `speech.wav` and `result.json` in a new `.runtime/chatterbox-eval/auditions/`
directory, and opens the WAV. Listen for every word and a complete ending.
Five focused no-cost CLI tests cover missing reference, unsupported minimum
length, malformed WAV, empty text and missing assets. Errors identify the
problem; missing assets never cause an implicit download. Omit `--prepare` for
offline re-use. `--seed 17` is the initial repeat; use other seeds for quality
experiments. `--output` must name a new directory, preserving previous attempts.

The command bounds preparation to three hours (individual transfers: 30 minutes)
and synthesis to 30 minutes, with process-tree termination on timeout. These are
hang limits, not performance targets. Run one preparation/audition per state
directory at a time. GPU configurations are deliberately unavailable in this pin.
PowerShell validates before acquisition; interrupted or mismatched source/assets
are preserved and require a fresh `--state` directory rather than silent repair.

Normal startup remains `pwsh -NoProfile -File ./scripts/conversation.ps1`.
No avatar data format, Zira/Hazel reference, working FlashHead source, model cache
or environment is changed by the audition command. This claim concerns changed
code paths; a new integrated browser regression benchmark has not been run here.

## Provenance, maintenance and selection

Source: [Resemble AI's archive at the evaluated revision](https://github.com/resemble-ai/chatterbox/tree/ab55923c27757c90cfcc407baa57dc25a7d25217).
Its README explicitly says retired since August 2026, without maintenance,
support or updates. The same document still promotes production use and a paid
TTS service, contradicting its retirement notice. The Nano model card also
retains promotional service/throughput claims. Treat these as stale claims,
not maintenance or host measurements.

Choose **Nano**, English, CPU first: upstream describes a 110M backbone intended
for constrained CPU use. Its full selected assets are considerably larger than
that headline: **1,941,941,067 bytes**. Turbo's 350M backbone and original's 500M
variant are deferred because they increase the initial resource experiment;
neither has been downloaded or benchmarked. No multilingual pack was acquired.
The claimed three-times-realtime CPU speed is not used as a measured result.

Pins and per-asset sizes/SHA-256 are in [chatterbox-lock.json](../../chatterbox-lock.json).
The official Nano model is [revision 71ccd1d](https://huggingface.co/ResembleAI/chatterbox-nano/tree/71ccd1d0081b430592cea481f4307e764e07bc64).
Perth is [revision ff1c8ac](https://github.com/resemble-ai/Perth/tree/ff1c8ac55a976971245cdd53c18d6131ca00d993),
pinned instead of upstream's moving `master` dependency. The environment is
CPython 3.12.10, PyTorch 2.6.0+cpu, torchaudio 2.6.0, **no CUDA runtime**.
[Hash-locked dependencies](chatterbox/requirements.lock) include build backends;
[the compatible Windows wheel inventory](chatterbox/wheel-inventory.json) records
110 wheels totalling **417,444,651 bytes**, excluding the two source-built projects.
These are artifact sizes, not measured network traffic. Git transport sizes and
an automatically installed Python distribution's transport size were not measured.

Before acquisition the host reported 756.9 GB free disk, 100,259,736 KiB visible
RAM / 87,141,828 KiB free, RTX 3090 24,576 MiB VRAM / 23,505 MiB free, driver
621.14. CPU synthesis does not allocate a candidate CUDA model. Do not assign
other processes' VRAM to Chatterbox. FlashHead pins Python 3.12.10 / torch
2.11.0+cu128, while this source pins torch 2.6.0. Both support Python 3.12 here;
the conflicting dependencies require a separate subprocess/environment.
Upstream's documented development platform is Python 3.11 / Debian 11.

## Licences, watermark and security

Chatterbox source, the Nano model card and Perth declare MIT. Retain their notices
with any redistribution. Source contains attributed derivatives (including
CosyVoice/S3Tokenizer Apache-2.0 and other BSD/MIT components); the top-level MIT
label is not a substitute for those notices. No wheel/model binaries are bundled
with tHead; the command acquires pinned upstream artifacts.

[Installed dependency licence metadata](chatterbox/dependency-licenses.json)
covers all 112 distributions. Most declare MIT/BSD/Apache/ISC/PSF variants, but
**pykakasi 2.3.0 is GPL-3.0-or-later**, **soxr 1.1.0 is LGPL-2.1-or-later**,
certifi/orjson/tqdm include MPL terms, and native wheels include additional
notices (for example libsndfile in SoundFile, numerical libraries in NumPy/SciPy).
These require review for the intended redistribution/linking arrangement before
production; an isolated research installation does not make the combined stack
MIT-only. Inventory metadata is not a completed production licence clearance.

Perth's real `PerthImplicitWatermarker` is retained and applied by upstream
`generate`; it is never replaced by a dummy/no-op. Its bundled 37,429,684-byte
checkpoint comes from the pinned Perth Git tree. The checkpoint is loaded by
upstream PyTorch code; use only that reviewed source, not arbitrary pickle files.
The harness excludes `conds.pt` and rejects unexpected `.pt` model files.
WAV export quantises the upstream watermarked float audio to PCM16. Watermark
robustness/detection after export has not been measured.

[The recorded dependency audit](chatterbox/dependency-audit.json) reports **90
known advisories in six packages**: torch 2.6.0 (25), diffusers 0.29.0 (5),
transformers 5.2.0 (6), gradio 6.8.0 (5), pillow 12.3.0 (39), starlette 0.52.1
(10). These are unresolved candidate findings, **not suppressed advisories or
an approved production baseline**. No Gradio server is launched. Offline inference
reduces exposure but does not resolve vulnerable dependencies or the absence of
upstream fixes. Production adoption requires a maintained, re-audited dependency
plan; this evaluation must not be wired into normal startup meanwhile.

The manual candidate emitted an upstream `LoRACompatibleLinear` FutureWarning from
diffusers/models/lora.py:393. The harness now filters only that exact message,
FutureWarning category and module: the pinned S3Gen needs this compatibility
layer and inference is unaffected. Remove/review the filter when the source/model
or diffusers pin changes. Other warnings are unaffected. A narrow Bandit B606 exception permits opt-in OS playback
of the fixed generated WAV; review it if that file type changes.

## Setup measurements and investigation log

1. **Hypothesis:** a smaller pinned model can work on native Windows without
   modifying FlashHead. **Change:** resolve upstream dependencies into a separate
   Python 3.12 environment and load Nano on CPU. **Measurement:** successful import
   and local model readiness in 13.578 s, output rate 24 kHz. **Conclusion:**
   Python 3.12 is viable; the candidate still needs synthesis and reproduction.
2. **Hypothesis:** the model CLI can acquire all pinned assets. **Change:** download
   only nine required files. **Measurement:** metadata arrived first; weights made
   no visible progress initially, but completed after 353 s. A parallel direct
   HTTPS diagnostic transfer also completed with identical hashes. **Conclusion:**
   an initial apparent stall was not a permanent acquisition failure. The delivered
   preparation uses bounded HTTPS transfers and validates size/hash.
3. **Hypothesis:** conditioned generation works offline with watermarking intact.
   **Change:** use a licensed 10-second reference, new baseline passage, seed 17,
   eight CPU threads and blocked Python socket operations. **Measurement:**
   [first result](chatterbox/setup-result.json), 8.64 s audio, synthesis 6.407 s
   (RTF 0.742), first complete PCM 29.799 s after worker start, including import,
   reference/model setup and first-use work. **Conclusion:** local non-streaming
   synthesis works. The user explicitly confirmed “Intelligible and complete”
   in this chat on 8 November 2026. This is not a similarity/naturalness score.
4. **Hypothesis:** the single preparation command reproduces the environment.
   **Change:** hash-locked sync plus local pinned-source builds. **Measurement:**
   the first command exposed inherited development `PYTHONHOME` (3.13) contaminating
   the candidate's 3.12 build; clearing that setting in the preparation subprocess
   fixed it. The completed command produced the same WAV digest, with first PCM
   16.993 s, conditioning 1.308 s and synthesis 6.432 s. **Conclusion:** a dedicated
   subprocess is necessary; this repeat is filesystem/cache warm, not a clean
   checkout or persistent warmed conversation turn.
5. **Hypothesis:** tracked files alone can reproduce preparation and speech.
   **Change:** clone local commit `64ae0fd` with `git clone --no-local --no-hardlinks`
   into `.runtime/chatterbox-clean-checkout`; run the documented command with
   empty bootstrap/candidate caches and no existing virtual environments. The
   installed host interpreters and uv/Git/PowerShell remain declared prerequisites.
   **Measurement:** 112 candidate packages installed, all pinned model assets
   freshly downloaded/verified; [clean result](chatterbox/clean-result.json)
   produces the exact previously auditioned WAV digest. Import 47.118 s,
   model ready 50.444 s, conditioning 10.062 s, synthesis 6.487 s, first complete
   PCM 66.993 s. This correctness reproduction ran alongside CPU checks, so its
   cold timings are observations under contention, not an isolated benchmark.
   **Conclusion:** native clean-checkout setup passes. The subsequent warning-filter
   and exception-comment fixes do not change dependencies, model assets or synthesis.

The first audition ran under network-restricted execution.
[A same-interpreter HTTPS probe](chatterbox/offline-probe.json) failed DNS resolution.
Additionally, inference sets Hugging Face/Transformers offline flags and rejects
Python socket DNS/connect/send operations, including lazy downloads. No unexpected
Python network attempt occurred in successful synthesis. This is not a packet
capture or proof about arbitrary native libraries' networking.

## Reference and delivered sample

[Reference excerpt](chatterbox/reference-1089-10s.wav) and
[synthetic output](chatterbox/setup-speech.wav) are openly distributable evaluation
assets, not private recordings. Reference: LibriSpeech test-clean,
**Peter Bobbe, reader 1089**, utterance `1089-134691-0009`, first exactly 10 seconds
of its 20.055-second mono 16 kHz recording, decoded from FLAC to PCM16 WAV without
other processing. Original FLAC SHA-256 is recorded in the attribution file.
Read speech from a LibriVox audiobook; recording equipment/acoustic conditions
are unknown, and accent was not independently classified. The new synthesis
passage is absent from its reference transcript.

Attribution: Vassil Panayotov, Daniel Povey, Guoguo Chen and Sanjeev Khudanpur,
LibriSpeech, derived from LibriVox; [OpenSLR resource 12](https://www.openslr.org/12),
**CC BY 4.0**. See [asset attribution](chatterbox/ATTRIBUTION.md).

## Verification and remaining work

Canonical command: `uv run --locked python scripts/verify.py` passed during
implementation (including 38 browser tests); the exact post-review handoff result
is recorded in the chat. Focused CLI tests, Ruff, strict mypy and static security
checks run during implementation. No main-runtime dependency or security
exception is changed. Manual scenario: run the documented command, listen to the
complete passage, retry without `--prepare`, then supply a missing/invalid WAV
and expect an explicit error. A newly generated WAV is always unreviewed until
a human listens; the command never grants a quality gate itself.

The code review against starting commit `4e77a5d` found no substantive spec defect.
Both concrete standards findings (the exact upstream warning and subprocess
analysis-exception documentation) were fixed and independently rechecked. The
remaining acquisition-inventory limitation is explicit above: Git/Python transport
bytes were not measured. This does not establish a production security clearance.
The reviewed launcher was also rerun in the clean clone: identical WAV digest,
with no warning output. Temporary clone/caches and duplicate diagnostic weights
were removed after preserving reproduction logs; the primary audition environment
is retained for re-use.

Clean-checkout preparation/generation and the explicit setup listening verdict pass.
The two-speaker repeated-condition #53 pack is delivered. The user explicitly
accepted the four-clip initial screen; the remaining 74 clips are unreviewed.
The prototype-gate scope is pending confirmation, rather than a negative quality
verdict. #54's browser/media latency, cancellation, recovery,
reference lifecycle, RAM/VRAM and continuous resampling checks remain untested.
Do not extrapolate these isolated whole-utterance CPU measurements to FlashHead.

## Integration and adoption decision (#54)

**No adoption at present. Integration evaluation is deferred, not passed or
technically rejected.** Issue #54 explicitly requires #53 to close with a passing
human quality verdict. The user judges the four-clip initial screen acceptable,
with all utterances complete. The remaining matrix is unreviewed, and #53 has not
yet closed with an agreed prototype-gate scope. This is not a negative quality
outcome; the written stage dependency is still pending. The retired upstream and 90 candidate dependency advisories also
remain material adoption risks; no production security/licensing clearance exists.

| Adoption requirement | Evidence/status |
| --- | --- |
| Native reproducibility | Pass; #52 closed with explicit user listening confirmation |
| Two-speaker quality and reference preparation | Positive/acceptable four-clip user screen; broader gate scope pending (#53 remains open) |
| Fresh FlashHead/browser baseline; cold and ten warmed turns per configuration | Not run: integration gate deferred |
| CPU/GPU coexistence, stalls, peak RAM/VRAM and allocation release | Not measured; the quality matrix uses CPU in separate processes and is not a coexistence benchmark |
| Browser first audible speech with a decoded moving frame; 3–5 s warm target | Not measured; isolated complete-WAV timing does not establish this |
| Continuous mono 16 kHz PCM16 resampling, bounded queues and phrase endings | Not integrated or verified for Chatterbox |
| Stop, reset, replacement, repeated voice switches, crashes/missing assets and recovery through browser/API | Not exercised for an experimental adapter; existing application tests remain separate |

No experimental application voice, reference-storage lifecycle, avatar persistence
change or adapter has been added. There is no experimental-app launch command
to claim for this deferred stage. Manual integration verification is inapplicable
until the gate permits that implementation; the #52/#53 audition commands are
not substitutes. No new production implementation tickets are warranted on the
current conditional evidence. If #53 later passes and closes, the next authorised
stage is the bounded #54 prototype and its existing acceptance matrix, with shared-GPU
measurements serialised and independent correctness checks parallelised safely.
