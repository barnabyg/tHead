# Phase 5 bounded bottleneck investigation (#25)

Baseline and success criterion: [ten-turn RTX 3090 benchmark](phase-5-latency.md).
Typical Submit to speech with moving video target is 3–5 seconds, with no normal
10+ second turns, later stalls, ordering/endings or cancellation regressions.
Digital measurements satisfy the latency bound. The user subsequently confirmed
clear speech, moving lips, approximate synchronisation and complete endings in the
delivered black-hole/follow-up scenario on 7 November 2026. Physical-speaker latency
remains uninstrumented; this is a short qualitative check, not per-turn validation.

Hypothesis: GPU throughput may prevent this prototype meeting the latency target.
Change/measurement: close the missing Submit/motion instrumentation and run the
declared eleven-request baseline on the existing configuration, without tuning.
Conclusion: median 2.473 s, p95/max 3.755 s, zero stalls/failures. First text varies
0.549–2.028 s after acceptance, a substantial varying upstream contribution.
There is no demonstrated GPU throughput shortfall in this sample.

Candidate hypothesis: reducing the 1.28-second playback buffer might reduce onset.
Decision: no experiment or implementation is justified while the measured digital
target is already met. The subsequent qualitative check also passed. Reducing buffering
could introduce later starvation. Keep content/order, sync pipeline, queue bounds,
budget, Stop and reset unchanged. No tuning experiments or speculative refactoring
were performed; this is the issue's explicit no-useful-optimisation outcome.

Stopping criterion: stop now because no measured limiting stage prevents the
digital target. Resume only after actual listening/viewing or a repeat benchmark
demonstrates a specific shortfall. Investigate provider/network variability before
assuming a faster GPU will fix it. No normal-use 10+ second turn occurred; deliberate
delay/failure fixtures belong to recovery evidence, never latency statistics.

The delivered production timing configuration is the measured baseline; subsequent
changes add diagnostic events and fixture regression scenarios only. Any future
buffer, model, voice, runtime, provider or scheduling change requires a comparable
ten-turn real-provider/GPU/browser run plus cancellation/endings rechecks.
No before/after improvement or tuned-performance claim is made.

Manual preparation/launch and the short observable scenario are the single command
and prerequisites in [the latency report](phase-5-latency.md#reproduction-and-manual-check).
