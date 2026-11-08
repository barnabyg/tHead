# Chatterbox / FlashHead integration (#54)

The opt-in harness uses real FlashHead/browser playback and deterministic no-cost
answers. Normal Zira/Hazel behaviour and released avatar storage remain compatible.
Experimental selection is saved separately. References have fixed IDs/hashes;
clients cannot provide paths. Recording provenance is in the [quality report](chatterbox-quality.md).

## Manual verification

Prerequisites: Windows 11, PowerShell 7, Git, uv and the normal FlashHead app
prepared using README.md; RTX 3090 with its NVIDIA driver. Acquisition needs
network access, 20 GiB free disk and 8 GiB free RAM. Synthesis is offline.
Run this one command in PowerShell 7:

```powershell
Set-Location C:/docs/git/tHead; ./scripts/chatterbox-app.ps1 -Avatar chatterbox-nano-1089
```

This prepares the isolated CPU environment and opens http://127.0.0.1:8767.
Select either Nano experimental avatar in Settings. Ask `short-1` ("Yes, that
sounds good.") and `multi-2` (three complete instructions). Check voice, moving
portrait, lip synchronisation, joins and final word. Stop during another reply,
ask `short-2`, then try New conversation during synthesis. Switch to Zira/Hazel
and back. Expect responsive controls, correct voice and no obsolete media.
Shut down and rerun the same command without `-Avatar` to reuse the last prepared
selection. Missing/changed assets must fail explicitly; restore with preparation
and reselect an available avatar. No personal reference import is implemented.

Append `-Configuration cuda` for the explicitly separate GPU environment/state.
It uses the same source/model pins. Insufficient VRAM or a mismatched environment
fails without CPU fallback. Default remains CPU; `-SkipPreparation` reuses assets.

## Measurement method

Same JFK portrait, browser and FlashHead settings; one fresh application cold
start, one cold multi-phrase reply and ten warmed short/multi-phrase replies per
configuration. Shared-GPU measurements are serial; independent correctness checks
run concurrently. Nano generates whole phrases, with no incremental PCM. A
persistent process caches model/conditioning. Continuous soxr HQ conversion feeds
mono 16 kHz PCM16, including the final flush, into existing bounded queues.

Onset is the later of browser digital audio and a decoded moving frame, relative
to submit-action on one client clock. Polling is 100 ms, resources about 500 ms.
This does not establish physical-speaker latency. Ten-sample p95 uses nearest rank
(the maximum) and is exploratory. Failed/autoplay-blocked attempts stay failures.
RAM/CPU seconds cover app/worker/browser trees; summed RSS may count shared pages.
VRAM, GPU utilisation and CPU percentage include device/system background use.

## CPU results

| Configuration | Warm onset median / range (s) | Above 5 s | Failed or 10+ s | Buffering events |
| --- | --- | --- | --- | --- |
| Zira baseline | 1.87 / 1.77–1.99 | 0/10 | 0/10 | 0 |
| Nano / Peter | 3.44 / 3.03–4.95 | 0/10 | 0/10 | 7 |
| Nano / Nikolle | 4.48 / 3.12–5.45 | 4/10 | 0/10 | 4 |

Peter meets the warm onset target in this sample; Nikolle does not consistently.
CPU multi-phrase playback had approximately 0.9–2.0 s buffering gaps. Stop/reset
returned to idle in about 0.30 s during synthesis and 0.59 s during playback.
Reloading a killed/crashed worker made the next onset about 15–16 s, exceeding
the normal-turn target. These performance results do not change accepted quality.

The first Peter benchmark aborted before turns because of an implicit 5-second
Playwright readiness assertion. The app itself prepared successfully. The bound
was corrected to 240 seconds; the failed attempt and fresh rerun are retained.
No CPU run had an OOM.

## Separate CUDA results

The second environment pins Python 3.12.10, torch/torchaudio 2.6.0+cu124 and CUDA
12.4, using the [official PyTorch 2.6 wheel configuration](https://pytorch.org/get-started/previous-versions/#v260).
The CPU and FlashHead environments were preserved. Source/model pins are identical;
[installed package differences and hardware](chatterbox/integration/environment.json)
are recorded. The host has Ryzen 5 7600 (6 cores/12 threads), about 103 GB physical
RAM, RTX 3090 (24,576 MiB VRAM), driver 621.14, and Chromium 158.0.8127.18.
FlashHead's observed baseline peak was 6,798 MiB, leaving ample measured headroom;
the worker additionally requires 8 GiB free before allocating, with no fallback.

| Configuration | Warm onset median / range (s) | Above 5 s | Failed or 10+ s | Buffering events |
| --- | --- | --- | --- | --- |
| Peter, first CUDA attempt | 2.44 / 2.16–5.05 | 1/10 | 0/10 | 0 |
| Peter, uncontended repeat | 2.41 / 2.10–2.72 | 0/10 | 0/10 | 0 |
| Nikolle | 2.53 / 2.20–2.85 | 0/10 | 0/10 | 0 |

The first GPU attempt overlapped the tail of no-cost canonical verification.
Its short-answer outlier had 3.37 s to first PCM and TTS RTF 2.63. Contention is a
plausible contributor, not a proven cause. A fresh process with correctness checks
finished repeated the same fixed sequence without source/model/generation tuning.
Both datasets are retained. The repeat meets the roughly 3–5 s warm target; the
first attempt demonstrates sensitivity and is not discarded from the assessment.

Fresh CUDA preparation took 66.48 s on its first process (model/reference worker
only); repeat worker preparations were 11.15 s and 10.62 s with existing driver/
kernel caches. Those repeat figures are not an empty-cache installation cold start.
CPU preparations were 9.94 s and 9.97 s. Full portrait/voice preparations and each
cold first reply are recorded separately in raw readiness/events. First PCM warm
medians were 0.75/0.79 s on CUDA, compared with 1.93/1.72 s on CPU and 0.008 s
for Zira. Median TTS RTF was 0.38/0.38 on CUDA versus 0.91/0.89 on CPU.

Total turn time includes speaking the answer: CUDA medians 5.95/6.81 s, maxima
14.92/15.83 s; CPU medians 7.62/8.35 s, maxima 20.50/22.56 s. Long spoken replies
naturally exceed 10 s total. The failed-experience test applies to first speech
of 10+ s, not to the duration of a complete long answer.

## Playback and correctness

The user reported the real prototype **"Synchronised and complete"** after being
asked to check short/multi-phrase speech, lip movement and endings. A real CPU
FlashHead clip was also supplied for that check. This is a human playback verdict,
not automated proof of every speaker/configuration or all 74 unreviewed quality
clips. CPU live buffering remains a measured limitation despite correct words.

FFmpeg decoded all 66 baseline/CPU/CUDA complete timelines without errors. Published
MP4 audio is mono 16 kHz, with matching starts and frame/AAC padding documented
in [media validation](chatterbox/integration/media-validation.json). Queue limits
remain unchanged; adapter replies and phrase lengths are bounded. No padding is
inserted between generated phrases, and the resampler is flushed at turn end.

No-cost API tests exercise real private-worker IPC and public HTTP errors. Browser
tests preserve backend error statuses and substitute only successful media for
cost-free UI coverage. They cover Stop, obsolete media, replacement, crash, reset,
repeated SAPI/Nano switches and restart reference reuse. Native tests use actual
FlashHead output, not those media substitutes. Real missing reference/model files
were temporarily moved, explicit failures observed, restored with hash verification,
and successful replacement turns generated. Old media returned HTTP 410 after
Stop/reset. Restart without an avatar override restored the saved stable reference
and completed speech. Normal persisted avatar formats were not migrated.

One extra CPU asset-probe run lost its resource monitor to inherited PYTHONHOME
from uv. Browser/asset results remain valid, but that attempt supplies no resource
claims. The monitor now uses isolated Python and its exit code is checked. A
focused host check confirmed the fix before CUDA measurement. All failed attempts,
including the earlier readiness-assertion abort, are retained.


## Recovery and resources

| Native probe | CPU idle / next onset (s) | CUDA idle / next onset (s) |
| --- | --- | --- |
| Stop during synthesis | 0.30 / 15.43 | 0.22 / 14.45 |
| New conversation during synthesis | 0.31 / 15.70 | 0.21 / 14.43 |
| Stop during playback | 0.59 / 3.75 | 0.79 / 2.12 |
| Worker crash | explicit error / 15.10 | explicit error / 14.33 |

Replacement turns succeeded with the selected reference; obsolete media returned
410. Switching to Zira/Hazel took about 0.45–0.57 s, Nano about 11.6–12.5 s;
subsequent warmed speech used the selected engine/reference. All four repeated
switches passed on CPU and CUDA. Missing real assets failed explicitly and
recovered after verified restoration; no alternate model/voice/hardware was used.

| Capture | Peak scoped RSS (GB) | Peak global VRAM (MiB) | Mean / max system CPU (%) | Mean / max GPU (%) |
| --- | --- | --- | --- | --- |
| Baseline | 3.76 | 6798 | 11.9 / 37.8 | 53.1 / 100 |
| CPU Peter | 6.95 | 6799 | 38.2 / 83.6 | 35.1 / 100 |
| CPU Nikolle + recovery/switch probes | 11.18 | 6798 | 32.4 / 87.3 | 28.2 / 100 |
| CUDA Peter uncontended | 6.90 | 9470 | 19.7 / 67.0 | 50.3 / 100 |
| CUDA Nikolle + recovery/switch probes | 8.29 | 9487 | 20.7 / 79.4 | 33.6 / 100 |

No OOM occurred. Probe scopes differ, so their aggregate utilisation means are
not a throughput comparison. FlashHead's released-allocation events stayed at
4,308,569,088 allocated / 5,943,328,768 reserved bytes across repeated switches and
recoveries, with zero queued audio. Device VRAM returned from the combined peak
to exactly its own starting value after both isolated runs: 836 MiB and 840 MiB.
[Cleanup](chatterbox/integration/cleanup.json) confirms no task app/voice worker or
listening benchmark port remained. This supports bounded resource reuse in the
measured sequence, not an unlimited-duration soak claim.

## Decision

**GPU Nano is viable as this bounded local research prototype. Do not adopt it
as a production voice yet.** Native setup and the explicitly revised human quality
gate pass. Warm uncontended GPU playback meets the target without stalls and
coexists with FlashHead; CPU is not recommended for conversational playback.
Cancellation is safe and responsive, but worker reload makes the next speech
14–16 seconds late. That recovery fails the desired normal-turn experience.

The pinned upstream is retired/unmaintained and its candidate environment has
90 recorded dependency advisories. No advisory has been suppressed to turn this
into a production pass. The CUDA package inventory differs only in the two
PyTorch wheel variants; it does not resolve those base-version risks. Keep the
CUDA wheel LICENSE/NOTICE and source/model/recording attributions. This is not a
production security or licence clearance. The wider 74-clip quality matrix,
accent classification, personal-reference lifecycle and long-duration soak remain
unreviewed/out of scope. Physical-speaker latency is unmeasured.

If maintenance/security ownership is accepted, the smallest follow-on work is:
(1) a cancellable engine boundary that preserves warm conditioning safely;
(2) validated local reference import/storage/deletion with licence provenance;
(3) a shared voice catalogue; (4) versioned avatar voice references with compatible
persistence; and (5) actionable missing-voice recovery. These are proposed scopes,
not shipped production features or newly published tickets. No production cloning
UI, saved-format migration, multilingual work, fine-tuning or hosted TTS was added.

## Evidence and verification

[Individual raw captures](chatterbox/integration/) contain the fixed text sequence,
all cold/warm turns, readiness, events, source-file hashes and failed attempts.
[Resource summary](chatterbox/integration/resource-summary.json) accompanies raw
500 ms process/device samples. The first CUDA attempt's overlap and CPU monitor
failure are retained and excluded from uncontended/resource claims respectively.
Browser digital onset, human playback, decoder validation and resource measurements
are separate evidence; none is silently substituted for another.

Reproduce native measurements serially with `scripts/chatterbox-measure.ps1`
using a fresh `-Label`, `-Avatar jfk-zira`, `chatterbox-nano-1089` or
`chatterbox-nano-121`, and explicit `-Configuration cpu`/`cuda`. Add `-Probes` for
fault/recovery/switch checks. Each invocation starts a fresh app, runs one cold
and ten warmed replies, records resource samples and shuts down its own tree.
It never overwrites a prior attempt. Port 8767 is default; `-Port` isolates a run.
Preparation can be included with `-Prepare`.

Canonical verification: `uv run --locked python scripts/verify.py`. Public UUIDs,
source/artifact hashes in named evidence schemas are narrowly excluded from
high-entropy secret findings; other fields and detectors remain active. Existing
exact upstream warning and fixed local subprocess analysis exceptions remain
scoped/documented. No candidate vulnerability suppression was added.
