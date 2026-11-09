# Local cloned voices

The private voice library and normal-app cloning controls support the approved
native Windows / RTX 3090 CUDA profile after explicit optional preparation.
[Release evidence](chatterbox-release.md) records the maintenance, recovery and
native end-to-end gates. Changed runtime/dependency/source-patch digests remain
unavailable until revalidated. Zira/Hazel require no Chatterbox download.

## One-command manual check

Prerequisites: Windows 11, PowerShell 7, uv 0.11.7, Node 24.14.1 for development
checks, and internet for first acquisition of the hash-pinned FFmpeg tools and
development Python dependencies. No API key, model download or GPU is needed
for this fixture. Run from **C:/docs/git/tHead**:

```powershell
pwsh -NoProfile -File ./scripts/voice-library-demo.ps1
```

Open [the local app](http://127.0.0.1:8769). Data stays in
`[IO.Path]::GetTempPath()/tHead-voice-manual`, independently of your normal app
data. Restart the same command to reopen it; `-UserData` accepts a different
isolated directory and `-Port` selects a free port. The server has a two-hour
lifetime and its supervisor has a finite teardown margin. Ctrl+C stops it.

1. Settings → Voices → Clone voice. Choose the bundled
   `docs/runtime/chatterbox/reference-1089-10s.wav`, name it, confirm recording
   permission and select Preview. The recording is a licensed LibriSpeech excerpt;
   its attribution is in [ATTRIBUTION.md](chatterbox/ATTRIBUTION.md).
2. Stop/replay the preview and Save. This fixture produces protocol audio and
   substitute browser media; it does **not** demonstrate cloned speech, quality,
   lip synchronisation or physical-speaker latency. A saved voice does not select
   itself or invoke a provider.
3. Back to Settings → Create avatar. Give two avatars different names/portraits
   and the same saved voice. Select them between turns, then Zira/Hazel. Ask uses
   free fixture text. Stop and New conversation must remain responsive.
4. Restart the command; both avatars and the voice remain. Try deleting the
   voice: the app identifies its avatars and refuses. Edit/delete those avatars
   deliberately before deleting the voice. Rename changes its label, not its ID.
5. Start another clone, choose invalid audio, correct it, then Cancel or navigate
   away during preview. Expect understandable errors, preserved form fields,
   inaccessible obsolete preview audio and no saved voice. Save is serialized;
   cancellation/navigation waits for its atomic result to avoid hiding a save.

Moving or deleting an uploaded source file does not affect a saved voice. The
app stores canonical audio, never its original path. For a missing/corrupt
reference, retain the avatar and use Voices → Repair, preview the replacement and
save explicitly; its voice ID and avatar assignments stay intact. Repair requires
an available approved engine; it is exercisable in the fixture.

## Storage and limits

The normal app uses `%LOCALAPPDATA%/tHead`, or an explicit `-UserData` /
`THEAD_USER_DATA`. Existing `avatars.sqlite3` columns and IDs are unchanged.
Additive voice tables and usage triggers share its transactions; old avatar
records and launch aliases remain readable. Back up the complete database while
the app is closed. A corrupt record is retained for repair; healthy voices and
built-in avatars remain usable. Database-level corruption needs backup recovery.

One WAV/MP3/M4A upload is limited to 20 MiB. Actual decoded audio must be over 5
and at most 30 seconds, one audio stream, one/two channels and 8–96 kHz. Canonical
audio is mono 24 kHz PCM16 WAV. Pinned local FFprobe/FFmpeg validate the actual
container and decoding, with finite 180-second operation limits. Recommend quiet
10–20-second English single-speaker speech. Format checks cannot establish
permission, speaker count, recording cleanliness or clone quality.

Audio-tool preparation downloads the pinned FFmpeg archive from the publisher's
[versioned GitHub release](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2).
The archive checksum and executable checksums remain mandatory. This mirror
avoids repeated HTTP 503 responses from the publisher's package host.

Uploads, decoding, reference conditioning and previews stay on this PC. Cloning
does not send recordings to a provider, enter transcripts, charge the budget or
write source audio into logs/tracked configuration. Temporary candidates expire;
Cancel removes them, save is atomic/idempotent, and deletion is blocked while an
avatar uses a voice. Opaque IDs determine storage; names and client filenames do
not become server paths. No server-path/URL import is accepted.

## Real native use

For the isolated **native manual check**, use the normal launcher path with
real local speech, real FlashHead media and free fixture provider text. From
`C:/docs/git/tHead`, with Windows 11, PowerShell 7, Git, uv 0.11.7, the normal
FlashHead prerequisites, an RTX 3090/CUDA-13-compatible driver, 20 GiB free disk
and at least 8 GiB free RAM/VRAM alongside FlashHead:

```powershell
pwsh -NoProfile -File ./scripts/voice-native-demo.ps1
```

This explicitly prepares the hash-pinned Python/source/packages/model in an
isolated environment and opens the normal app at
[port 8771](http://127.0.0.1:8771). Follow the same short clone/preview/save/shared
avatar scenario above; this mode produces real cloned speech and moving
portraits. Data and the fixture budget are isolated in the temporary
`tHead-voice-native` directory. `-UserData`, `-ChatterboxState` and `-Port` select
independent test locations. After preparation, disconnect the network and repeat
preview/conversation; no speech request downloads anything. Ordinary `run.bat`
continues to use the regular release gate.

The diagnostic CLI `-CandidateChatterbox` requires `-Diagnostics`,
`-FixtureProvider` and an explicit isolated `-UserData`. It cannot turn a paid
provider request into a hidden fallback. In this mode, ask
`Fixture speech: The final words should be complete.` for exact free fixture
speech through the normal provider/conversation path. All other questions retain
the existing fixture answers. Diagnostic worker crashes use the session-bound
`/voices/diagnostic` API; no crash control is added to the ordinary UI.

Voices → **Prepare local voices** starts an explicit bounded setup job when
the runtime is eligible. **Preparing local voices** keeps **Cancel preparation**
visible and prevents duplicate starts. **Setup complete — ready to clone voices**
appears only after the backend reports the engine available; **Clone voice** then
becomes usable. Returning with an installed, available engine shows **Ready to
clone voices** without starting downloads. Failure and cancellation keep an
explicit outcome and **Retry voice preparation** action. Device/runtime blockers
remain visible and prevent cloning. Zira/Hazel remain usable while optional
preparation runs. Select
Zira/Hazel before changing an installed cloned-voice environment. Interrupted
setup preserves the existing voice library and verified acquisition state.

### Preparation status manual check

Use the native prerequisites above. From **C:/docs/git/tHead**, use initially
absent isolated directories for the first run:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -FixtureProvider -Diagnostics -InitializeBudget -UserData "$env:TEMP/tHead-preparation-ui-data" -ChatterboxState "$env:TEMP/tHead-preparation-ui-engine" -Port 8771
```

Open Settings → Voices. Expect setup to be required and Clone voice disabled.
Start preparation, cancel once, then retry and allow setup to finish. Expect
the explicit completion message, an enabled Clone voice action and no stale
request, cancellation or error message. Navigate away/back, reload, and restart
with the same command: readiness should remain clear without another setup
attempt. An unavailable device/runtime should show its blocker and leave
Zira/Hazel and existing avatars intact. This check uses real optional downloads
and GPU setup; browser tests substitute deterministic preparation API responses.

Use the [maintenance candidate guide](chatterbox/maintenance.md) for the isolated
research runtime and short offline regression previews. The approved profile is
available through regular startup. The normal app shows the release blockers and
refuses preview/selection with an unapproved engine;
it never falls back to CPU, SAPI, another model or a hosted service.

The supported conversational candidate is native Windows/RTX 3090 CUDA only.
CPU is unproven for conversation. RAM/VRAM admission, ten warmed turns,
mixed interruption/crash recovery, clean preparation and concise human
speech/lip-sync confirmation are recorded in the release evidence. Automated browser
onset measures digital audio plus decoded frames, not physical-speaker latency.
