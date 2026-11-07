# Native Windows streaming experiment

Working directory: the repository root (`C:/docs/git/tHead` on the measured host).
Use PowerShell 7 and the prerequisites in [windows-demo.md](windows-demo.md):
Windows 11, RTX 3090, CUDA-capable driver, Python, Git, uv 0.11.7, VC++ runtime,
32 GB free disk, network access for pinned downloads and an audible output device.
Close other GPU workloads and any server already using port 8765.

One command prepares the hash-locked runtime, fixed portrait, English speech and
FFmpeg, then launches the persistent local server and your default browser:

```powershell
pwsh -NoProfile -File ./scripts/stream-demo.ps1
```

Open `http://127.0.0.1:8765` if the browser does not open. A current Chromium or
Firefox browser with H.264/AAC MediaSource support is required. Click Start when
the model is idle. If autoplay is blocked, click Play audio/video. Watch and
listen for synthetic JFK animation, continuous English speech and approximate
lip synchronisation. Expect playback before generation finishes, an orderly end,
and a second Start using the same loaded model. Reports appear below the player.
The existing offline `scripts/demo.ps1` workflow is preserved.

Stop pauses and detaches the browser media immediately, aborts pending fetches
and appends, and revokes its object URL. The server invalidates the run ID before
accepting more media or telemetry. Repeated Stop is harmless. Start becomes
available after the current non-preemptible inference call returns and its
FFmpeg process, sockets and bounded queues are released; weights stay loaded.
Failure is shown in the report and leaves the owner available for another run.
Test Stop before first playback, while buffering, and while speech is playing,
then Start and verify that no old speech returns. Also click Stop twice.

Real browser checks on 7 November stopped before first playback and during
active playback. The first run was stopped at 0.300 s and released generation at
0.486 s. The active run played at 1.794 s, received Stop at 1.918 s and produced no
further media. CPU HTTP tests inject a non-preemptible delayed result and failure,
verify HTTP 410 for stopped media and rejection of stale telemetry, and complete
a replacement run. `--test-backend` is explicitly a CPU protocol diagnostic that
produces no playable media; it cannot establish GPU or playback feasibility.
Client pause-call duration is recorded separately from server abandonment;
neither browser state nor telemetry measures the physical speaker's decay.
The selected player additionally routes audio through a local Web Audio analyser.
Stop samples this digital output every approximately 10 ms until two consecutive
256-sample windows have RMS below 0.00001, recording the first silent observation
and last non-silent observation separately from the pause call and GPU release.
An already silent source is labelled accordingly. Browser scheduling limits this
measurement; it does not measure DAC, speaker or room acoustics. No microphone,
recording permission or external audio service is involved.

## Progressively arriving speech

Select Arriving every 0.96 s or Arriving with a 3 s pause, then Start. The browser
acts as the prerecorded source: it sends ordered mono 16 kHz PCM16 messages to
`/input`, at the selected arrival rate. The inference owner uses only received
messages in this mode; it does not read the complete WAV. The source browser
does have the complete recording, as a controlled arrival simulator. Two queued
input chunks are allowed; HTTP 429 applies backpressure, and indices prevent
duplication or reordering. Requests for abandoned runs are rejected.

Generation starts after 15,360 samples (0.96 s) arrive, or after an explicitly
final shorter message. Empty arrival queues wait for speech without inserting
silence; no arrival for two minutes fails the run. End-of-input alone pads the
final model window; only the actual PCM and corresponding video frames reach
FFmpeg. The 0.35-second option exercises a single partial window; six seconds
exercises a final 0.24-second window. The 20-second input is seconds 31–51 of the
same pinned speech recording; the fixed portrait and model settings are unchanged.

This is a practical **chunked adaptation**. An eight-second rolling window is
re-encoded by wav2vec on each call; there is no preserved audio-encoder cache.
The first window is zero-filled history, not eight seconds of received speech.
Conditioning uses 33 frames and ±2 embedding frames, clamping the trailing indices
to received context. Model motion latents (last nine frames), advancing RNG,
portrait state and weights persist between chunks. The public portrait-preparation
call resets motion and seed between runs. Overlapping window re-encoding may
change boundary embeddings; motion persistence does not prove perceived continuity.

The initial 24-frame profile needed two generation calls / 1.92 seconds of arrived
speech for its first playable fragment. The selected eight-frame profile needs
one call / 0.96 seconds, while the progressive player waits for its initial
1.28-second playback buffer. In the initial delayed six-second run, generation started
at 0.977 s with exactly 15,360 received samples. Playback began at 2.597 s while
the third message was still unreceived. The deliberate three-second pause caused
one observed stall (3.630–6.865 s); playback resumed and ended at 6.064 s media
time. All 96,000 original samples were rendered, with no inserted underrun silence.
Arrival timestamps and cumulative sample counts are recorded per message;
`input-complete` records a PCM SHA-256 for comparing with the declared source.
Use the same Stop/restart scenario in both arrival modes, including during the
deliberate pause. A stall caused by absent input is expected and is reported.

The server is loopback-only and intended for one local viewer. It expires after
two hours; preparation has a separate five-hour limit. Do not expose it publicly.
Use `-NoBrowser` to launch without opening another browser. Logs and per-run
timestamped JSON evidence are under `.runtime/streaming/<run-id>/`; directories
are retained for review. Preparation caches are the declared `.runtime` trees
from the offline guide. No global Python packages or alternate model are used.

## Transport and measurement

One FFmpeg process per run receives generated RGB frames and their corresponding
PCM speech through two bounded loopback feeds. It emits one continuous fragmented
MP4: H.264 at 512 × 512 / 25 fps, no B frames, eight-frame keyframe interval, AAC
128 kbit/s. The browser appends ordered initialization/media fragments to a
single MediaSource timeline. This avoids restarting the AAC encoder at boundaries.
AAC priming adds approximately 64 ms to this profile's timeline; visual/audio
judgement is still required. The final video frame count rounds up to 40 ms;
audio retains the original sample count, with AAC padding in the container.

Two raw chunks per feed and nine unconsumed output fragments (2.88 seconds) bound
transport memory; browser delivery pauses above 2.88 seconds buffered. One append
can overshoot that browser threshold by one fragment. Consumed browser
media is removed after five seconds. Encoded fragments remain on disk as evidence
(input is capped at 30 seconds per run). A missing consumer fails after five
minutes. FFmpeg drain has a five-minute limit. These are hang limits, not targets.
Encoder connection and each blocked input-queue write also have five-minute
limits. Stop interrupts these waits and drain independently of encoder progress.

The initial 24-frame profile needed the next model chunk to close a fragment.
The selected eight-frame profile produces playable output from the first model
chunk. The player initially buffers at least 0.64 seconds for complete input and
1.28 seconds for timed arrivals, trading some startup time for continuity;
the short-input option uses 0.35 seconds. `frames-ready` marks
CPU-visible completed GPU output, `media-ready` marks mux availability, and browser
`appended`, `playing`, `first-frame-presented`, `waiting`, `occupancy` and `ended`
events establish the player boundary. Server event times are monotonic seconds
from run acceptance; browser events include their own monotonic time and UTC.
Server receipt includes loopback request latency and cannot measure speaker DAC
latency or certify audible output. Initial waiting before playing is startup,
not a sustained playback stall. Model load time is reported separately from runs.

Initial real RTX 3090 browser run on 7 November 2026: model load 3.534 s;
first generated chunk 1.322 s; first playable fragment 1.947 s; browser playing
1.988 s; render complete 5.029 s for six seconds of speech. The browser reached
`ended` at media time 6.064 s with no post-start waiting event. This establishes
playback before rendering finishes; it does not alone establish perceived lip sync.

## Repeatable assessment

After playing the desired scenarios, generate the machine-readable assessment:

```powershell
uv run --locked python scripts/assess_streaming.py
```

This reads `.runtime/streaming`, checks completed clips' codecs, start times,
durations and decoded video frame counts, decodes both streams with errors fatal,
compares recorded PCM hashes where available, and writes
`.runtime/streaming-assessment.json`. It reports startup, generation speed,
input/output queues, browser buffering, stalls and cancellation separately.
It does not substitute for the listening scenario above. See the
[Phase 2 assessment](phase-2-assessment.md) for measured results and remaining gaps.
Use `-FragmentFrames 24` on the launch command to reproduce the initial transport
granularity; the current player's initial-buffer policy remains in effect.
