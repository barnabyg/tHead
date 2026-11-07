# Windows conversational application

From `C:/docs/git/tHead`, in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1
```

Prerequisites: Windows 11, RTX 3090 with the pinned native CUDA driver/runtime,
Python 3.12, uv 0.11.7, Git, PowerShell 7, Microsoft Zira Desktop English voice
and the installed assets in `speech-lock.json`. Use an H.264/AAC MediaSource
browser (Chrome/Edge). See [the speech guide](windows-speech.md) for asset,
voice and tool prerequisites. The command prepares the declared FlashHead Lite,
fixed portrait, FFmpeg and input caches, loads GPU/voice once and opens
[the loopback application](http://127.0.0.1:8765). Downloads require network
access and sufficient disk space; warm caches avoid repeated downloads.

Set `OPENAI_API_KEY` in the backend environment before launching, using your
existing credential manager. The browser never receives it. Missing credentials
disable Ask with an actionable message. `THEAD_MODEL` configures the model.
The default is `gpt-6-luna` with reasoning disabled. Official documentation checked
7 November 2026: [model](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses).
The app uses the fixed standard OpenAI HTTPS endpoint, stateless Responses
(`store: false`), no tools, 384 maximum output tokens and instructions requesting
two to four concise English sentences. There are no automatic retries; another
submission is a new request. Provider errors are redacted to actionable states.

Wait for idle, ask “What is a black hole?”, and read the incremental answer.
Expect local speech and moving video before a sufficiently long/delayed answer
has finished generating. The transcript labels generated text separately from
spoken playback. A short response can finish generating before playback starts.
Click Play if the browser blocks autoplay. Stop immediately detaches playback.

For a controlled stream without paid calls, use the same command with
`-FixtureProvider -Diagnostics`. This uses real local TTS/GPU/media but replaces
the external text provider. Choose “Delay provider stream”; media should become
available while later text is delayed. CPU protocol checks use `-TestBackend`
instead: visit the printed loopback URL; those diagnostic bytes cannot establish
playable media or GPU behaviour.

Questions are limited to 1200 characters. Answers are limited to 4096 characters
in addition to the provider token bound. Incremental phrases prefer sentence
boundaries, then whitespace, then a hard 180-character cut for unbroken strings;
arbitrary token boundaries and final partial text are preserved. No phrase-boundary
padding or avatar-state restart is introduced. Audio is capped at two minutes,
two queued input windows and the existing bounded media lookahead. Speech/media
backpressure also pauses text consumption. Provider network operations have a
15-second socket timeout, three-minute stream deadline and bounded event sizes.
Speech/handoff/player waits retain finite limits from the speech pipeline.
The process has a two-hour lifetime, with an outer supervisor allowing cleanup.

Conversation text and diagnostics containing generated words remain in backend
memory; they are not saved to `result.json` or readiness files. Temporary media
remains under ignored `.runtime/conversation` until cleanup. This is a single-user
loopback experiment. Existing speech and streaming demos remain independent.

Ask “How do we detect one?” after the black-hole answer. Both turns remain in the
transcript and earlier completed exchanges accompany the follow-up request.
New conversation assigns a fresh session identity and clears transcript/context
while retaining the loaded model and voice. A server restart loses session context;
a stale browser submission is rejected and the status refresh exposes the new session.

Context retains the newest coherent exchanges that fit 8192 conservatively bounded
input tokens, including current question, instructions and framing margins. The
bound uses UTF-8 byte length plus 64 tokens per message and 256 global overhead,
rather than assuming four characters per token. Oldest exchanges are dropped whole;
the transcript remains visible and states how many exchanges were omitted. A
100-turn in-memory session limit requires New conversation rather than growing
memory indefinitely. Provider-stored histories and conversation files are unused.
