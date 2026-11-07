# Native Windows English talking-head demonstration

## Run and check

Working directory: `C:/docs/git/tHead`, or the root of your checkout.
Use PowerShell 7. Install the [smoke-test prerequisites](windows-smoke.md):
Windows 11 x64, Git, Python, uv 0.11.7, the Microsoft Visual C++ runtime,
and an RTX 3090 with a CUDA 12.8-capable driver. Close GPU-heavy applications.
Allow at least 32 GB free disk space and network access to the runtime sources,
`www.gyan.dev` and `upload.wikimedia.org`. Enable an audible Windows output device.
No system FFmpeg, CUDA compiler, WSL, LLM or TTS service is required.

One command prepares the runtime, downloads hash-checked inputs and FFmpeg,
generates the clip and plays it with FFplay:

```powershell
pwsh -NoProfile -File ./scripts/demo.ps1
```

Manual scenario: watch the six-second player window and listen to the English
recording. Expect a synthetic animation of JFK's portrait with visible mouth/head
movement, audible speech, and mouth movement approximately following speech.
Check the onset and end of speech against the mouth, with no conspicuous lag or
increasing drift. This is generated demonstration footage, not an original film
of the speech. FFplay closes at the end. Exit 0 means generation, decode checks
and the player process succeeded; it cannot establish that your speakers worked
or that you judged the animation synchronised.

For generation without a player, add `-NoPlay`. The MP4 is
`.runtime/demo/clip.mp4`. Replay it by opening it in a Windows media player.
Close a previous player before regenerating: Windows may prevent replacing an
open video or executable. Do not infer success from an old clip left on disk.

When upgrading an issue #2 checkout, the loader may reject the previous local
source patch. Preserve any needed work, then move `.runtime/FlashHead` aside and
rerun; the launcher reacquires the pinned source and applies the current patch.
It never silently discards unknown source edits.

## Inputs and terms

`demo-lock.json` records exact download URLs, SHA-256 digests and the audio cut.
Acquisition refuses changed content. No personal or undeclared local input is used.

- Portrait: [John F. Kennedy, White House color photo portrait](https://commons.wikimedia.org/wiki/File:John_F._Kennedy,_White_House_color_photo_portrait.jpg),
  photograph by Cecil Stoughton, White House, 11 July 1963. The source identifies
  it as a US federal government work in the public domain. Upstream resizes and
  centre-crops it to 512 × 512; no face-detection dependency is added.
- Audio: [JFK inaugural address](https://commons.wikimedia.org/wiki/File:JFK_inaugural_address.ogg),
  20 January 1961, credited to JFK and the John F. Kennedy Presidential Library
  and Museum; the source marks it public domain as a US government work.
  FFmpeg cuts seconds **31–37** into mono 16 kHz PCM16 WAV. The recorded voice is
  neither synthesized nor cloned. Preserve provenance and do not present the
  synthetic clip as original historical footage or an endorsement.

Source pages document public-domain status in the US; review the source terms
for your intended jurisdiction/use. Assets and generated video are downloaded or
created locally, rather than committed to this repository. Model terms remain
those in the [runtime notices](windows-smoke.md#notices), including Open-RAIL-M
for the LTX VAE.

## Native media tools and output profile

The launcher downloads Gyan's **FFmpeg 9.0.2 essentials Windows x64 build**
from its versioned URL, checks its published SHA-256, and extracts it below
`.runtime/media`. The archive includes FFmpeg, FFprobe, FFplay and its license;
it does not alter `PATH` or install software system-wide. The build source and
license information are available on the [publisher's builds page](https://www.gyan.dev/ffmpeg/builds/).
Retain those notices if redistributing binaries; this repository distributes none.

The profile keeps upstream's **512 × 512**, **25 fps**, **four denoising steps**,
seed 42, bfloat16 CUDA, native PyTorch attention, eager model/VAE, and colour
correction strength 1.0. Arbitrary smaller model resolutions are not assumed.
The driver follows upstream's audio-window algorithm: eight seconds of history,
33-frame model windows, nine motion-context frames discarded, 24 new frames per
chunk. Seven chunks produce 168 frames; silent padding completes the final chunk.
The mux trims the output to the original six seconds / 150 video frames.

Output is H.264, CRF 18, yuv420p, no B-frames, AAC 128 kbit/s, MP4 faststart.
FFprobe checks codecs, dimensions, frame rate, durations within 80 ms and stream
start times within 40 ms. FFmpeg decodes both streams with errors fatal before
the candidate is promoted to `clip.mp4`. These checks detect timing/container
errors but cannot substitute for listening and visual lip-sync inspection.

The driver calls the real upstream pipeline directly and writes raw RGB frames
to FFmpeg, avoiding upstream's unpinned imageio/librosa stack and unchecked mux
exit status. `patches/windows-eager-single-gpu.patch` also records two adaptations
needed during inference with the pinned newer libraries:

- Add Transformers 5's output-capture decorator to the custom wav2vec forward
  method, restoring all 13 hidden states, and use `config.return_dict`.
- Replace deprecated CUDA autocast with `torch.amp.autocast("cuda", enabled=False)`
  at the projection that explicitly operates in float32, preserving its intent.

## Diagnostics and measured evidence

Failures exit nonzero and record the stage/error. `.runtime/demo.log` and
`.runtime/demo-result.json` cover preparation and playback;
`.runtime/clip-result.json` covers generation, CUDA memory and media inspection.
Raw RGB frames and partial media remain after inference/mux/decode failure;
raw frames are removed after successful validation. The current report is
reset before work, so a previous successful report cannot masquerade as success.
The generated status and player exit are deliberately separate from human
playback confirmation.

Preparation allows five hours for its bounded install/download/load subprocesses;
generation has a one-hour hard limit, mux five minutes, decode/playback three
minutes. Each media acquisition has a ten-minute transfer deadline plus at most
one pending 180-second network read. These are hang limits, not speed targets.
The Windows runner terminates timed-out subprocess trees.

See [the RTX 3090 clip report](rtx3090-clip.json) for the actual measured run.
The first inference attempt failed with missing wav2vec hidden states; a minimal
audio-encoder reproduction failed before the decorator change and returned 13
states afterwards. The complete GPU run then generated and decoded six seconds.
An initial launcher rerun exposed a locked FFplay executable; verified extraction
now leaves identical files untouched. An open previous clip also correctly
failed promotion rather than reporting success; close players before rerunning.
The user confirmed on 7 November 2026: "Speech and animation are in sync."
This completes the audible playback and approximate lip-sync check for this host.
Computer-use screenshot inspection was unavailable because app approval timed out;
the listening/animation assessment is the user's direct playback observation.
