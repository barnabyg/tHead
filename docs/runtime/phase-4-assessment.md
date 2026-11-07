# Phase 4 conversational workflow assessment

Measured on 7 November 2026, native Windows 11 build 26300, RTX 3090 24 GB,
Python 3.12.10, pinned FlashHead Lite/CUDA 12.8 and Microsoft Zira Desktop.
Chromium 156 presented real generated H.264/AAC avatar media. Automated Chromium
158 tests use synthetic colour/tone media and a deterministic text provider;
they are correctness checks, not GPU or perceptual evidence.

**Result: the conversational workflow is implemented and demonstrated at the
digital browser boundary. Perceptual sign-off and Phase 5 performance validation
remain open.** No claim of a typical 3–5 second experience is made from these
few runs. The independent ten-turn median/p95 assessment and optimisation remain
Phase 5 work.

## Reproducible workflow

Use the one preparation/launch command and prerequisites in
[windows-conversation.md](windows-conversation.md), from `C:/docs/git/tHead`.
The guide includes the exact black-hole/follow-up/Stop/replacement/reset scenario,
first-use accounting, no-cost provider fixtures, failure probes and an isolated
budget-exhaustion fixture. Existing demonstrations remain available.

The documented launcher was exercised with warm declared caches and the native
GPU/local voice: preparation took 11.664 seconds, followed by approximately
8.019 seconds of application readiness. It validates cached runtime/source/model
pins and prepares the audio inputs before launch. This does not measure a fresh
download or installation of Windows, the GPU driver or the voice assets.
Clean-checkout startup verification is recorded separately below.

## Timing evidence and overlap

[rtx3090-conversation.json](rtx3090-conversation.json) contains public example
questions, raw response events, usage and readiness snapshots, deliberately
preserved for this assessment. Normal application operation keeps conversations
in memory; this explicit evidence capture is not conversation persistence.
Times below are seconds after backend acceptance, which includes provider
networking; client monotonic/UTC telemetry is in the raw events.

| Run | LLM first text | First TTS ready | First media | First moving frame | Digital audio onset | Text consumption complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial real black-hole answer | 3.049 | 3.378 | 4.301 | 5.075 | 5.150 | 7.479 |
| Repeated real black-hole answer | 1.436 | 1.800 | 2.563 | 3.350 | 3.407 | 5.824 |
| Exact real contextual follow-up | 0.606 | 1.027 | 1.693 | 2.441 | 2.565 | 6.148 |
| Controlled delayed provider, real TTS/GPU | 0.001 | 0.059 | 1.365 | 2.142 | 2.213 | 3.066 |

The delayed fixture explicitly withholds later characters for three seconds;
audio with moving video starts first. It had one post-start wait because the
deliberate text delay starved the short initial sentence. The real answer and
follow-up runs recorded no post-start waiting/stalled events. The LLM-complete
time measures consumption of the stream, including downstream backpressure;
it is not an isolated provider generation benchmark. First-media to playback
includes buffering and browser scheduling. Digital audio onset uses the browser
audio graph with a 25 ms sample interval, not a microphone at the speakers.

Four bounded paid requests cost an estimated **USD 0.0001745** in total, using
reported usage and the conservative application input rate. One pilot follow-up
accidentally included the previous question and is labelled/excluded from the
exact follow-up demonstration. The exact follow-up played to its complete ending,
then an idle Stop exposed an instrumentation path that marked it interrupted;
that path was corrected and is now covered by the Chromium test that verifies
completed assistant context survives idle Stop. It is not active-Stop evidence.
Accounting is an estimate rather than authoritative billing; see
[conversation-budget.md](conversation-budget.md) for official price sources,
effective date, UTC boundaries and fail-closed behaviour.

## Stop, reset and recovery

In the controlled native long-answer probe, playback was active at 4.929 seconds
of media when Stop was handled. Browser detach took **1 ms**. The first silent
audio-graph sample was observed **12.4 ms** after the action, with the next sample
confirming silence. Resources released **0.374 seconds** after backend Stop.
This separates digital silence from non-preemptible GPU-window completion and
does not establish physical-speaker silence latency.

The stopped answer stayed Interrupted with a conservative allowance retained.
A subsequent native turn completed without reloading GPU resources; its captured
provider fixture context contains the stopped user question and no unfinished
assistant text. An injected real local media failure reported a recoverable error.
New conversation during another long answer cleared the transcript immediately,
hid obsolete output, retained accounting, and allowed a successful fresh native
turn in the same process. Readiness/voice identity stayed unchanged between turns.

Ten HTTP application tests cover streamed text boundaries, context limits and
session loss, cancellation at asynchronous stages, repeated Stop, stale telemetry,
busy reset, provider/TTS/media failures, missing completion, budget rejection,
unusable accounting and untrusted Host headers. Six accounting contract tests cover
durability/rollover and concurrent connections. Four parallel Chromium tests cover
the actual controls, transcript rendering, contextual follow-up, an accepted request
with delayed start reply, busy reset, failures and budget rejection. They make no
paid requests. Their playable synthetic media is explicitly a transport substitute.

The backend credential was checked against the delivered HTML, player JavaScript
and status payload without printing it; no match was present. Provider error bodies
are not reflected into browser material or diagnostics. The server restricts Host
and mutation Origin to loopback addresses.

## Remaining limits

Human confirmation of audible clarity, approximate lip sync, phrase ordering and
the complete ending has not been supplied in this task. Digital onset/frame/end
events and visible playback do not replace that perceptual check. Model access
and network latency can vary. Fresh cache downloads, cross-process budget
contention and price-table changes have not been independently exercised here.
GPU work is serialised because concurrent inference would invalidate timings;
CPU/browser correctness suites run independently in parallel. Phase 5's ten-turn
distribution, bottleneck tuning, long-session soak and hardware decisions are
outside this assessment.

## Clean-checkout startup

A detached, clean tracked checkout of `3d1b32c` ran the documented command with
`-NoBrowser -Diagnostics -FixtureProvider -InitializeBudget`. Preparation completed
in **12.769 seconds** and the native GPU/Zira application became ready in **8.638
seconds** after construction, with no configuration error. Its ledger, generated
outputs and copied public input files were isolated in the clean checkout.
Directory junctions supplied the declared warm Python environments, pinned
upstream/model/media/download caches; Windows, the GPU driver, voice, Python and
uv were already installed. This verifies tracked launch sources with declared
prerequisites/caches, not a fresh machine or cold download. Browser playback and
paid requests were checked in the main checkout rather than replayed here.
