# Private local voice library

The library stores canonical reference audio and metadata in the existing private
`avatars.sqlite3`, normally `%LOCALAPPDATA%/tHead/avatars.sqlite3`. `-UserData`
selects an isolated test directory. Existing avatar columns, portraits, IDs and
built-in Zira/Hazel values are unchanged. New tables are additive transactions;
an interrupted schema or save operation rolls back without migrating old records.

A saved voice has an opaque `voice-…` identity independent of its display name.
Multiple avatars can share it. The app retains the prepared reference, so moving
or deleting the original recording has no effect. It stores the engine identity,
canonical/source SHA-256, duration, sample/channel metadata, creation time and the
user's permission confirmation. It does not retain the source filename, browser
path, transcript or original compressed input, and does not upload audio or log
its contents. The user-data directory inherits normal Windows user permissions;
use a directory private to your account.

## Import limits and preparation

Use a recording you own or have permission to use. Prefer 10–20 seconds of clean,
quiet English speech from one speaker. Format validation does not detect multiple
speakers, noise or clone quality; the synthetic preview is the quality check.

- Input: one actual WAV, MP3, or M4A (AAC/ALAC), at most **20 MiB**.
- Decoded speech: **longer than 5 seconds and at most 30 seconds**.
- Source: one audio stream, 1–2 channels, 8–96 kHz; video is rejected. This bounds
  accepted source samples to 2,880,000 per channel (5,760,000 in total).
- Canonical reference: mono, 24 kHz, PCM16 WAV, at most 720,000 samples. Conversion
  changes channel/rate representation without cropping the spoken content. The
  engine applies its own pinned conditioning to this reference.
- FFprobe and FFmpeg each have a three-minute deadline, bounded diagnostic output,
  restricted local file/pipe protocols, and cancellation that terminates the tool.
  Decoder failure, invalid metadata, excessive actual samples or a misleading file
  extension rejects the import. A bounded decode checks actual sample duration;
  encoded MP3/AAC container padding alone is not counted as spoken content.

Only four pending imports are allowed. Temporary imports are separate from saved
voices and expire after one hour. Each application session holds a lazy local OS
lock and marks its candidates with an opaque owner identity. A new startup/import
immediately removes candidates whose owner process has died; another live app's
locked imports remain intact. Graceful shutdown closes the store, removes its
pending candidates and releases its lease. Cancel removes a candidate immediately;
decoder temporary files are removed on success/failure/cancel. Owner-scoped orphan
directories are removed with their dead session. Legacy directories without an
owner marker are removed after ten minutes, beyond the total bounded decoder
lifetime. Saved voice records and idempotent-save receipts survive this cleanup.
SQLite reuses freed pages and
zeros deleted record content (`secure_delete`); deletion is not a claim of forensic
erasure from disks or backups.

Names contain 1–80 characters without control characters. Saved names are unique
case-insensitively and cannot collide with Zira/Hazel catalogue names. A temporary
candidate may have the same name as a saved voice; final Save validates a corrected
name atomically. A successful synthetic preview is required before Save. Duplicate
Save submissions for one candidate return the same saved identity. Save never
implicitly changes an avatar.

Rename preserves identity. Delete identifies avatars using a voice and refuses
until they have deliberately been changed. A shared-database transaction and
triggers prevent concurrent assignment/deletion races. Missing/corrupt references
remain listed as unavailable; explicit Repair replaces reference bytes after a new
preview while preserving voice identity, name and avatar assignments. Healthy
records remain usable. Back up the whole database before moving user data.

Readiness verifies both the saved metadata schema and the actual canonical WAV,
including matching identity/name, engine/provenance, hashes, duration, sample rate
and channel count. Malformed records stay stored and appear unavailable; they do
not prevent healthy records from being listed. If an identity/name column itself
is damaged, the catalogue uses a safe unavailable display entry and explains that
the database must be preserved/restored. It does not silently invent a replacement
voice identity or rewrite the corrupt record.

Relative user-data paths are anchored when a store is opened, so model-loading
changes to the process working directory cannot redirect subsequent reads/writes.
If the database later disappears or becomes unreadable, the voice catalogue
reports an actionable storage error while built-in voices remain available. Reads
never create an empty replacement for a missing database. Restore the original
database or a backup and reopen the application to retry.
Shutdown still releases the session lease after a known storage failure; pending
imports are reaped when the repaired database is reopened.

## Test launch and short manual scenario

Prerequisites: Windows 11, PowerShell 7, Python, uv 0.11.7, the repository's locked
development environment, and network access for the first explicit tools download.
This command prepares only the pinned FFmpeg tools and starts the normal app with
an isolated user-data directory and the no-cost protocol fixture backend. From
`C:/docs/git/tHead`, run this **one command** in PowerShell 7:

```powershell
uv run --locked python scripts/prepare_voice_media.py; if ($LASTEXITCODE -eq 0) { pwsh -NoProfile -File ./scripts/conversation.ps1 -TestBackend -UserData "$env:TEMP/tHead-voice-library-review" -Port 8771 }
```

Open [the local test app](http://127.0.0.1:8771), then Voices → Clone voice. Choose
`docs/runtime/chatterbox/reference-1089-10s.wav`, name the voice and confirm permission.
The bundled reference has [CC BY 4.0 provenance](chatterbox/ATTRIBUTION.md).
Preview, Save, Rename, and assign it to two test avatars. Copy the source recording
elsewhere, restart with the same command, and confirm the saved voice still exists.
Attempt deletion: both avatars must be identified and deletion blocked. Change
both avatars to Zira/Hazel, then delete the voice.

The fixture verifies UI/API/storage behavior; its preview is a labelled generated
protocol signal, **not evidence of cloned speech quality or native timing**.
Regular Chatterbox enablement and real offline preview remain subject to #57–#62
security, lifecycle, native Windows/RTX 3090 and human-listening release gates.
Existing Zira/Hazel use does not need these audio-import tools or a Chatterbox model.

## Public storage/API boundary

`VoiceStore` in `scripts/voices.py` exposes `import_audio`, `candidate`, `reference`,
`mark_previewed`, `save`, `cancel`, `read`, `list`, `rename`, `usage`, `delete` and
`repair`. It accepts uploaded bytes plus a format filename, never a reference path
or URL. HTTP consumers use the normal app's session-scoped `/voices/import`,
`/voices/preview`, `/voices/save`, `/voices/cancel`, `/voices/rename` and
`/voices/delete` operations; preview runs fixed local text and never calls a model
provider. Cancel/back invalidates the operation before deleting temporary state.

`tests/test_voices.py` exercises this public storage boundary using synthetic WAV,
MP3 and M4A recordings and the actual pinned tools. HTTP/browser coverage belongs
to the consuming application tests. It includes source removal/restart, format and
size/duration/channel/rate limits, names, cancel, pending-import bounds, idempotent
save, interrupted transactional save, shared-avatar deletion and explicit repair.

## Decoder pins and notices

`demo-lock.json` pins the Gyan FFmpeg 9.0.2 essentials archive by HTTPS URL and
SHA-256. `voice-media-lock.json` additionally pins the exact FFmpeg and FFprobe
executable SHA-256 values, independently checked against that verified archive.
`scripts/prepare_voice_media.py` is explicit acquisition: it downloads no speech
models, starts no GPU workers, uses no paid calls, and retains the build's `LICENSE`
and `README.txt` beside the tools. Imports recheck executable pins on file changes;
they never download or silently choose a system decoder.

This build includes GPLv3 software and third-party codecs. Its licence/notices are
not covered by Chatterbox's MIT declarations. The repository downloads rather than
redistributes these binaries; anyone bundling them must review the build's complete
licence and corresponding-source obligations. Update the archive and executable
pins together, review upstream security/licence changes, rerun actual supported
format tests and confirm a clean preparation before accepting a new decoder build.
