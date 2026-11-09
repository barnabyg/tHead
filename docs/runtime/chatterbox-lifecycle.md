# Bounded Chatterbox lifecycle (#58)

The adapter retains its model process after ordinary Stop/New conversation. One
outstanding JSON-lines request carries a worker epoch, request ID, turn ID and
reference ID/hash. Cancelled callers return promptly; their response is discarded
by identity before the next operation. Cancelled PCM never reaches the media
pipeline. Existing session cancellation still makes obsolete media return HTTP
410 and prevents it becoming context for a replacement turn.

The current source generates a whole phrase synchronously. It cannot interrupt a
native model call. Each adapter exposes `draining` while an obsolete operation
finishes, then reuses the model. Each operation has a 60-second watchdog even when
its caller has cancelled; initial model preparation has a 180-second response
limit. Fatal errors close the affected process. The regular app's bounded
`ChatterboxEngine` promotes its warmed standby and replenishes the failed slot;
there is no CPU/SAPI substitution or provider/context reset. `failed` and
`recovery_error` explain failure; `preparing` identifies a cold child load.

## Shared engine ownership

Normal integration owns one two-worker `ChatterboxEngine` for the application lifetime,
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

The [normal-app release sequence](chatterbox-release.md) passed with the remediated
runtime: ten warmed turns and twelve mixed recovery/switch cycles, all within
5 seconds, with stale media inaccessible and no stalls. The measured pool used
12,230 MiB peak device-wide VRAM, released its workers on shutdown and passed the
concise human speech/lip-sync check. The native guide provides the single
preparation-and-launch command. The synthetic command above remains a control
check, not native acceptance evidence. Historical single-worker reloads of about
14 seconds are retained as the baseline motivating the pool.

## Bounded two-worker recovery attempt

Hypothesis: retaining one already-prepared standby avoids model reloading on the
user's replacement request after Stop or a worker crash. The remediated candidate
has measured model allocations of about 2.30 GB (2.36 GB reserved), against the
historical FlashHead peak of about 6.8 GB on the 24 GB RTX 3090. This supports
investigating two workers; it does not establish combined peak headroom or latency.

Change: `scripts/chatterbox_engine.py::ChatterboxEngine` owns exactly two
`ChatterboxVoice` instances, initially prepared serially. Every fresh process
requires at least 8 GiB free VRAM and 8 GiB available RAM alongside the current
application. Failed admission is explicit. CUDA configuration is mandatory for
real conversational pooling, with no alternate model/device/voice substitution.

Stop or crash abandons the affected worker's turn and promotes the warmed survivor.
At most one finite background thread drains or rebuilds unavailable workers. Each
slot is attempted once per requested reference version; repeated reference churn
has a finite bound. There is no unlimited retry loop and no third process. If both
workers are draining/unavailable, a request fails clearly and can be retried after
readiness returns. Replenishment leaves the conversation, portrait and provider
accounting alone. It may contend with current GPU work; native measurement must
verify that performance remains acceptable.

Each worker has a generated private canonical-reference snapshot beside the
library's derived conditioning audio, preventing reference changes from rewriting
a still-draining worker's input. Two snapshots and their atomic temporary files
are removed on shutdown. Each worker retains the existing two-entry conditioning
bound and removes transient imports when switching away. All IPC retains the
request/epoch/turn/reference identity checks and detached-operation watchdogs.

Normal and experimental startup share the same shutdown owner. It signals the
active turn first, then attempts preparation/preview cancellation, upload-socket
release, server closure, storage-lease release, worker joins, speech-pool closure
and reference removal independently. A new database fault or bounded join failure
is reported only after the remaining cleanup has been attempted. The no-GPU HTTP
regression removes the database immediately before shutdown and verifies that
cached worker processes, import leases and derived reference files are released.

The pool implements the public SpeechVoice boundary and `set_reference` with the
same signature as the single-worker adapter. `fault` delegates explicit diagnostic
faults to the active worker. Metadata reports `ready_workers`, `worker_count`,
`replenishing`, `lifecycle_state`, admission measurements and any `recovery_error`.
The SpeechVoice protocol describes metadata as a readable property so both mutable
adapter metadata and computed pool status satisfy strict typing.

Deleting a saved voice also discards its unused conditioning from both workers
without unloading the current voice or its models. A hash shared by the active
voice stays available. The application briefly marks voice maintenance while
sending bounded discard commands outside its control/status locks. If damaged
metadata has lost the deleted reference's hash, it drops inactive cached/in-flight
conditioning instead, retaining the current voice's hash and warm models. Obsolete
workers apply pending discards after draining and before becoming ready. Pending
entries cover only hashes present or in flight in the two bounded worker caches
and disappear after acknowledgement. Per-worker cache sizes and process IDs in
speech-engine status support no-cost HTTP regression checks of release and reuse.

Measurement: the new HTTP fixture module first failed because the pool did not
exist. After implementation, the real fixture-worker IPC tests passed Stop/late
PCM isolation, promotion without waiting for a four-second obsolete synthesis,
and crash/survivor promotion with one replacement. These are synthetic correctness
checks. They provide neither native GPU timing nor physical-speaker evidence.
Ruff, strict mypy and Bandit pass for the implementation and HTTP harness.

Initial conclusion (before native measurement): bounded warm failover was ready
for integration, with native timing/resource gates outstanding. The subsequent
normal-app measurements linked above cleared those gates. Existing human quality
acceptance was preserved and the concise remediated/native checks were accepted.
