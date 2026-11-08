# Saved avatar voice investigation (#48)

Investigated 8 November 2026 from `5d414a1ef43506c39eb857a815b3a3419f87ac66`
on native Windows build 26300. The reported unexpected voice change was not
reproduced. No speculative fix was applied. Original/later voice names, triggering
sequence and whether a restart occurred remain unknown.

## Baseline and method

Success means retaining the saved voice reference through creation, selection,
switching, subsequent turns and restart, and synthesising with that reference
or reporting an unavailable voice. No silent substitution is acceptable.

From `C:/docs/git/tHead`, existing deterministic HTTP tests ran with:

```powershell
./.venv/Scripts/python.exe -W error -m unittest discover -s tests -p test_conversation.py
```

All 14 tests passed in 80.226 s. Initial sandbox socket error 10013 disappeared
outside the sandbox; it was an execution restriction. Focused browser checks:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = 'C:/Users/Bob/AppData/Local/ms-playwright'
$env:THEAD_TEST_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
./node_modules/.bin/playwright.cmd test --grep 'create a named avatar|saved portrait survives|PNG creation and saved avatar preparation|interrupted creation' --workers=4
```

Four tests passed in 7.3 s. These cover explicit Hazel storage/selection and a
response, source removal/restart, unavailable-voice preparation/recovery and
interrupted storage. Fixtures replace speech/GPU media and do not verify audible
identity. Native synthesis below is a separate adapter probe, not synchronised
avatar playback or human listening.

## Investigation record

1. Hypothesis: persistence or catalogue order changes the saved voice. Inspected
   stable `zira`/`hazel` references, SQLite voice storage and direct lock mapping;
   existing creation/restart checks passed. No ordering-based selection or saved
   rewrite was found. Unknown reporter sequences remain unproven.
2. Hypothesis: SAPI chooses a different voice. Native `Voice.prepare`/`speak`
   synthesised the same passage Zira → Hazel → Zira → Hazel, closing each worker:
   “The river flows quietly through the town. Today we are testing the same short
   English passage.” Each voice passed pinned asset checks and returned its
   declared token. Zira (`TTS_MS_EN-US_ZIRA_11.0`) produced 104960 samples;
   Hazel (`TTS_MS_EN-GB_HAZEL_11.0`) produced 121440 samples, mono PCM16 at
   16 kHz. Each voice's repeat was byte-identical; the two voices differed.
   No substitution reproduced. Cross-turn worker reuse with avatar playback
   still needs native application verification.
3. Hypothesis: restart changes selection, perceived as a voice change. Startup
   does not persist selection: explicit `-Avatar`/`--avatar`, `THEAD_AVATAR`,
   legacy `THEAD_PAIR`, then JFK/Zira determine the launch avatar. Saved avatar
   voice references are independent. Restart without an override starts JFK;
   reselect the saved avatar before comparing. This is an observed distinction,
   not an established cause of the report.

Missing voices fail preparation: exact name selection, token and English culture
checks reject mismatches. A failed preparation disables readiness and reports
recovery instructions. No intentional silent default-voice substitution exists.

Because there is no failing reproduction, diagnosis stopped before cause-specific
instrumentation or a regression fix. These observations narrow uncertainty;
they do not establish that the unidentified perceptual symptom is resolved.

## Native manual verification

Working directory: `C:/docs/git/tHead`. Prerequisites: Windows 11, PowerShell 7,
Python 3.12, uv, pinned CUDA/RTX 3090 runtime/model assets, installed supported
Zira/Hazel Desktop voices and a compatible H.264/AAC browser. See
[conversation setup](windows-conversation.md). One preparation-and-launch command:

```powershell
./run.bat -FixtureProvider -InitializeBudget -Diagnostics
```

Create an avatar with Hazel and a local portrait. Save, explicitly select it and
ask a question, then a follow-up. Switch to JFK and back and speak again. Restart
with the same command, explicitly reselect the saved avatar and ask again.
Expect Hazel throughout with synchronised portrait playback, or an actionable
unavailable-voice error. The immediate default JFK voice after restart does not
demonstrate a changed saved voice.

The “Unavailable Desktop voice” diagnostic should give a preparation error with
Ask disabled. Selecting a healthy avatar recovers without losing context. This
simulates error handling rather than a real missing Windows installation.
Native listening and synchronised avatar playback for this exact report remain
unverified. No paid provider requests were made.

## Details needed if it recurs

Record avatar name, original/later perceived voices, exact sequence, restart,
Stop and switching events, and whether the same avatar was explicitly reselected.
Capture the active avatar shown in Settings, saved voice reference and loading
TTS name/token from `/status`, plus preparation errors. Preserve the database
before changing it; it contains personal portraits. A minimal reproduction with
these details is needed before changing persistence or worker reuse.
