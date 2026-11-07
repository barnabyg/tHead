# Configured avatars and local voices (#30)

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
