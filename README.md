# tHead

Native Windows talking-head feasibility work. Generate and play a six-second
English clip using the [talking-head demonstration](docs/runtime/windows-demo.md)
for [issue #3](https://github.com/barnabyg/tHead/issues/3):

```powershell
pwsh -NoProfile -File ./scripts/demo.ps1
```

The launcher prepares the pinned GPU runtime, public-domain inputs and native
FFmpeg tools, generates a real 512 × 512 FlashHead Lite clip and opens FFplay.
Check the guide's prerequisites first. Listening and lip-sync confirmation are
manual checks; successful generation alone does not certify playback quality.

The separate
[FlashHead Lite model-loading smoke test](docs/runtime/windows-smoke.md) for
[issue #2](https://github.com/barnabyg/tHead/issues/2) remains available.

Run from the repository root in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/smoke.ps1
```

Read the prerequisites and measured result in the runtime guide first. Readiness
means the real Lite, LTX VAE and audio encoder weights loaded on the RTX 3090.
The demo adds video generation and playback. See the
[Windows reproducibility baseline](docs/runtime/windows-baseline.md) for clean-checkout
preparation, repeated RTX 3090 measurements and the Phase 1 conclusion.

Streaming output, Stop/recovery and controlled progressive audio input are available
in the [browser streaming experiment](docs/runtime/windows-streaming.md):

```powershell
pwsh -NoProfile -File ./scripts/stream-demo.ps1
```

The [Phase 2 assessment](docs/runtime/phase-2-assessment.md) records real RTX 3090
measurements and the feasibility decision. This is prerecorded speech, with no
TTS, LLM or integrated conversation pipeline.

The [local text-to-avatar demonstration](docs/runtime/windows-speech.md) adds
CPU synthesis with the installed Windows Zira English voice:

```powershell
pwsh -NoProfile -File ./scripts/speech-demo.ps1
```

The [Phase 3 assessment](docs/runtime/phase-3-assessment.md) records integrated
RTX 3090/browser measurements, Stop/recovery evidence and the feasibility decision.

The [conversational application](docs/runtime/windows-conversation.md) adds streamed
OpenAI answers, bounded session context, Stop/reset, recovery and a durable USD 40
monthly application guard. From the repository root, after setting the backend key:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1
```

First use adds `-InitializeBudget`; normal restarts preserve the existing ledger.
See the guide for prerequisites, no-cost fixtures and manual scenarios, and the
[Phase 4 assessment](docs/runtime/phase-4-assessment.md) for measured results and limits.

For development, install uv 0.11.7 and Node.js 24.14.1, then prepare the pinned
browser-check tooling once:

```powershell
npm.cmd ci --ignore-scripts
npx.cmd playwright install chromium
```

Run the canonical verification command:

```powershell
uv run --locked python scripts/verify.py
```

It checks Python and browser formatting/lint, strict Python types, browser JavaScript
syntax, static security analysis, command-boundary
tests, dependency locks and vulnerabilities, secrets, Python syntax and PowerShell
syntax. CI runs these checks on Windows. GPU validation uses the separate smoke
command and must be run on the target hardware. Independent CPU test modules run
concurrently with isolated temporary paths and loopback ports; unittest has no
internal parallel worker mode. GPU runs are serial because they share one GPU
and memory/timing measurements.
There is no distributable application package at this phase, so wheel building
and deployment verification are inapplicable.
