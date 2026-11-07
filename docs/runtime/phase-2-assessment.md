# Phase 2 feasibility assessment

Measured 7 November 2026 on native Windows 11 build 26300, RTX 3090 24 GB,
driver 621.14, Ryzen 5 7600. Source/model/software pins match the
[Phase 1 baseline](windows-baseline.md): Python 3.12.10, Torch 2.11.0+cu128,
CUDA runtime 12.8, Diffusers 0.42.1, Transformers 5.22.2 and FFmpeg 9.0.2.
The browser was the desktop app's local Chromium browser. GPU runs were serial.
The fixed portrait and speech provenance remain in `demo-lock.json` and
[the offline guide](windows-demo.md). No TTS, LLM or integrated conversation runs
were performed.

**Decision: the chunked technical path is credible, but hold the Phase 3 gate
pending human confirmation of audible synchronisation and boundary quality.**
Real browser playback, progressive input and bounded cancellation work on the
target hardware. Container timestamps and decoded frame counts cannot establish
perceived lip sync. The Phase 1 listening confirmation does not validate this
new streaming path. A listening/visual assessment has been requested; no Phase 2
human result is assumed.

## Measured runs

Times are seconds from server run acceptance; first frames means the first
completed GPU batch copied to CPU. Playable means a complete muxed A/V fragment;
playing is the browser event, with presentation callbacks recorded separately.
Server receipt adds loopback request overhead. Physical speaker latency was not
measured. Full per-run metrics, memory and media probes are in
[`rtx3090-streaming.json`](rtx3090-streaming.json); run IDs below locate raw local
events and fragments under `.runtime/streaming/<id>/`.

| Run ID prefix | Input / profile | First frames | Playable | Playing | Render complete | Post-start stalls |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| fcadcd67 | 6 s complete, initial 24-frame fragments | 1.322 | 1.947 | 1.988 | 5.029 | None |
| 08f3a8c3 | 6 s, timed input + deliberate 3 s pause, initial profile | 1.697 | 2.560 | 2.597 | 10.068 | 3.235 s |
| 5a2d237b | 0.35 s, timed final input, initial profile | 1.064 | 1.078 | 1.141 | 1.066 | None |
| 4a0efa6c | 20 s, timed input, initial profile | 1.585 | 2.565 | 2.621 | 20.877 | 0.005, 0.032, 0.941 s |
| 81856ac5 | 20 s, timed input, selected profile | 1.676 | 1.691 | 2.585 | 20.879 | None |
| 2621e675 | 6 s complete, selected profile, warmed owner | 1.102 | 1.143 | 1.190 | 4.842 | None |
| 4f661460 | 6 s timed, selected profile, warmed owner | 1.580 | 1.617 | 2.614 | 7.071 | None |
| b775b482 | 20 s timed, selected profile, repeated owner | See JSON | See JSON | 2.640 | 20.885 | None |

Six-second speech is source seconds 31–37; longer speech is 31–51; the short
input is the first 5,600 PCM samples of the six-second cut. All are mono 16 kHz
PCM16. Timed arrival supplies one 15,360-sample chunk after its 0.96-second
recording interval, with the final partial interval shortened appropriately.
The delayed case adds three seconds before message index two.

All completed observed clips decoded successfully with exactly 150, 500 or nine
video frames for 6 s, 20 s or 0.35 s. Both streams start at timestamp zero;
the continuous AAC mux introduces approximately 64 ms of initial timing/padding.
Six- and 20-second media finish at 6.064 and 20.064 seconds. The short case ends
at 0.424 seconds (video), 0.414 seconds (audio), including final frame rounding.
This is container/frame evidence, not perceptual synchronisation evidence.
Final partial segments are retained; underruns insert no new speech or silence.
Recorded received-PCM hashes match the declared source where hash instrumentation
was present. Earlier baseline runs predate that instrumentation and are labelled
with a null comparison in the JSON.

## Buffering investigation

Baseline/target: preserve continuous warmed playback while reducing avoidable
first-playable delay. Measurement uses GPU batch timings and real browser events,
with a 20-second timed-input run to expose jitter that a short clip can hide.

**Hypothesis → change → measurement → conclusion:** the 24-frame keyframe interval
holds the first fragment until a second generation call, and the initial roughly
one-second player buffer has inadequate arrival-jitter margin. Change the mux to
eight-frame (0.32 s) fragments, keep a bounded 2.88 s output horizon, and initially
buffer 1.28 s for timed input / 0.64 s for complete input. The 20-second comparison
reduced first-playable time from 2.565 to 1.691 s; actual playback stayed near
2.6 s because of deliberate startup buffering. Three stalls became zero in two
longer runs. Complete-input playback began at 1.190 s. Select this profile.

Trade-offs: more keyframes increase encoded size; input timing jitter can still
stall playback, and a deliberate three-second arrival gap still does. This is a
bounded prerecorded experiment, not an indefinitely sustainable service. Pure
model generation for the longer clips is about 1.54–1.56 times playback speed;
arrival-paced end-to-end rendering remains near playback speed by construction.
The short partial window pays for a full model call, so its throughput ratio is
below real time. Do not extrapolate short-run throughput to conversations.

Post-run Torch allocations were 4,314,651,648 bytes across completed runs;
reserved memory remained 5,943,328,768 bytes. Peaks were about 5.35 GB. This shows
no observed GPU allocator growth across these repeats, not a long-duration leak
proof or a whole-system memory measurement. Later instrumentation also records
process RSS, but the initial comparisons did not measure CPU memory growth.
Model load took 3.399–3.588 s in separate server processes. This excludes Python
import/startup and uses warmed filesystem caches; readiness timing is reported
separately in newer reports. Runs within each process retained the loaded weights.

## Stop, stale output and recovery

Real Stop scenarios covered before first playback, before first progressive
arrival, during progressive generation, during a deliberate arrival gap while
buffering, and active playback. Repeated Stop was exercised. In selected-profile
runs, pause/detach calls took 0.5–0.9 ms in browser JavaScript; this is action to
pause-call completion, not an acoustic silence measurement. Generation resources
were released separately: 0.168 s after Stop before arrival, 0.275 s during
generation and 0.037 s while waiting for input. The earlier active-playback Stop
released generation after 0.456 s. Non-preemptible inference is disclosed in the
[launch guide](windows-streaming.md).

No recorded media fragment was published after Stop. CPU HTTP probes separately
inject delayed external results and generation failure, reject stopped media and
stale telemetry, and complete replacement runs. Real repeated runs also completed
without reloading weights. Those probes produce no playable media and are not
counted as GPU/perceptual evidence.

## Reproducibility and remaining work

Use the one preparation/launch command, prerequisites and changed-behaviour
scenario in [windows-streaming.md](windows-streaming.md). A real launcher run
prepared the pinned runtime and inputs from the existing declared `.runtime`
caches, then loaded the server. Uncached acquisition was established in Phase 1;
the current workflow still needs the final clean-checkout recheck recorded here.
All preparation/model/media caches and the installed VC++ runtime/driver are
prerequisites, not files supplied by a normal source checkout.

The selected strategy preserves motion latents across 0.96-second audio chunks
and re-encodes an eight-second window; it is not a stateful incremental wav2vec
encoder. Startup needs 0.96 s received audio for generation, around 1.6 s to first
playable output in the measured timed runs, and around 2.6 s to playback with
continuity margin. This leaves limited but credible room within the eventual
3–5 s goal for LLM first-token delay, TTS first-audio production, text chunking,
handoff and browser scheduling. Those stages are unmeasured; their delays may
overlap or accumulate, and the integrated target has **not** been met or tested.

Before Phase 3: confirm audible/visual boundary quality, retain the selected
startup margin, and budget the missing stages with actual measurements. If lip
sync or motion continuity fails, investigate the rolling encoder/window boundary
and AAC timing on this same runtime before building an integrated pipeline.
