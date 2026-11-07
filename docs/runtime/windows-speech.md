# Local English text to avatar

From `C:/docs/git/tHead` (or your clone root), run this single preparation/launch
command in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/speech-demo.ps1
```

Prerequisites: the native Windows/RTX 3090 prerequisites in
[windows-demo.md](windows-demo.md), PowerShell 7, Python and uv on PATH, and the
Windows desktop voice **Microsoft Zira Desktop**, en-US, token
`TTS_MS_EN-US_ZIRA_11.0`. There is no automatic alternative voice or hardware.
If missing, install English (United States) in Windows Speech settings, Manage
voices, Add voices, then verify the desktop voice exists. See Microsoft's
[voice acquisition guide](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices).
The launcher prepares the same pinned source, public portrait, GPU environment
and FFmpeg as Phase 2, then opens `http://127.0.0.1:8765`. Stop other servers on
that port first. Server lifetime is bounded to two hours, including child cleanup.
Declared caches/assets live in `.runtime/`, as documented for the offline demo.

Select **Entered English text**, enter a passage, and click Start. Empty text and
more than 1200 characters are rejected; only one response runs at a time. Example:

> Hello. This is a local text to speech demonstration. The avatar should speak
> this passage clearly, then finish without repeating any words.

Expect local synthetic English speech, a moving portrait, and a clean ending.
Listen for missing/repeated words and look for approximate lip synchronisation.
Try Stop before speech and during playback, then submit another passage in the
same application. Click Play audio/video if browser autoplay is blocked.
No LLM or hosted TTS is involved. The prerecorded streaming and offline launchers
remain available independently.

## Engine and reproducibility

Synthesis uses Windows PowerShell 5.1's framework `System.Speech` 4.0.0.0 and the
fixed installed Zira 11.0 voice, rate 0, volume 100, on CPU. It requests mono
16 kHz signed PCM16 directly using `SpeechAudioFormatInfo`; no resampling is
required. JSON stdin carries plain text, never executable commands or SSML.
The worker and voice stay loaded between normal runs. Native engine details and
cold combined readiness are exposed in `/status`; per-run timings are in
`.runtime/speech/<run>/result.json`.

Windows supplies the engine/voice under its own licence; no Windows voice files
are redistributed here. Install them through Windows rather than copying
personal assets. OS servicing may change the voice: record OS/file versions and
revalidate after updates. The engine is an installed prerequisite, not a package
download implicitly performed by the launcher.

Piper was considered: a local CPU alternative, but its GPLv3 engine and separately
licensed voice models add acquisition, dependency and resampling requirements.
Zira's measured CPU synthesis is comfortably faster than speech duration in the
initial isolated probe; concurrent GPU timing and perceptual quality still need
integrated measurement. Do not infer conversation feasibility from isolated TTS.
