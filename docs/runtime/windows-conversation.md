# Windows conversational application

For named avatars and legacy pair aliases, see [the avatar guide](windows-pairs.md).
The default is **JFK**; **Grace** is also built in.
Open **Settings** to choose the current **Avatar** by name. Use **Back to conversation**
to return without losing your draft, transcript, context, playback or accounting.
**Stop** and **New conversation** remain available on both pages. Avatar changes
remain disabled until the current response ends; preparation errors appear beside
the selector and can be recovered by choosing a healthy avatar.
Use **Create avatar** beside the selector in Settings to add your own portrait and voice.
[Creation, storage and verification](windows-avatars.md) describes the workflow.

From `C:/docs/git/tHead`, in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1
```

Alternatively, double-click `run.bat` in the repository root or run `./run.bat`
from PowerShell 7. It starts the same application, locates the project folder
automatically and accepts the same options. For first use, run
`./run.bat -InitializeBudget`; subsequent launches use `./run.bat`.

Prerequisites: Windows 11, RTX 3090 with the pinned native CUDA driver/runtime,
Python 3.12, uv 0.11.7, Git, PowerShell 7, Microsoft Zira Desktop English voice
and the installed assets in `speech-lock.json`. Use an H.264/AAC MediaSource
browser (Chrome/Edge). See [the speech guide](windows-speech.md) for asset,
voice and tool prerequisites. The command prepares the declared FlashHead Lite,
configured portraits, FFmpeg and input caches, loads the GPU model once and opens
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

On **first use only**, add `-InitializeBudget` to the launch command to explicitly
create `.runtime/conversation-budget.sqlite3`. Normal launches open this existing
ledger. Missing/corrupt accounting disables paid requests; restore it rather than
initialising away prior spend. `-Budget <absolute-path>` selects an existing ledger
or explicitly creates it with `-InitializeBudget`. Keep that path across restarts
and model changes. The UI shows per-turn token usage/cost when available and UTC
monthly totals in USD. Missing final usage retains the conservative reserved cost,
including cancellation/failure. Reset never clears accounting. Only priced models
can dispatch. See [budget policy and controlled near-limit fixture](conversation-budget.md).

To show rejection without spending money, create the disposable full-limit ledger
in that guide and launch `conversation.ps1 -TestBackend -Budget <printed-path>`.
Ask a question: expect a budget error, unchanged totals and no provider dispatch.
For playable fixture media use `-FixtureProvider -Budget <printed-path>` instead.

Wait for idle, ask “What is a black hole?”, and read the incremental answer.
Expect local speech and moving video before a sufficiently long/delayed answer
has finished generating. The transcript labels generated text separately from
spoken playback. A short response can finish generating before playback starts.
Click Play if the browser blocks autoplay. Stop immediately detaches playback.

The portrait remains visible before the first answer, while a response prepares,
and after playback, Stop or New conversation. Moving video replaces the still
portrait only once a decoded frame is available. Switching avatar/voice updates
the portrait after successful preparation; a failed switch retains the active
avatar. The conversation scrolls independently so the avatar stays on screen,
including in the compact mobile layout. Session details combines monthly budget totals and a numbered usage list for the
current conversation. Each entry identifies the question and turn state with input/output
tokens and estimated USD cost when available. Interrupted/failed turns retain their
conservative allowance if final usage is missing. Timing diagnostics and diagnostic
fault controls (when enabled) remain in the same area. The transcript contains no
separate usage disclosures. New conversation clears this turn list and transcript,
while monthly budget accounting remains intact.

To manually check this UI from `C:/docs/git/tHead`, with the prerequisites and
backend key above, run `./run.bat` in PowerShell 7. Open
[the application](http://127.0.0.1:8765): expect the portrait before asking anything.
Ask a question, Stop during preparation or playback, then start a new conversation;
the avatar must remain visible throughout. Open Settings using the keyboard, select a different Avatar between turns, and
check the portrait changes after preparation. Return and ask a contextual follow-up;
expect the new portrait/voice with the earlier context. Type a draft, open Settings
and return: the draft and transcript must remain. Open Settings during playback:
expect uninterrupted playback, a disabled Avatar selector and usable Stop/New conversation.
Repeat at 320 px width; controls must fit and keyboard focus must move to the
Settings heading on entry and the Settings action on return. Resize to a narrow window and scroll a long transcript:
the portrait and question controls should remain available. Open Session details after two questions: expect separate numbered usage entries
alongside monthly totals and diagnostics. Stop another response, then start a new
conversation: expect the turn list to clear while budget totals remain accurate.
At desktop and narrow widths, expect no text over the portrait/video, no header
tagline and no conversation header bar or blank strip above the transcript. Real speech quality and lip sync still require
the existing GPU/manual listening checks.

For a controlled stream without paid calls, use the same command with
`-FixtureProvider -Diagnostics -InitializeBudget` on first fixture use. This uses
real local TTS/GPU/media but replaces
the external text provider. Choose “Delay provider stream”; media should become
available while later text is delayed. CPU protocol checks use `-TestBackend`
instead: visit the printed loopback URL; those diagnostic bytes cannot establish
playable media or GPU behaviour.

The provider fixture uses `.runtime/conversation-fixture-budget.sqlite3` by default,
separate from real accounting. Its usage/costs are simulated. The CPU fixture uses
its output directory's ledger. An explicit `-Budget` path overrides these defaults.

For the complete manual scenario, Ask the black-hole question, wait for the complete
spoken ending, then ask “How do we detect one?”. While an answer plays, click Stop,
then ask a replacement question. Click New conversation while a long answer is
working and submit a new topic after resources release: the old transcript/media
must stay absent. For repeatable no-cost Stop timing, select “Long fixture answer”.
Choose each of Fail provider, Disconnect provider, Fail local TTS and Fail media;
after the visible failure select None and Ask again. Expect recovery in the same
process. Check budget totals survive Stop, reset and relaunch. These fixture checks
do not assess answer quality or prove actual provider/network availability.

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
while retaining the loaded model and selected pair. A server restart loses session context;
a stale browser submission is rejected and the status refresh exposes the new session.

Context retains the newest coherent exchanges that fit 8192 conservatively bounded
input tokens, including current question, instructions and framing margins. The
bound uses UTF-8 byte length plus 64 tokens per message and 256 global overhead,
rather than assuming four characters per token. Oldest exchanges are dropped whole;
the transcript remains visible and states how many exchanges were omitted. A
100-turn in-memory session limit requires New conversation rather than growing
memory indefinitely. Provider-stored histories and conversation files are unused.

Stop and New conversation remain usable during provider connection, text streaming,
synthesis, inference, buffering and playback. Both synchronously detach the browser
player before network requests. A client epoch rejects delayed start responses;
unique session/response IDs reject old media, text and telemetry. New conversation
clears visible/backend context immediately while the old worker releases; Ask
remains disabled until resources are idle. Repeated Stop is harmless. A stopped
or failed answer retains its user question but excludes unfinished assistant text
from later context. Its transcript label does not claim everything was spoken.

Cancellation shuts down the provider socket where connected; connect/read timeouts
are 15 seconds and stream deadline 180 seconds. Non-preemptible local inference
finishes its current window and discards the result; synthesis cancellation and
handoff waits observe the cancellation flag. The speech producer has a 30-second
release join and server shutdown allows 120 seconds. Browser media waits are
bounded to 120 seconds and a response to ten minutes. Browser digital silence
telemetry is separate from resource release and cannot measure physical speaker
latency. No automatic retries replay partial speech. For recovery, select a provider,
TTS or media failure under `-FixtureProvider -Diagnostics`, Ask, observe a clear
failure, select None and Ask again without restarting. Repeat Stop during the
delayed-provider and delayed-TTS probes; then try New conversation while busy.

Named avatars are **JFK** and **Grace**. Use `-Avatar hopper-hazel` or
`THEAD_AVATAR`; legacy Pair flags and THEAD_PAIR remain supported. See the
[avatar guide](windows-pairs.md) for selection and manual verification.
