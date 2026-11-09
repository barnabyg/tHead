# Bounded Chatterbox lifecycle (#58)

The adapter retains its model process after ordinary Stop/New conversation. One
outstanding JSON-lines request carries a worker epoch, request ID, turn ID and
reference ID/hash. Cancelled callers return promptly; their response is discarded
by identity before the next operation. Cancelled PCM never reaches the media
pipeline. Existing session cancellation still makes obsolete media return HTTP
410 and prevents it becoming context for a replacement turn.

The current source generates a whole phrase synchronously. It cannot interrupt a
native model call. The lifecycle exposes `draining` while an obsolete operation
finishes, then reuses the model. Each operation has a 60-second watchdog even when
its caller has cancelled; initial model preparation has a 180-second response
limit. Fatal errors close the process; a subsequent request prepares a fresh
process with the same explicit device and reference. There is no retry loop,
standby pool, CPU/SAPI substitution or provider/context reset. `failed` and
`recovery_error` explain failure; `preparing` identifies a subsequent cold load.

## Shared engine ownership

Normal integration should own one `ChatterboxVoice` for the application lifetime,
including while Zira/Hazel are selected. Avatar changes must not close that shared
engine. Call `set_reference(identity, canonical_path, sha256, cancelled=None)` only
between turns. Paths come from the local voice library, never request JSON or a
browser file path. The adapter and worker verify the hash before conditioning and
at the start of each turn. A missing/changed reference fails explicitly.

The same worker reconditions on a different reference without reloading its model.
At most two reference conditionings are retained in least-recently-used order.
Transient `import-` references leave the cache when switching away. When no saved
reference was active before a preview, its owner should close the preview engine
on cancellation rather than retain temporary conditioning while using SAPI.
The current entry is preserved while preparing another; a failure does not commit
the candidate identity. A cancelled reference change closes the process because
no new identity was committed. `begin_turn`, `speak` and `finish_turn` require one
shared cancellation event; overlapping previews/turns are rejected. The public
application must serialize whole preview/conversation operations. `close()` at
application shutdown releases the worker, log and response reader.

`configuration='maintained'` selects `chatterbox-maintained-lock.json` and CUDA
explicitly. Legacy `cpu`/`cuda` experiment configurations remain available. This
adapter does not itself authorize a candidate for normal use: the runtime audit
and normal-app release gate must pass independently.

## No-cost control verification

Prerequisites: the development environment and normal test tooling from README.md.
Run this single PowerShell 7 command from the repository root:

```powershell
Set-Location C:/docs/git/tHead; ./scripts/chatterbox-app.ps1 -TestBackend -Avatar chatterbox-nano-1089 -Output .runtime/issue58-manual
```

This launches isolated synthetic fixture speech/media, with no models, GPU or paid
provider requests. It is a control/identity check, not a listening or latency gate.
In the browser, submit `multi-2`, press Stop, then submit `short-2`; repeat using
New conversation. Expect responsive controls, only the replacement turn, and the
same selected voice. Diagnostic `/experimental` faults remain in this opt-in
harness and are not ordinary public application controls.

Focused HTTP tests exercise real fixture-worker IPC, warm worker retention after
Stop/reset, stale media HTTP 410, explicit crash failure and subsequent recovery.
The historical test expecting worker death on Stop failed after the behavior
change; its replacement checks that the selected worker survives.

## Release decision

**Partial implementation; regular enablement remains blocked.** No native timing,
new headroom, crash-onset or human listening result is supplied by these changes.
Historical native CUDA worker reload took roughly 11 seconds and next speech
roughly 14 seconds. This change avoids that reload for ordinary cancellation but
cannot establish <=5-second replacement onset while obsolete synthesis drains.
Crash recovery still requires cold model loading and therefore does not clear
#58's <=5-second release criterion.

Before #58 closes, use the remediated #57 runtime and the finished normal-app route
to measure one cold start, ten warmed short/multi-phrase turns and at least ten
mixed interruption/recovery cycles including crashes and reference switches.
Record each cancellation, first PCM, browser digital onset with decoded moving
frame, complete ending/stalls, RAM/VRAM and worker release. Serialize shared-GPU
runs, retain failures, and distinguish digital onset from physical-speaker latency
and human listening confirmation. The normal-app handoff must document its one
preparation-and-launch command after those dependencies land. Do not present the
synthetic command above as native acceptance evidence.
