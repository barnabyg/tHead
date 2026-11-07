# Phase 5 bounded use and recovery (#26)

Two complementary scenarios were run on 7 November 2026. Neither establishes
indefinite stability. The 100-turn session is a deterministic browser correctness
test; the native scenario uses real Windows Zira, FlashHead Lite/RTX 3090 and
playable generated media with a no-cost provider fixture. Fixture timing is never
included in real-provider latency statistics.

## Browser session boundary

The actual Ask control submitted 100 approximately 970-character questions with
synthetic playable transport media. It observed each completed ending, visible
context omission, a 100-entry transcript, rejection of turn 101 with unchanged
response identity/accounting, then New conversation and a successful fresh turn
with exactly one dispatched user message. Focused run: 3.2 minutes, passed.
This exercises context trimming/session admission at the UI boundary; it does
not measure native GPU memory over 100 real-media turns.

Other browser checks cover contextual follow-up, idle Stop preserving completed
assistant context, late accepted start responses, busy reset, literal provider
markup, repeated Stop during connection/streaming/synthesis, exclusion of stopped
assistant text while retaining its question, replacement success after every
failure and budget rejection preserving run/accounting. CPU suites run safely
in parallel with isolated fixture directories/ports. GPU experiments are serial.

## Native clean-checkout run

[Raw snapshots](rtx3090-phase5-recovery.json) record the complete native scenario.
Application source is the clean tracked checkout `52aa59a`; runner source is
`3a807b1` (including the stricter review fixes). This made 30 fixture submissions:
six stopped probes, one busy reset, eight failures and fifteen completed replacement/
fresh/recovery turns. Every failure class was exercised twice in the same process.
The runner's accepted Ask response pins each probe to its actual response identity.
Busy reset clears the transcript before a fresh topic succeeds. Old asynchronous
results did not reappear. Accounting is retained across Stop/reset; fixture costs
are simulated, not paid. Browser budget exhaustion is a separate no-cost scenario.

| Stop stage | Backend stop-handled to release, seconds | Digital silence |
| --- | ---: | --- |
| Provider connection waiting | 0.3383 | Already silent |
| Provider stream | 0.0256 | Already silent |
| Synthesis | 0.9787 | Already silent |
| Avatar inference | 0.1938 | Already silent |
| Media buffering | 0.3753 | Already silent |
| Active audible playback | 0.3695 | Observed after 17 ms |

Each probe pressed Stop twice. The playback probe waited for audio onset and
more than one second of media playback, then required silence status `observed`.
First silent sample was 17 ms after action; next sample confirmed silence.
These are browser audio-graph observations at 48 kHz/256 analyser samples,
not physical-speaker latency. Other stages cannot establish silence of audible
speech because they were already silent. Backend release starts at server Stop
handling and uses its own monotonic clock, separately from browser silence.
Inference is non-preemptible within a window; completed obsolete work is discarded.
Cancellation may close/recreate the voice worker; GPU models remain loaded.

Release snapshots ranged 4.297–4.309 GB allocated GPU memory, 5.929–5.943 GB
reserved, and 2.710–2.989 GB process RSS (decimal GB). The initial jump is warm-up;
later allocations remained around 4.309 GB across success, reset and failures.
This short sample cannot distinguish all allocator/cache growth from leaks.
Audio queue peaked at 2 windows and media at 9 fragments; released audio queues
were zero. Real-provider baseline render snapshots separately had constant
4.315 GB allocated/5.943 GB reserved and RSS 2.995–3.044 GB.

Disk fragments are retained across turns/reset: the isolated native scenario
left **473 MP4 files, 68,319,041 bytes**. Worker release is not disk reclamation.
This is a known retention limitation; do not infer bounded disk use or unlimited
session longevity. The temporary clean checkout and its generated media are
removed after preserving snapshots/accounting. Existing main-checkout media is
preserved. No automatic cleanup of historical user-session media was introduced.

## Repeat and manual verification

From `C:/docs/git/tHead`, with Windows/GPU/voice/tool prerequisites in
[the launch guide](windows-conversation.md), use this one preparation/launch command:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -FixtureProvider -Diagnostics
```

First fixture use adds `-InitializeBudget`; preserve its ledger on restarts.
Wait for idle at http://127.0.0.1:8765. The guide's black-hole/follow-up,
Stop/replacement, busy-reset and four failure choices are the short manual scenario;
expect complete synchronised endings, immediate player detach, cleared old context
on reset and successful replacement after each failure. For repeatable raw capture,
run `node ./scripts/resilience.cjs ./my-new-recovery.json` in a second PowerShell 7
window after installing the documented browser tools. It requires fixture mode,
refuses existing output and has a 30-minute wall limit. Use a fresh fixture ledger
for comparable accounting; never substitute it for real durable accounting.

Remaining gaps: physical speaker measurements, listening/viewing this new run,
100-turn native-media resource trends, cross-process hardware contention and
indefinite operation. Future optimisation of buffering, scheduling, models or
provider consumption must rerun the affected scenarios. The delivered production
timing settings are unchanged from the ten-turn baseline.
