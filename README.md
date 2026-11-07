# tHead

Native Windows talking-head feasibility work. The current deliverable is the
[FlashHead Lite model-loading smoke test](docs/runtime/windows-smoke.md) for
[issue #2](https://github.com/barnabyg/tHead/issues/2).

Run from the repository root in PowerShell 7:

```powershell
pwsh -NoProfile -File ./scripts/smoke.ps1
```

Read the prerequisites and measured result in the runtime guide first. Readiness
means the real Lite, LTX VAE and audio encoder weights loaded on the RTX 3090.
Video generation, playback and streaming are subsequent work.

For development, install uv 0.11.7 and run the canonical verification command:

```powershell
uv run --locked python scripts/verify.py
```

It checks formatting, lint, strict types, static security analysis, command-boundary
tests, dependency locks and vulnerabilities, secrets, Python syntax and PowerShell
syntax. CI runs these checks on Windows. GPU validation uses the separate smoke
command and must be run on the target hardware. There is one small CPU test suite;
GPU runs are serial because they share one GPU and memory/timing measurements.
There is no distributable application package at this phase, so wheel building
and deployment verification are inapplicable.
