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

The server is loopback-only and intended for one local viewer. It expires after
two hours; preparation has a separate five-hour limit. Do not expose it publicly.
Use `-NoBrowser` to launch without opening another browser. Logs and per-run
timestamped JSON evidence are under `.runtime/streaming/<run-id>/`; directories
are retained for review. Preparation caches are the declared `.runtime` trees
from the offline guide. No global Python packages or alternate model are used.

## Transport and measurement

One FFmpeg process per run receives generated RGB frames and their corresponding
PCM speech through two bounded loopback feeds. It emits one continuous fragmented
MP4: H.264 at 512 × 512 / 25 fps, no B frames, 24-frame keyframe interval, AAC
128 kbit/s. The browser appends ordered initialization/media fragments to a
single MediaSource timeline. This avoids restarting the AAC encoder at boundaries.
AAC priming adds approximately 64 ms to this profile's timeline; visual/audio
judgement is still required. The final video frame count rounds up to 40 ms;
audio retains the original sample count, with AAC padding in the container.

Two raw chunks per feed and three unconsumed output fragments bound transport
memory; browser delivery pauses above 2.88 seconds buffered. Consumed browser
media is removed after five seconds. Encoded fragments remain on disk as evidence
(input is capped at 30 seconds per run). A missing consumer fails after five
minutes. FFmpeg drain has a five-minute limit. These are hang limits, not targets.

The first complete fragment normally requires the next keyframe, so one extra
0.96-second generation call contributes to startup latency. `frames-ready` marks
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
