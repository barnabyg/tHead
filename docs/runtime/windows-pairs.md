# Configured avatars and local voices (#30–#32)

From `C:/docs/git/tHead` in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -Pair hopper-hazel -Diagnostics
```

This command prepares pinned runtime/media/portraits and launches
http://127.0.0.1:8765. Wait for idle. Omit `-Pair` for `jfk-zira` (the existing
default), or use `-Pair jfk-zira`. `THEAD_PAIR` supplies the stable ID when no
flag is given. Unknown IDs fail before preparation. Python's `--pair` uses the
same IDs. See [the conversation guide](windows-conversation.md) for backend
credentials, persistent budget, GPU and tool prerequisites. Only first real use
adds `-InitializeBudget`; subsequent launches reuse the real ledger.
`-FixtureProvider` uses a separate simulated ledger and no paid text requests,
with real local speech/GPU/media. First fixture use needs `-InitializeBudget`.
CPU `-TestBackend` media is not playable.

`-Port 8876` selects an isolated loopback port (default 8765); its URL is
http://127.0.0.1:8876. A port already owned by another server is rejected rather
than allowing duplicate Windows listeners to serve the wrong application.

The launcher downloads both declared portraits and verifies SHA256.
`avatar-pairs.json`, `speech-lock.json` and `hazel-lock.json` pin acquisition and
expected bytes. Portrait decoding, voice files, exact Desktop name/token and
English culture are checked before readiness. Changed/missing assets produce
errors; no fallback is permitted. The model loads once per process; motion state
resets per response as before.

| Stable ID | Portrait | Local synthetic voice |
| --- | --- | --- |
| `jfk-zira` | John F. Kennedy | Microsoft Zira Desktop, en-US |
| `hopper-hazel` | Grace Hopper | Microsoft Hazel Desktop, en-GB |

These are synthetic demonstrations, without voice likeness or endorsement.
JFK's [official White House portrait](https://commons.wikimedia.org/wiki/File:John_F._Kennedy,_White_House_color_photo_portrait.jpg)
is a US federal public-domain work (Cecil Stoughton / White House).
Hopper's [official Navy portrait](https://commons.wikimedia.org/wiki/File:Grace_Hopper.jpg)
is public domain in the US; requested credit: James S. Davis / U.S. Navy,
[NH 96919-KN](https://www.history.navy.mil/our-collections/photography/numerical-list-of-images/nhhc-series/nh-series/NH-96000/NH-96919-KN.html).
Windows supplies voices under Microsoft's terms; files are not redistributed.
Existing FlashHead/model/media terms and pins continue to apply.

Do not assume Hazel is installed. Microsoft's
[voice installation instructions](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices)
list Hazel under English (Great Britain): Narrator settings → Add legacy voices →
Manage voices/Add voices → English (Great Britain). Install the legacy Desktop
voice and verify availability to `System.Speech`, not merely Narrator.
No registry copying or automatic installation is performed. From PowerShell 7:

```powershell
powershell.exe -NoProfile -NonInteractive -Command 'Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; try { $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo | Select-Object Name,Culture,Id } } finally { $s.Dispose() }'
```

Expected tokens: `TTS_MS_EN-US_ZIRA_11.0` and `TTS_MS_EN-GB_HAZEL_11.0`.
Windows updates may change hashes; investigate/review pins instead of bypassing
validation. Both voices were enumerated on this Windows 11 build 26300 host;
Hazel produced 114880 PCM16 bytes (3.59 s) in a native probe. This is digital
evidence, not listening confirmation. Fresh voice installation is untested.

For each pair ask “What is a black hole?”, wait for its complete spoken ending,
then ask “How do we detect one?”. Expect context, chosen portrait and assigned
voice throughout. Stop an answer, ask a replacement, then use New conversation
while busy: old media must remain absent and the fresh answer must have no prior
context. Listen/view for clear continuous speech, moving lips, approximate
synchronisation and complete endings. Phase 6 evidence distinguishes native
digital results from listening confirmation.

## Between-turn selection (#31)

Choose **Avatar and voice** after playback ends or after Stop releases resources.
The labelled active pair changes only when portrait and voice preparation finish;
Ask and the selector remain disabled during preparation. Stop and New conversation
remain usable. Switching keeps the transcript/context; New conversation clears
context while retaining the chosen pair, including during preparation. No model
reload occurs. Old media routes expire when a switch is accepted. Each response
records its selected pair, session and unique response identity.

Concurrent selection requests are **rejected**, never queued or superseded. Wait
for readiness or an error before another selection. An API selection during
generation or unended playback returns a conflict; Stop permits recovery after
resource release. Preparation performs no LLM request and changes no budget.

Demo: complete the black-hole answer with JFK/Zira, select Hopper/Hazel, ask the
contextual follow-up, Stop an answer, switch back and ask a replacement. For a
loading check with `-Diagnostics`, choose **Pair diagnostic → Delay preparation**,
switch, then click New conversation and Stop during loading. Expect the chosen
pair to become ready in the new empty conversation, without old playback.

## Failure and recovery (#32)

Failed preparation leaves **Active pair** showing the last successful pair and
the selector showing the failed requested pair. Ask stays disabled. The error
names the requested pair and remediation. Choose an available pair to recover;
the transcript and budget remain intact. A candidate voice is disposed if portrait,
voice validation or avatar preparation fails; portrait/voice activate together.
There is one preparation job and at most two voice owners during handoff, with
no per-selection model cache. Stop does not cancel the chosen pair's preparation;
it detaches response playback. New conversation retains preparation/choice while
clearing context. Because pending switches are rejected, a delayed completion
cannot supersede a later accepted selection.

Controlled failure scenario, without editing application internals: launch the
command above with `-FixtureProvider` (initialise its separate ledger on first use).
Complete an answer, choose **Pair diagnostic → Fail after partial preparation**,
then select the other pair. Expect a named error, unchanged last active pair and
disabled Ask. Choose **None**, select the available original pair, and ask the
follow-up; context must survive. Repeat with missing/unreadable/invalid portrait,
unavailable Desktop voice, invalid voice assets and delayed failure. During delayed
failure, use New conversation: expect empty context, retained failed choice and
the same recoverable error. These controlled diagnostics simulate failures and
are available only with diagnostics/fixture launch flags; they never call the LLM.

## Bounded native evidence capture (#33)

Install browser verification tooling (`npm.cmd ci --ignore-scripts` and
`npx.cmd playwright install chromium`) once. With the app ready from the launch
command above plus `-FixtureProvider`, run from the same directory:

```powershell
node ./scripts/pair-assessment.cjs ./my-pair-fixture-evidence.json
```

It requires a new output path and saves raw evidence after each complete turn or
switch. It warms both pairs, runs ten alternating-pair prompts (including black
hole/follow-up), then Stop/replacement, busy reset, partial-preparation failure and
recovery, and reset during loading. First/repeat switches and server preparation
are separate from Submit-to-digital-audio-with-advancing-video. The five measured
turns per pair exclude two warm-ups and separate recovery probes. Failed attempts
remain in the report. Playback must complete without autoplay intervention to be
valid. It has finite three-minute operation and thirty-minute overall limits.

For real-provider timing, restart without `-FixtureProvider` using the durable
real ledger and explicitly add `--real` to the evidence command. This opts into
at most 18 paid requests and USD 0.05 additional conservative reservations at the
declared gpt-6-luna rates; there are no automatic retries. The monthly guard still
applies. For an isolated app port set `$env:THEAD_URL = 'http://127.0.0.1:8876'`
in the evidence command's terminal. Never point real evidence at the fixture
ledger or reset existing accounting. Reports deliberately save prompts/answers;
they are opt-in artifacts, unlike the session-only application itself.

For an additional no-cost check of audible Stop in both pairs, use the same
fixture app and evidence command with `--stop-only`. It waits for moving playback
and a non-silent browser audio graph, Stops, requires observed digital silence,
and completes a replacement response for each pair. This uses four fixture
requests and cannot run in real-provider mode.

With the app launched using `-FixtureProvider -Diagnostics`, run:

```powershell
node ./scripts/pair-assessment.cjs ./my-audible-stop-evidence.json --stop-only
```

Expect observed digital silence and a complete replacement response after Stop
with each pair; the output must report `complete: true` without errors.
