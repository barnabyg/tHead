# Phase 5 prototype handoff (#28)

The RTX 3090 demonstrated a **2.473 s median, 3.755 s p95, 2.077–3.755 s range**
for ten warmed real-provider Submit-to-digital-audio-and-advancing-video turns,
with zero recorded failures, stalls or 10+ second turns. Estimated total paid
experiment cost including the excluded warm-up was **USD 0.00079175**. No paid
optimisation experiments were needed. This meets the digital latency bound.
On 7 November 2026, the user completed the black-hole/follow-up listening/viewing
check on the delivered real-provider app and confirmed all four checks passed:
clear speech, moving lips, approximate synchronisation and complete endings.
Together these support the prototype experience on the tested RTX 3090 configuration.
The sign-off is qualitative and separate from the ten-turn digital benchmark;
physical-speaker Submit latency was not instrumented.

See [per-turn/stage/raw latency evidence](phase-5-latency.md),
[the evidence-backed no-tuning decision](phase-5-investigation.md),
[bounded-session/Stop/reset/failure/resource results](phase-5-recovery.md), and
[the hardware decision](phase-5-hardware.md). No RTX 4090 is recommended from
these results, and none was comparatively tested. This report establishes neither
indefinite stability nor the entire product goal, and does not itself authorise
selectable-avatar work.

## Clean tracked launch

A detached clean tracked checkout of `52aa59a` ran the documented launcher with
`-NoBrowser -Diagnostics -FixtureProvider -InitializeBudget` and isolated generated
inputs, outputs and fixture ledger. `git status --porcelain` was empty before and
after startup. Preparation **14.243 s**, application readiness **8.838 s**.
[Startup evidence](phase5-clean-startup.json) records the command, source, cache
declarations and runtime/voice/model pins. Native browser recovery/Stop/reset
was then exercised against this checkout, using the current reviewed runner.
Real-provider distribution was measured at `eb47df3`; later executable changes
add observation/fixture validation, with no production buffering/model change.

Declared installed prerequisites: Windows 11 build 26300, RTX 3090 24 GB/driver
621.14, PowerShell 7.6.9, bootstrap Python 3.12.10, uv 0.11.7, Git, Windows Zira
Desktop English voice and H.264/AAC browser. The locked runtime uses CUDA 12.8.
Explicit junctions supplied warm `venv`, `download-venv`, `python`, `uv-cache`,
`hf-cache`, `models`, `FlashHead`, `media` and `archives` caches. Generated input
copies and ledger were local to the clean checkout. No entire-runtime junction
was used. This validates tracked launch sources with declared warm prerequisites;
it does not validate a fresh Windows/driver/voice installation or fresh downloads.
The clean fixture ledger does not replace or reset the real monthly ledger.

## One preparation/launch command

From `C:/docs/git/tHead` in PowerShell 7, after setting the backend credential
through the existing credential manager and installing the declared prerequisites:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -Diagnostics
```

Only first real use adds `-InitializeBudget`. Normal restarts reuse
`.runtime/conversation-budget.sqlite3`; never initialise away previous accounting.
Model defaults to gpt-6-luna. Wait for idle at http://127.0.0.1:8765.
The command prepares pinned source/models/media, loads local voice/GPU once and
opens the browser. Downloads need network and disk space. The app has a two-hour
lifetime with bounded shutdown. No keys are needed in the browser.

Short scenario: ask “What is a black hole?”, hear the complete ending, ask
“How do we detect one?”, Stop an active answer and submit a replacement. Start
New conversation while busy, then ask a fresh topic. Expect obsolete text/media
to remain absent. For reproducible controlled failures, restart with the same
command plus `-FixtureProvider` and choose Fail provider, Disconnect provider,
Fail local TTS and Fail media; select None and successfully Ask after each.
Use the separate fixture budget, initialising it only on first fixture use.
Confirm clear continuous speech, moving approximately synchronised lips, complete
endings and accounting retained through Stop/reset. Autoplay intervention invalidates
timed latency measurements and must be reported.

## Limits and next action

The short native resource scenario and 100-turn synthetic browser scenario passed;
native GPU resource behaviour over all 100 turns remains unverified. Media fragments
accumulate on disk until explicitly removed; resource-idle does not mean disk
cleanup. Model/provider/network variability and sample size limit generalisation.
No persistent conversation storage or automatic hardware migration was introduced.

Perceptual validation of the short delivered-app scenario passed. The remaining
validation work is native 100-turn resource behaviour and physical-speaker timing
if that level of measurement is required. If further use exposes a shortfall,
isolate provider/network, synthesis, inference or buffering before tuning or
recommending hardware. Future production timing changes require comparable
real ten-turn evidence and the affected cancellation/endings rechecks.
