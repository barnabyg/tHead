# Phase 5 hardware decision (#27)

The measured RTX 3090 configuration reaches digital Submit-to-audio-and-advancing-
video onset in 2.077–3.755 seconds over ten warmed real-provider turns: median
2.473 s, nearest-rank p95 3.755 s, no recorded stalls/failures or 10+ second turns.
See [the baseline and raw evidence](phase-5-latency.md) and
[the no-change optimisation decision](phase-5-investigation.md).

**No hardware change is recommended on this evidence. A 4090 comparison is
unnecessary for the demonstrated prototype.** On 7 November 2026 the user confirmed
clear speech, moving lips, approximate synchronisation and complete endings for
the delivered real-provider black-hole/follow-up scenario. This qualitative sign-off
supports retaining the RTX 3090; it does not instrument physical-speaker latency
or establish synchronisation accuracy for every turn.

Only an actual RTX 3090 is available on the tested host. No RTX 4090 setup,
native Windows operation or end-to-end comparison was performed. No upstream
throughput claim is used to infer a 4090 requirement. The most variable observed
initial stage is provider first text (0.549–2.028 seconds after acceptance),
which a GPU replacement cannot remove. Local synthesis/inference and initial
buffering contribute too; overlapping stages cannot be summed.

The short listening/viewing scenario passed. Use the single PowerShell 7 launch
command and prerequisites in [the launch guide](windows-conversation.md) to repeat
it after production changes. If further use or a repeated comparable benchmark
demonstrates a shortfall, first isolate its stage. Only a persistent
GPU-bound shortfall justifies obtaining an actual 4090 and repeating the same
at-least-ten-turn source/model/prompt/context/settings benchmark, declaring host
differences, readiness, failures/stalls and spend. Until then, comparative hardware
validation is unresolved and a 4090 is not established as necessary.
