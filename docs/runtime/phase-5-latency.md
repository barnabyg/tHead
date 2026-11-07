# Phase 5 RTX 3090 latency evidence (#24)

7 November 2026. Ten warmed exploratory turns, preceded by one excluded warm-up,
through real OpenAI gpt-6-luna, native Windows Zira, FlashHead Lite and real
H.264/AAC MediaSource playback. Source: `eb47df3`, clean tracked diff at capture.
Source/model/dependency pins remain in runtime-lock.json, speech-lock.json and
demo-lock.json; readiness metadata, voice identity, browser version, prompts,
ordered full context, raw events and accounting are in
[the evidence JSON](rtx3090-phase5-baseline.json).

RTX 3090 24 GB, Windows 11 build 26300, driver 621.14, Python 3.12.10,
CUDA 12.8, eager single GPU, fixed JFK portrait, 8-frame fragments,
1.28-second initial buffer and 2.88-second browser lookahead. Chromium 158
headless, no autoplay override, manual Play or autoplay rejection. Preparation
with warm caches took 12.009 s; application readiness is recorded separately in
the evidence. This is a fresh process with warm filesystem/model caches, not
cold installation/download readiness.

## Results

Each row is Submit to the later of digital audio onset and advancing video.
All ten attempts completed to the browser ended event with backend resources
idle. No post-start waiting/stalled events or failed attempts were observed.

| Turn | Prompt | Seconds |
| --- | --- | ---: |
| Warm-up, excluded | What is gravity? | 5.0951 |
| 1 | What is a black hole? | 2.7541 |
| 2 | How do we detect one? | 2.4533 |
| 3 | Why do seasons happen? | 3.7554 |
| 4 | What changes in the Southern Hemisphere? | 2.6395 |
| 5 | How does a rainbow form? | 2.3157 |
| 6 | What conditions do we need to see one? | 2.4087 |
| 7 | What causes ocean tides? | 2.6331 |
| 8 | Why are there usually two high tides each day? | 2.4920 |
| 9 | How do solar panels produce electricity? | 2.2681 |
| 10 | Do they still work on cloudy days? | 2.0771 |

Median **2.47265 s** (average of sorted fifth/sixth); p95 **3.7554 s**
(nearest rank, ceil(0.95 × 10)); range **2.0771–3.7554 s**. Zero normal-use
10+ second turns, so none required stage investigation. Ten turns do not
establish an SLA or indefinite stability. Warm-up remains visible rather than
being silently removed. Estimated ledger increment including warm-up:
**USD 0.00079175**, below the USD 0.05 experiment allowance; not authoritative billing.

## Measurement and stage interpretation

Submit is timestamped before AudioContext resume or requests. Request/run/session
identities correlate evidence; client onset minus client Submit uses one monotonic
clock and includes preflight, client/server transit and provider networking.
No client/server clock subtraction is used. Server seconds begin at acceptance
and describe stage receipt/order separately. UTC is diagnostic correlation only.

Audio onset is RMS ≥ 0.00001 in a 256-sample browser analyser sampled every 25 ms.
Video requires a second presented frame with increasing mediaTime. Timer scheduling
can add delay; numerical decimal precision is not measurement accuracy. This
establishes digital signal plus advancing frames, not physical-speaker latency,
semantic speech onset, perceived lip-sync or visible facial motion quality.
No microphone measurement or per-turn listening/viewing sign-off was collected
for the ten-turn run. Separately, on 7 November 2026 the user checked the delivered
real-provider app with the black-hole question and contextual follow-up and confirmed
clear speech, moving lips, approximate synchronisation and complete endings.
That qualitative check does not instrument physical-speaker latency or certify
every benchmark answer.

LLM first-text ranged 0.549–2.028 s after backend acceptance. First media ranged
1.235–2.888 s. First speech preparation (`tts-segment`) and avatar window times
(`frames-ready.generation_seconds`) are retained separately per turn. Media
availability, appended buffers, play-request, playing, first frame, moving-video,
audio onset and ended are in the raw events. Speech production and GPU work
overlap provider stream consumption; `llm-complete` includes downstream
backpressure and must not be labelled isolated provider generation time.
Do not sum these overlapping stages. Media-to-onset includes initial buffering,
decoding and browser scheduling. Fixed queues remain bounded.

## Reproduction and manual check

From `C:/docs/git/tHead`, with prerequisites and existing backend credentials and
durable budget described in [the launch guide](windows-conversation.md):

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -Diagnostics
```

Wait for idle at http://127.0.0.1:8765. In another PowerShell 7 window in the same
directory, after the documented browser tooling installation:

```powershell
node ./scripts/benchmark.cjs ./my-new-benchmark.json
```

The command refuses fixture mode, unknown pricing configurations and an existing
output file; it declares one warm-up, ten measured turns, finite operation/wall
limits, retains errors and writes raw evidence after every turn. Its headless
browser uses the same controls/player. Failures and autoplay intervention invalidate
latency attempts and remain visible; a truncated/aborted report is not a completed run.
For physical listening/viewing, use the visible application and the black-hole,
follow-up, complete ending, Stop/replacement and busy-reset scenario in the launch
guide. Confirm intelligible speech, continuous moving lips, approximate sync and
complete endings. Do not substitute this digital report for that check.
