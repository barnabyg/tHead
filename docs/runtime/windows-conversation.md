# Windows conversational application

For named avatars and legacy pair aliases, see [the avatar guide](windows-pairs.md).
The default is **JFK**; **Grace** is also built in.
Open the full-screen **Settings** page to choose **Current avatar** by name. Use **Back to conversation**
to return without losing your draft, transcript, context, playback or accounting.
**Ask** changes to **Stop** while a response is in progress. In Settings, **Stop** moves to the header. Avatar changes
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
(`store: false`), no tools, a default of 384 maximum output tokens and instructions requesting
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

Wait for **Ready**. Enter a question or select **What is a black hole?** to fill the empty composer. Edit the question and choose **Ask** to send it.
Expect local speech and moving video before a sufficiently long/delayed answer
has finished generating. The transcript labels generated text separately from
spoken playback. A short response can finish generating before playback starts.
Click Play if the browser blocks autoplay. Stop immediately detaches playback.

The portrait remains visible before the first answer, while a response prepares,
and after playback, Stop or New conversation. Moving video replaces the still
portrait only once a decoded frame is available. Switching avatar/voice updates
the portrait after successful preparation; a failed switch retains the active
avatar. The conversation scrolls independently so the avatar stays on screen,
including in the compact mobile layout. **Expand portrait** opens a larger view on narrow screens. **Reduce portrait** restores the compact view during playback. Session details combines monthly budget totals and a numbered usage list for the
current conversation. Each entry identifies the question and turn state with input/output
tokens and estimated USD cost when available. Interrupted/failed turns retain their
conservative allowance if final usage is missing. Timing diagnostics and diagnostic
fault controls (when enabled) remain in the same area. The transcript contains no
separate usage disclosures. New conversation clears this turn list and transcript,
while monthly budget accounting remains intact.

### Quick UI check

From `C:/docs/git/tHead` on Windows with Python and PowerShell 7 installed, launch the local CPU fixture:

```powershell
.\run.bat -TestBackend -Port 8765
```

Open [the conversation](http://127.0.0.1:8765). Select the example and edit it. The transcript should stay empty until you choose **Ask**. When tHead accepts the question, the input should clear and the question should appear in the transcript. To check cancellation, expand **Session details**, select **Delay provider stream**, and ask a follow-up. Open **Settings** and choose **Stop**. On return, the transcript should show the interrupted turn. Narrow the window to phone width, then expand and reduce the portrait while keeping the composer in view. Audio and lip-sync checks use the native launcher below.

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

Context retains the newest coherent exchanges that fit the configured input allowance
(8192 conservatively bounded tokens by default), including the current question,
instructions and framing margins. The
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

## Model selection in Settings

**Model** changes apply to subsequent questions. An active turn retains its captured
model, context and price reservation. The server saves the selected model, thinking
level, token limits and startup avatar in `%LOCALAPPDATA%\tHead\avatars.sqlite3`
(or the directory selected with `-UserData`). Clearing browser data has no effect
on these preferences. At startup, an explicit `--model` or `THEAD_MODEL` overrides the
saved model. A fresh installation defaults to `gpt-6-luna`. If a saved model is no
longer available, select an eligible model in Settings to resume.

Settings fetches the models visible to the backend API key at startup and hourly while the
server is running. The Model dropdown shows models with confirmed text input, text output,
Responses streaming and Standard text pricing. Open **Excluded models** to inspect the
remaining IDs and the reason each is unavailable. New eligible models appear automatically.
A failed inventory or pricing fetch blocks paid dispatch and retries after one minute.
Fixture launches use an offline model list.

From `C:/docs/git/tHead`, with the backend API key and native runtime prerequisites above,
launch the application in PowerShell 7. Add `-InitializeBudget` on first use.

```powershell
./run.bat
```

Open **Settings**. Check the Model dropdown and expand **Excluded models**. Select a
different eligible model and inspect **Thinking level**. Checking Settings is free.
To verify a paid turn, return to the conversation, ask a short question and check
the model and estimated cost in Session details.

## Thinking level

The app reads explicit reasoning levels from the model page or its entry in the official
model index. **Model default** delegates to the provider by omitting the reasoning
parameter. It is the only option when supported levels cannot be established.
Luna starts at `none` when its page confirms support, preserving the existing
low-latency setting. For other models the app uses the documented default when known.
The saved level applies to future turns and survives New conversation and app restarts.
Starting with a different model override uses that model's initial level.
Switching models retains a compatible level; moving from Luna's `none` to Sol
visibly selects `medium` with an explanation. Unknown/unavailable models show a
disabled level control. Validation never dispatches an unsupported combination.

The official [Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
establish these mappings (checked 8 November 2026). The configured output-token
cap includes reasoning and visible output. High effort may exhaust it without a
visible answer: lower Thinking level and submit again after the actionable error.
Reported reasoning tokens are shown as a subset of output, never added again to
cost. Interrupted or failed calls without final usage retain their reservation.

Using the same `./run.bat` command above, choose two supported thinking levels
and ask at each. Session details shows each turn's captured model and Thinking
value (also `run.thinkingLevel` in Timing diagnostics), rather than inferring the
setting from answer length or delay. Change level during a response and verify
only the next turn changes. Switch from Luna/none to Sol: expect medium and a
visible explanation. In fixture diagnostics, Reject provider settings must show
an actionable error; select None, adjust the level and ask a contextual follow-up
without restarting. Real provider access, timing and answer quality remain manual.

## Token limits

In Settings, open **Response settings → Advanced token limits** to edit three whole-number values and save them together with **Save token limits**:

| Setting | Default | Allowed range | Effect |
| --- | ---: | ---: | --- |
| Maximum output tokens | 384 | 16–32768 | Responses `max_output_tokens` hard cap, including reasoning; also used for the pre-request cost reservation. |
| Answer token target | 240 | 1–32768 | Prompt instruction requesting the answer finish within this many tokens; must not exceed maximum output tokens. |
| Input token allowance | 8192 | 512–131072 | Conservative UTF-8-based allowance for the current question, instructions and history; whole older exchanges are omitted to fit. |

Changes apply to future questions. A response in progress keeps its captured limits and
reservation. Limits survive page reloads, model switches, New conversation and app restarts. Invalid
values leave all settings unchanged. A question that cannot fit the input allowance is
rejected before reserving cost or calling the provider. The existing 4096-character answer,
two-minute speech and three-minute provider safeguards still apply independently.

Manual verification requires Python and PowerShell 7. From any directory, this single
command launches the no-cost CPU fixture without downloads, credentials or a GPU:

```powershell
pwsh -NoProfile -Command "Set-Location C:/docs/git/tHead; ./run.bat -TestBackend -Port 8765"
```

Open [the local app](http://127.0.0.1:8765), then Settings. On first use the limits are
384, 240 and 8192. Select a model and thinking level, then save limits of 1024, 800
and 512. Stop the server with Ctrl+C and run the same command again. Open Settings
in a private browser window and check all five values. Try a target of 1025:
expect an error and editable controls; correct it to 800 and save again. Ask a short
question and a follow-up: Timing diagnostics should show `run.tokenLimits` with the saved
values, `max_output_tokens: 1024` in the fixture provider-request event, and omitted older
context. CPU fixture media is deliberately unplayable; check real answer length and
speech using the normal launch command and an existing provider key/runtime.
