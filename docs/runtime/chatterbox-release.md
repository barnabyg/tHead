# Regular local voices: release evidence (#57–#62)

Target: native Windows 11 / NVIDIA GeForce RTX 3090, English Nano, CUDA 13.0.
CPU conversation and other GPU configurations are unavailable until separately
verified. FlashHead retains its existing isolated runtime and pins.

The [individual native results](chatterbox/native-release.json) cover the normal
Conversation app, real upload/decoding/storage, actual local synthesis, the real
provider fixture path and real FlashHead/browser playback. The runner rejects the
old experimental fixture harness. No paid provider request was made.

| Gate | Observed result |
| --- | --- |
| Fresh advisory review | 0 reported advisories across 81 PyPI versions; 2 immutable source projects reviewed separately |
| Interpreter | Independently acquired hash-pinned CPython 3.12.16 / Astral 20261026; OpenSSL 3.5.9 and Expat 2.9.0 |
| Clean checkout | Independent source/Python/wheel/model acquisition and exact 83-package preparation passed from a fresh branch-backed checkout |
| Regular approval | Native speech passed for all three saved avatars using that independently installed runtime, without a candidate override |
| Warm first speech | 10/10 within 5 s; median 2.423 s, range 2.2144–2.8326 s |
| Mixed recovery | 12/12 Stop/reset/crash/reference/shared-avatar/Zira/Hazel cycles passed; replacement/switch onset 1.6772–2.8978 s |
| Cancellation | 0.2485–0.8213 s; obsolete media returned HTTP 410 |
| Stalls / stale media / silent substitutions | 0 observed |
| Worker bound | Two speech workers, one finite replenisher; no third worker allowed |
| Peak resources | 12,230 MiB device-wide VRAM; 9,365,659,648 bytes summed process-tree RSS (about 8.72 GiB) |
| Shutdown | Workers released; derived reference snapshots removed; device-wide VRAM returned to desktop/driver range |
| Offline restart / removed source copies | Both voices and three avatars persisted; three actual speech onsets 2.2310, 1.9643, 2.0147 s |
| Missing engine | All five avatars/two saved voices retained; requested voice explicitly unavailable, no substitution |
| Damaged reference | Actual normal UI repair preserved the voice ID and both avatar assignments; repaired native speech/media completed |
| In-use deletion | Blocked with avatar names; deliberate avatar voice changes then allowed deletion without affecting the other voice |
| Cancel optional preparation | 0.1311 s; saved voices/avatars preserved and Zira stayed ready |
| Human confirmation, 9 November 2026 | Both concise remediated previews remained acceptable; normal-app speech completeness/intelligibility and lip sync accepted |

First-speech numbers combine **browser digital audio onset and a decoded moving
frame**. They do not measure physical-speaker latency. Cold engine preparation
and preview time are recorded separately; a warmed onset is not a cold-start
claim. Process RSS sums can count shared pages more than once. VRAM includes
desktop/driver activity; shutdown samples varied by tens of MiB, with task-owned
workers gone. This is bounded machine evidence, not a general hardware promise.

The [maintenance review](chatterbox/maintenance.md), exact final inventory,
Python/native component reviews and failed compatibility attempts remain
available. No Chatterbox advisory exclusions, warning baseline or new runtime
security exception was introduced. Repository maintainers own the pinned patch
series and the documented before-release/monthly update checks.

Two final validation failures are retained in the individual results: an inherited
development Python home broke a task harness launch, and relative paths became
invalid when FlashHead changed directory. Native interpreter isolation and public
path anchoring fixed them; the independently installed regular profile then
passed, including relative CLI paths. Late storage failures now leave built-ins
usable and release import leases safely for repair/restart.

Normal usage does not download Chatterbox until the user explicitly chooses
preparation. Speech is offline after preparation; reference audio and provenance
stay in private app-managed storage. The existing avatar schema/IDs and launch
aliases remain readable. The release profile must be re-reviewed when any
approved runtime, dependency or source-patch digest changes.

From **C:/docs/git/tHead**, the single no-cost native preparation-and-launch
command is:

```powershell
pwsh -NoProfile -File ./scripts/voice-native-demo.ps1
```

See [cloned voices](cloned-voices.md) for prerequisites and the concise manual
scenario. After preparing once, append `-Offline` to check prepared offline
startup. Use the bundled licensed reference, preview/Stop/replay/save, assign it to
two avatars, speak/switch/Stop/reset, restart after removing the upload source,
then try in-use deletion and explicit repair. Expect correct complete speech,
moving media and stable identities with actionable errors. The protocol-only
fixture command in that guide is available without a GPU.

The full canonical verification command is
`uv run --locked python scripts/verify.py`. Its final result and the independent
clean-checkout installation result are recorded with the release handoff.
