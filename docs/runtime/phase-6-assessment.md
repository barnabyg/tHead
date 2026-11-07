# Phase 6 selectable-avatar handoff (#30–#33)

The application supports JFK/Zira (default) and Grace Hopper/Hazel, launch IDs and
between-turn browser selection, atomic preparation and recoverable errors. The
model remains loaded once; switching preserves context, Stop detaches playback,
and New conversation retains the choice while clearing context. Pending switches
are rejected, never queued or superseded. See [the launch/pair guide](windows-pairs.md)
for source terms, pinned acquisition, voices, installation checks and scenarios.

## Native audiovisual and recovery evidence

On 7 November 2026, the user viewed/listened to the native JFK/Zira black-hole
sample and Hopper/Hazel contextual follow-up and confirmed **both pass clear
speech, moving lips, approximate synchronisation, continuous playback and complete
endings**. These samples used real local SAPI voices, FlashHead Lite and H.264/AAC
media with deterministic fixture text. This is qualitative confirmation of those
two outputs, separate from digital timing; it neither instruments physical
speakers nor certifies every later real-provider answer.

[Native fixture evidence](rtx3090-phase6-fixture.json) records 17 requests (15
complete playbacks and two deliberately interrupted turns), ten alternating-pair
measured prompts after two explicit warm-ups, Stop/replacement, busy reset,
failure after partial preparation/recovery, and New conversation during delayed
preparation. Duration **182.17 s**. Five measured digital onsets per pair:
JFK/Zira median **1.904 s**, p95 **1.931 s**, range **1.711–1.931 s**;
Hopper/Hazel median **1.832 s**, p95 **1.864 s**, range **1.781–1.864 s**.
Fixture accounting increased by simulated **USD 0.001608125**; no paid provider
requests occurred, and the real ledger was untouched by this run.

Allocated GPU bytes stayed **4308569088**, reserved **5943328768** at every
completed-turn resource sample. Same-pair RSS endpoints grew by 0.79 MB (JFK)
and 1.60 MB (Hopper), with different pair-specific RSS levels. This short run
does not establish indefinite stability or a leak rate. Preparation retains one
job and at most two voice owners during handoff; no per-selection model cache
is added. Existing media fragments still accumulate on disk under ignored runtime
outputs. Native 100-turn/multi-hour selectable-avatar resource behaviour is untested.

The fixture capture records its starting source plus tracked diff and runner
SHA256. Final production source is `3781960`; subsequent changes to the capture
were UI acknowledgement gating and exclusive-port launch handling, with no
provider/speech/inference/buffering profile change. The final real capture uses
the exact clean tracked implementation revision.

## Real-provider latency and switching

[Real native evidence](rtx3090-phase6-real.json) captured clean tracked source
`3781960eb304bbc2a8c44ec8e289077eb31a039f`, Chromium 158, gpt-6-luna,
Windows 11 build 26300, RTX 3090 24 GB/driver 621.14, Python 3.12.10,
CUDA 12.8, FlashHead Lite eager single GPU and the pinned Desktop voice tokens.
Eight-frame fragments, 1.28 s initial buffer and 2.88 s lookahead are unchanged.
Model/application startup was **8.291 s**, including **0.658 s** default-pair
preparation. Source/models/media filesystem caches were warm; this was a fresh
application process, not a fresh installation. GPU measurements were serial.

First-use response warm-ups were **3.750 s** (JFK/Zira) and **4.477 s**
(Hopper/Hazel), both retained and excluded from the following measured sample:

| Turn | Pair | Prompt | Digital onset, s |
| --- | --- | --- | ---: |
| 1 | JFK/Zira | What is a black hole? | 2.512 |
| 2 | Hopper/Hazel | How do we detect one? | 2.912 |
| 3 | JFK/Zira | Why do seasons happen? | 2.304 |
| 4 | Hopper/Hazel | What changes in the Southern Hemisphere? | 2.332 |
| 5 | JFK/Zira | How does a rainbow form? | 2.231 |
| 6 | Hopper/Hazel | What conditions do we need to see one? | 2.631 |
| 7 | JFK/Zira | What causes ocean tides? | 2.251 |
| 8 | Hopper/Hazel | Why are there usually two high tides each day? | 3.015 |
| 9 | JFK/Zira | How do solar panels produce electricity? | 2.195 |
| 10 | Hopper/Hazel | Do they still work on cloudy days? | 2.282 |

All ten completed with browser ended events, digital audio onset and advancing
frames, without autoplay intervention, post-start stalls, failures or 10+ second
normal-use turns. Combined median **2.318 s**, nearest-rank p95 **3.015 s**,
range **2.195–3.015 s**. JFK/Zira (five turns) median **2.251 s**, p95 **2.512 s**;
Hopper/Hazel (five turns) median **2.631 s**, p95 **3.015 s**. These observations
meet the prototype's 3–5 s digital target and show no warmed-up regression versus
[Phase 5](phase-5-latency.md): median 2.473 s, p95 3.755 s, range 2.077–3.755 s.
The prompts match that ten-turn list, but warm-up/context histories differ and
samples are small; this is no causal speedup claim. LLM first-text ranged
0.471–0.965 s versus Phase 5's 0.549–2.028 s, so provider variation is material.
There were no 10+ second turns requiring stage optimisation or hardware changes.

Switch timing is **separate** from Submit onset: twelve successful switches,
median **0.388 s**, nearest-rank p95 **0.405 s**, range **0.385–0.405 s**.
First Hopper use was **0.391 s** observed / **0.287 s** server preparation;
repeat preparation was about **0.282–0.359 s**. The observed interval includes
automation/control/status polling overhead and must not be treated as precise
physical UI latency. Default first preparation occurs inside startup above.
The deliberate two-second loading diagnostic is excluded from normal switches.

The full real scenario completed 17 bounded requests, including 15 complete
playbacks and two intended interruptions, in **328.255 s**. It also passed
contextual follow-up after switching, Stop/replacement, busy reset,
partial-preparation failure/recovery and retained choice on reset during loading.
Estimated existing-ledger increment was **USD 0.002743875**, including retained
conservative reservations for interrupted work, below the explicit USD 0.05 cap.
No real ledger was initialised/reset. Fixture accounting is separately identified.

Real allocated/reserved GPU bytes matched the fixed values above at all completed
resource samples. Same-pair first/last RSS increased **6.47 MB** (JFK) and
**3.83 MB** (Hopper), with much of the change during warm-up/early turns. This
bounded five-minute observation is neither evidence of indefinite stability nor
a validated long-session leak rate. Raw per-turn resources, timings, settings,
errors and complete transcripts are retained for audit.

## Clean tracked launch and audible Stop

A branch-backed clean checkout of `3781960` ran the documented PowerShell launcher
with `-NoBrowser -Diagnostics -FixtureProvider -InitializeBudget -Pair hopper-hazel
-Port 8878`. Tracked status was empty before and after startup/scenarios.
[Startup evidence](phase6-clean-startup.json) records the command, source,
prerequisites, voice/model pins and readiness. Preparation took **14.119 s**;
application readiness **8.936 s**, with Hopper/Hazel active on startup.

Explicit warm junctions supplied `venv`, `download-venv`, `python`, `uv-cache`,
`hf-cache`, `models`, `FlashHead`, `media` and `archives`. No whole-runtime
junction was used. The clean checkout newly acquired both pinned portraits and
source speech, generated its WAV inputs and used isolated media outputs and a
disposable simulated fixture ledger. This validates tracked acquisition/launch
with declared warm runtime dependencies, not fresh Windows/GPU/voice installation
or fresh model downloads. The actual URLs/hashes remain in tracked locks; local
generated files alone are not the reproduction instructions.

[Supplemental audible-Stop evidence](rtx3090-phase6-stop.json) used that clean
application and the delivered fixture-only `--stop-only` capture mode. Four
no-cost requests in **37.018 s** exercised both pairs: wait for moving playback
and a non-silent browser graph, Stop, verify stopped identity/state and detached
media, observe digital silence, then complete a replacement. Before-Stop RMS
was 0.162 (JFK) and 0.174 (Hopper); first silent samples were **17.3 ms** and
**17.2 ms** after Stop, respectively, with two consecutive below-threshold samples
required. These are browser graph observations with scheduling/FFT-window limits,
not physical speaker measurements. The ten-turn captures separately exercised
Stop at synthesis start and New conversation during active work/loading.

The final application code matches the clean source. Later capture changes add
only the supplemental observation mode and narrowly scoped public-evidence
secret-scan metadata handling; the report retains runner SHA256 and tracked diff.
The temporary checkout/branch and task-owned native servers were removed/stopped
after preserving evidence; shared warm caches and the older app were retained.

## Investigation and excluded attempts

1. A pre-existing application on port 8765 returned old status without pair fields.
   No result from that attempt is used. Windows duplicate listener semantics
   allowed ambiguous routing. The launcher now exposes `-Port`; the server uses
   exclusive Windows binding, and an HTTP-boundary test verifies duplicate launch
   failure without replacing the original session. The older app was preserved.
2. An isolated fixture attempt completed two warm-ups, then exposed selection
   before New conversation acknowledgement (stale session conflict). It was
   stopped and excluded. A gated browser test reproduced the race; controls now
   wait for reset/cancellation acknowledgement and invalidate stale status polls.
   The replacement run above completed all probes.
3. Review identified a related end-of-playback acknowledgement edge. A delayed
   telemetry test reproduced it; UI and backend now share selection availability.
   These fixes changed coordination, not response production or model settings.

## Launch and manual scenario

From `C:/docs/git/tHead` in PowerShell 7, with Windows 11, RTX 3090 24 GB,
driver/CUDA and tools from the existing runtime guide, both pinned Desktop voices,
backend credential and the existing real monthly budget:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -Diagnostics
```

Wait for readiness at http://127.0.0.1:8765. If another app owns that port, add
`-Port 8877` and use http://127.0.0.1:8877. Only first real use adds
`-InitializeBudget`; normal launches reuse the ledger. `-Pair hopper-hazel`
starts with the second pair; omitted pair remains JFK/Zira. Voice installation
and hashes are validated, never silently substituted.

Ask “What is a black hole?”, hear the ending, select Hopper/Hazel and ask
“How do we detect one?”. Switch back, Stop an active answer, submit a replacement
and use New conversation while busy. Expect context across switches, none after
reset, and no old/mismatched playback. For controlled no-cost recovery, launch
with `-FixtureProvider` using its separate ledger, select **Fail after partial
preparation**, switch, observe the named error, choose **None** and an available
pair, and ask again. Repeat delayed preparation with New conversation. The pair
guide documents missing/unreadable/invalid portrait and voice diagnostics too.

Fresh Windows/driver/voice installation remains unverified. No voice files are
redistributed. Browser digital audio/advancing frames cannot measure speaker
latency, semantic speech onset or synchronisation precision. The evidence sample
is exploratory, not an SLA; fresh downloads and warm caches are declared in the
clean-checkout record. No hardware/service/runtime expansion is implied.
