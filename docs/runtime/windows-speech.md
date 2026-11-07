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

## Progressive speech

Text is normalised only for whitespace. Sentence-ending `.`, `!` or `?` followed
by whitespace is a preferred boundary; sentences over 180 characters split at
the last whitespace within that limit. A single longer word is rejected.
Abbreviations can therefore create a prosodic break. Final text needs no
punctuation. Separate sentence synthesis may change intonation; this is the
latency/continuity trade-off of the lightweight engine.

The producer synthesises one bounded phrase, then hands off ordered 15,360-sample
windows (0.96 s). It joins leftover samples to the next phrase without inserting
silence or padding phrase boundaries. Only end-of-text sends a final partial
window, including an explicit empty drain marker after an exact full window.
One voice, rolling avatar history, motion state and continuous encoder remain in
use across phrase boundaries. No substitute speech is supplied while waiting.
The next phrase is synthesised only after queued windows from the preceding
phrase have been consumed. This limits synthesis lookahead; a short passage can
still finish synthesis before playback and is labelled accordingly in evidence.

There are at most two queued PCM windows, one in-flight phrase (at most 30 s),
120 s total speech and 1200 text characters. Producer handoff applies backpressure
with a five-minute hard limit. Phase 2's eight-frame fragments, 2.88 s media
horizon and **1.28 s progressive startup buffer** are retained. A complete short
utterance below that buffer starts after the encoder drains. Browser media older
than two seconds is evicted during playback. Real text/voice timing must still be
measured; CPU protocol probes do not establish sound or continuity.

## Stop and recovery

Stop pauses and detaches the browser's media synchronously, revokes its object
URL and aborts media fetches before sending the server request. A browser epoch
invalidates pending start responses; run IDs reject old media/input/telemetry.
Repeated Stop is harmless. New input is enabled after the old GPU owner and
speech producer release; already loaded model resources remain reusable.

Native GPU inference cannot be preempted mid-call. Its result is discarded after
Stop. Browser digital silence is sampled separately (10 ms timer, 256-sample
audio analyser, two silent observations, five-second observation limit); this is
an audio-graph observation, not physical speaker latency. A replacement run
cancels an outstanding silence observation to avoid attributing new speech to
the old run. Results record `stop-handled`, `generation-abandoned`,
`tts-released` and `resources-released` separately.

TTS waits poll cancellation every 50 ms. Cancelling active native synthesis kills
its worker and waits at most 10 s plus a 5 s pipe-reader join; the next submission
reloads the voice. The producer must join within 30 s before accepting another
run. Encoder shutdown kills FFmpeg, waits at most 30 s and joins its three
threads for at most 5 s each. Inference has no reliable thread-level kill: if it
hangs, the outer two-hour process-tree supervisor is the final limit. Stop
silence should not be confused with those resource-release limits. PCM, pending
phrase, media queues and per-run events (2000) are bounded; repeated runs reuse
one GPU pipeline and one TTS worker rather than accumulating loaded copies.

For explicit failure injection, append `-Diagnostics` to the same launcher.
Choose **Fail local TTS** or **Fail media**, Start, expect a clear failure, reset
the fault to None and submit the example again successfully. **Delay synthesis**
allows Stop before first audio. These controls are unavailable without the flag;
the CPU protocol test backend also enables them but produces no playable media.
**Delay buffering** holds transport below the startup margin for three seconds,
allowing Stop during buffering without altering the selected profile.

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
revalidate after updates. `speech-lock.json` pins the three installed Zira voice
file hashes and token; startup fails if they differ. Revalidation and a lock
update are needed after a changed voice installation.
The engine is an installed prerequisite, not a package
download implicitly performed by the launcher.

Piper was considered: a local CPU alternative, but its GPLv3 engine and separately
licensed voice models add acquisition, dependency and resampling requirements.
Zira's measured CPU synthesis is comfortably faster than speech duration in the
initial isolated probe; concurrent GPU timing and perceptual quality still need
integrated measurement. Do not infer conversation feasibility from isolated TTS.

## Repeating the measurements

Start the demonstration with `-Diagnostics`, submit the declared passages through
the browser, and run this bounded resource monitor concurrently in another
PowerShell 7 terminal from the clone root:

```powershell
./.runtime/venv/Scripts/python.exe scripts/assess_speech.py --monitor-seconds 360 --output .runtime/speech-resources.json
```

After playback and recovery probes finish, summarise server/browser timings,
PCM handoff hashes and decode every completed published media stream:

```powershell
./.runtime/venv/Scripts/python.exe scripts/assess_speech.py
```

The report is `.runtime/speech-assessment.json`. Audio onset uses a 25 ms browser
timer, an RMS threshold of 0.00001, and an independent frame-presentation callback;
server receipt adds loopback overhead. It is digital output, not speaker latency.
The resource monitor samples the whole GPU/system plus matching app/TTS processes;
other desktop/development activity is included, so it is observational contention
evidence rather than an isolated causal benchmark. Run GPU demonstrations serially.
