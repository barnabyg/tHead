# Browser media fixture

`browser.mp4` contains one second of synthetic moving colour bars and a 440 Hz
tone, generated locally with the declared FFmpeg. It contains no portrait, voice,
personal data or third-party recording. Chromium tests substitute this file at the
external media transport boundary; it proves player/control behaviour, not avatar
quality or audio/video synchronisation of the GPU pipeline.

Reproduce from the repository root in PowerShell 7, with prepared media tools:

```powershell
$lock = Get-Content ./demo-lock.json -Raw | ConvertFrom-Json
$ffmpeg = Join-Path ./.runtime/media ($lock.media.directory + '/bin/ffmpeg.exe')
& $ffmpeg -nostdin -v error -y -f lavfi -i 'testsrc2=size=128x128:rate=25:duration=1' -f lavfi -i 'sine=frequency=440:sample_rate=16000:duration=1' -c:v libx264 -profile:v baseline -pix_fmt yuv420p -c:a aac -movflags '+frag_keyframe+empty_moov+default_base_moof' ./tests/fixtures/browser.mp4
```

Running tests needs the tracked fixture and Playwright Chromium, not FFmpeg or a GPU.

`portrait.jpg` is a 96 × 96 solid green JPEG used to check the portrait HTTP
endpoint and browser image decoding without downloaded portraits. Reproduce with
the same `$ffmpeg` above:

```powershell
& $ffmpeg -nostdin -v error -y -f lavfi -i 'color=c=0x405547:s=96x96' -frames:v 1 -update 1 ./tests/fixtures/portrait.jpg
```
