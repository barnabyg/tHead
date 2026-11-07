# Phase 3 feasibility assessment

Measured on 7 November 2026, native Windows 11 build 26300.9711, Ryzen 5 7600,
RTX 3090 24 GB, driver 621.14, Chromium 156. Avatar/runtime pins are unchanged
from Phase 2; `speech-lock.json` identifies the fixed Microsoft Zira Desktop
11.0 voice, installed asset hashes, rate and audio format. Windows PowerShell
5.1 loads framework System.Speech 4.0.0.0. No LLM or hosted TTS was used.

**Decision: pass for this tested local text-to-avatar feasibility profile.**
The integrated pipeline produces real progressive speech/video, preserves PCM
handoff content, supports Stop and replacement passages, and recovers from
injected TTS/media failures. The user confirmed the example's words, approximate
lip synchronisation, phrase boundaries and complete ending during this session.
This is a bounded Windows feasibility demonstration, not a claim that Phase 4's
eventual LLM-integrated 3–5 s conversational target is already achieved.

## Measured player boundary

Full exact texts, phrase timings, runtime pins, media decoding, memory, queue
occupancy and cancellation results are in [rtx3090-speech.json](rtx3090-speech.json).
IDs below locate preserved raw run events and published fragments in
`.runtime/speech/<id>/`. Times are seconds after server acceptance; client UTC
and monotonic timestamps are also retained. Server receipt includes loopback
overhead. Audio onset uses the browser audio graph (25 ms sample interval),
combined with the independent first video presentation callback. Physical
speaker latency was not measured.

| Run prefix | Input / duration | First frames | First playable | Playing | Audio with moving video |
| --- | --- | ---: | ---: | ---: | ---: |
| 02033d07 | Example, 10.245 s | 1.105 | 1.147 | 1.798 | 2.029 |
| 60a1959d | Same example, repeat | 0.981 | 1.002 | 1.662 | 1.823 |
| 684819b6 | Same example, repeat | 1.319 | 1.341 | 1.989 | 2.162 |
| ef92cd2b | `Hi`, 1.170 s | 1.185 | 1.229 | 1.934 | 2.055 |
| 8af4d45d | Four sentences, 18.865 s | 0.984 | 1.005 | 1.701 | 1.852 |
| a4eea0c9 | Long unpunctuated text, 18.270 s, clean checkout | See JSON | See JSON | See JSON | 1.887 |

The example is the three-sentence passage in [windows-speech.md](windows-speech.md).
The four-sentence passage exercises comma/exclamation punctuation and no final
punctuation. The clean-checkout passage repeats the declared sentence without
punctuation, forcing the 180-character bound and a final partial segment. Exact
texts are included in JSON rather than relying on private fixtures.

The three repeated example runs reported no post-start stalls. Their total CPU
TTS preparation was 0.034–0.068 s for 10.245 s audio (151–305 times speech speed),
under concurrent avatar generation. First phrase audio appeared in 0.003–0.039 s.
The native isolated worker probe loaded in 0.548 s and produced 4.56 s speech in
0.081 s. Combined cold GPU/voice readiness was 7.944 s; the clean-checkout launch
reported 9.109 s after server construction. Preparation/download time is separate.

Real early playback is established by the final phrase timings, not just by
streaming a prepared file: run 02033d07 began digital speech at 2.029 s, while
the last phrase started synthesis at 2.371 s and became available at 2.395 s.
The initial implementation prepared all phrases before playback; it is retained
as baseline runs dba9dea1 and d764dc39 and is **not** counted as progressive proof.
The producer now waits for the preceding queued audio to drain before preparing
another phrase. Short utterances can legitimately finish synthesis before playback.

All measured complete final-profile runs have matching synthesised/received PCM
hashes. Published completed streams decode successfully with continuous audio
and video timelines. AAC adds approximately 64 ms padding; video rounds the final
partial window to a frame. PCM integrity proves handoff ordering, not whether a
voice pronounced every word correctly; that is covered by the perceptual check.
GPU generation of the repeated examples ran at 1.39–1.45 times playback speed.
Keep Phase 2's eight-frame fragments and 1.28 s progressive startup margin.

## Stop, failures and retained resources

Run ab99e174 stopped during the delayed synthesis probe at 0.259 s, before any
audio; all task resources released at 1.013 s. The deliberate one-second delayed
external result was rejected. Run fc37b82f stopped while media was buffering
below the startup margin at 1.672 s and released at 2.121 s. Run 931ee655 stopped
during active speech/handoff at 4.077 s: synchronous client detach took 0.8 ms,
the last non-silent sample was observed at 11.1 ms, first silence at 21.8 ms,
and inference/media resources released 0.440 s after server Stop handling.
These observations must not be conflated with physical speaker silence or
preemptible GPU execution. No media was published after Stop in these reports.

Real application-boundary injected TTS and media failures (a82955f4, eec3e472)
exposed clear failure states. Replacement 9be4ac65 completed and played after
both failures in the same process. A successful long passage also followed the
buffering Stop in the clean process. Deterministic CPU HTTP tests separately
exercise repeated Stop, delayed results, stale media/telemetry/input, ordering,
bounded queues and subsequent submissions; their fake media is not GPU evidence.

Repeated complete runs retained 4,314,651,648 allocated GPU bytes and
5,943,328,768 reserved bytes, with peaks around 5.36 GB and process RSS around
3.00 GB. Resource observations include a bounded six-minute sampler of system
CPU, whole-GPU load/memory and app/TTS process CPU time/RSS. Development and
desktop activity are included; this is not an isolated contention benchmark or
a long-duration leak proof. No trend toward accumulating loaded GPU copies was
observed. Queue, worker and shutdown bounds are documented in the launch guide.

## Reproduction and remaining limits

The single documented preparation/launch command was executed from a clean
branch-backed checkout of 8589261. It verified declared source patches, Python
and wheel locks, model revisions, portrait/media and the installed voice hashes,
then successfully served real browser playback. Only declared `.runtime/` caches
were shared via directory junctions; no untracked application sources were used.
This was a warm-cache clean-source check, not a fresh multi-gigabyte download or
a fresh Windows installation. The installed Zira voice remains a Windows
prerequisite under Windows terms; its files are not redistributed.

The worst repeated digital onset of 2.162 s leaves arithmetic room of about
0.84–2.84 s before a 3–5 s target. Future LLM/network/orchestration delay may
overlap or accumulate: measure Phase 4 rather than treating that subtraction as
a proven latency budget. Long initial phrases, voice prosody, abbreviations,
CPU contention and browser scheduling can change results. There is no promise
of indefinite sessions, arbitrary languages/voices, or arbitrary hardware.

Canonical verification is `uv run --locked python scripts/verify.py`; the local
run passed formatting, lint, strict types, static checks, parallel CPU suites,
dependency/secret audits and script packaging/syntax gates. Public UUID and PCM
hash exceptions extend the existing exact-file/exact-field secret-scan filter;
no vulnerability exceptions were added. Manual testing uses the single launch
command and the short scenario in [windows-speech.md](windows-speech.md).
