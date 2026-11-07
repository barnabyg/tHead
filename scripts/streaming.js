const video = document.querySelector('#video');
const start = document.querySelector('#start');
const play = document.querySelector('#play');
const statusText = document.querySelector('#status');
const report = document.querySelector('#report');
let active = null;
let epoch = 0;
let submitting = false;
let notice = '';
let audioOutput = null;
function prepareAudioOutput() {
  if (!audioOutput) {
    const context = new AudioContext();
    const source = context.createMediaElementSource(video);
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(context.destination);
    audioOutput = { context, analyser, samples: new Float32Array(256) };
  }
  return audioOutput;
}
function outputRms() {
  if (audioOutput?.context.state !== 'running') return null;
  audioOutput.analyser.getFloatTimeDomainData(audioOutput.samples);
  return Math.sqrt(
    audioOutput.samples.reduce((sum, value) => sum + value * value, 0) / audioOutput.samples.length,
  );
}
function observeSilence(run, actionTime, beforeRms) {
  if (!run || beforeRms === null) return;
  const threshold = 0.00001;
  let firstSilent = null,
    lastNonSilent = 0,
    consecutive = 0;
  const sample = () => {
    const elapsed = performance.now() - actionTime;
    if (active && active !== run) return;
    const rms = outputRms();
    if (rms !== null && rms < threshold) {
      if (firstSilent === null) firstSilent = elapsed;
      consecutive++;
    } else {
      lastNonSilent = elapsed;
      firstSilent = null;
      consecutive = 0;
    }
    if (consecutive >= 2 || elapsed > 5000) {
      post('/stop', {
        run: run.id,
        digitalSilence: {
          status:
            consecutive >= 2
              ? beforeRms < threshold
                ? 'already-silent'
                : 'observed'
              : 'not-observed',
          firstSilentMilliseconds: firstSilent,
          lastNonSilentMilliseconds: lastNonSilent,
          preStopRms: beforeRms,
          threshold,
          sampleRate: audioOutput.context.sampleRate,
          analyserSamples: audioOutput.samples.length,
          measurement: 'browser-audio-graph',
        },
      }).catch(() => {});
    } else setTimeout(sample, 10);
  };
  setTimeout(sample, 10);
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function post(path, data) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = Error(result.error || response.status);
    error.status = response.status;
    throw error;
  }
  return result;
}
function telemetry(event, extra = {}) {
  const run = active;
  if (!run || run.ended) return;
  const buffered = video.buffered.length
    ? video.buffered.end(video.buffered.length - 1) - video.currentTime
    : 0;
  post('/telemetry', {
    run: run.id,
    event,
    clientMilliseconds: performance.now(),
    utc: new Date().toISOString(),
    currentTime: video.currentTime,
    buffered,
    ...extra,
  }).catch(() => {});
}
for (const event of ['playing', 'waiting', 'stalled', 'ended', 'error']) {
  video.addEventListener(event, () => {
    telemetry(event, { mediaError: video.error?.message });
    if (event === 'playing') statusText.textContent = 'Playing';
    if (event === 'waiting' && active) statusText.textContent = 'Buffering';
    if (event === 'ended') {
      statusText.textContent = 'Playback ended';
      if (active) active.ended = true;
    }
    if (event === 'error') statusText.textContent = `Playback failed: ${video.error?.message}`;
    if (event === 'error' && active) {
      const run = release();
      epoch++;
      post('/stop', { run: run.id }).catch(() => {});
    }
  });
}
setInterval(() => {
  if (!video.ended) telemetry('occupancy');
}, 500);
setInterval(() => {
  const run = active;
  if (!run || run.audible || video.paused || video.ended) return;
  const rms = outputRms();
  if (rms !== null && rms >= 0.00001) {
    run.audible = true;
    telemetry('digital-audio-onset', {
      rms,
      measurement: 'browser-audio-graph',
      sampleIntervalMilliseconds: 25,
    });
  }
}, 25);
function release() {
  const run = active;
  active = null;
  run?.controller?.abort();
  video.pause();
  video.removeAttribute('src');
  video.load();
  if (run?.url) URL.revokeObjectURL(run.url);
  play.hidden = true;
  return run;
}
document.querySelector('#stop').onclick = () => {
  epoch++;
  const before = performance.now();
  const beforeRms = outputRms();
  const run = active;
  telemetry('stop-action');
  release();
  observeSilence(run, before, beforeRms);
  statusText.textContent = 'Stopped; waiting for inference resources if needed';
  notice = statusText.textContent;
  if (run)
    post('/stop', { run: run.id, clientPauseMilliseconds: performance.now() - before }).catch(
      (error) => {
        statusText.textContent = String(error);
      },
    );
};
function waitEvent(target, event, signal) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      target.removeEventListener(event, success);
      target.removeEventListener('error', failure);
      signal.removeEventListener('abort', failure);
    };
    const success = () => {
      cleanup();
      resolve();
    };
    const failure = () => {
      cleanup();
      reject(Error('Media operation aborted or failed'));
    };
    target.addEventListener(event, success, { once: true });
    target.addEventListener('error', failure, { once: true });
    signal.addEventListener('abort', failure, { once: true });
    if (signal.aborted) failure();
  });
}
async function append(buffer, data, signal) {
  const updated = waitEvent(buffer, 'updateend', signal);
  buffer.appendBuffer(data);
  await updated;
}
async function feed(run, clip, delayed) {
  const response = await fetch(`/audio?clip=${clip}`, { signal: run.controller.signal });
  if (!response.ok) throw Error('Declared input unavailable; rerun preparation');
  const pcm = new Uint8Array(await response.arrayBuffer());
  for (let offset = 0, index = 0; offset < pcm.length; offset += 30720, index++) {
    await sleep(Math.min(960, (pcm.length - offset) / 32));
    if (delayed && index === 2) await sleep(3000);
    if (active !== run) return;
    const chunk = pcm.slice(offset, offset + 30720);
    const data = {
      run: run.id,
      index,
      pcm: btoa(String.fromCharCode(...chunk)),
      final: offset + chunk.length === pcm.length,
    };
    while (active === run) {
      try {
        await post('/input', data);
        break;
      } catch (error) {
        if (error.status !== 429) throw error;
        await sleep(50);
      }
    }
  }
}
start.onclick = async () => {
  if (submitting) return;
  submitting = true;
  notice = '';
  const ticket = ++epoch;
  const previous = release();
  if (previous && !previous.ended) await post('/stop', { run: previous.id }).catch(() => {});
  start.disabled = true;
  play.hidden = true;
  try {
    await prepareAudioOutput().context.resume();
    if (ticket !== epoch) return;
    const clip = document.querySelector('#clip').value;
    const mode = document.querySelector('#mode').value;
    const run =
      clip === 'text'
        ? await post('/speak', {
            text: document.querySelector('#text').value,
            fault: document.querySelector('#fault').value,
          })
        : await post('/start', { clip, progressive: mode !== 'complete' });
    if (ticket !== epoch) {
      await post('/stop', { run: run.id });
      return;
    }
    active = run;
    statusText.textContent = clip === 'text' ? 'Preparing local speech and avatar' : 'Generating';
    run.controller = new AbortController();
    const media = new MediaSource();
    run.url = URL.createObjectURL(media);
    video.src = run.url;
    await waitEvent(media, 'sourceopen', run.controller.signal);
    const codec = 'video/mp4; codecs="avc1.42C01E, mp4a.40.2"';
    if (!MediaSource.isTypeSupported(codec))
      throw Error('This browser lacks H.264/AAC MediaSource support');
    const buffer = media.addSourceBuffer(codec);
    const minimumBuffer =
      clip === 'text' ? 1.28 : clip === 'short' ? 0.35 : mode === 'complete' ? 0.64 : 1.28;
    telemetry('client-settings', {
      userAgent: navigator.userAgent,
      mode,
      clip,
      initialBufferSeconds: minimumBuffer,
    });
    if (clip !== 'text' && mode !== 'complete')
      feed(run, clip, mode === 'delayed').catch((error) => {
        if (active !== run) return;
        statusText.textContent = String(error);
        telemetry('input-failure', { message: String(error) });
        epoch++;
        release();
        post('/stop', { run: run.id }).catch(() => {});
      });
    let index = 0,
      requested = false;
    while (active === run) {
      if (
        video.buffered.length &&
        video.buffered.end(video.buffered.length - 1) - video.currentTime > 2.88
      ) {
        await sleep(100);
        continue;
      }
      const response = await fetch(`/segment?run=${run.id}&index=${index}`, {
        signal: run.controller.signal,
      });
      if (active !== run) return;
      if (response.status === 202) {
        await sleep(50);
        continue;
      }
      if (response.status === 204) {
        media.endOfStream();
        telemetry('end-of-stream');
        if (!requested && video.buffered.length) {
          requested = true;
          telemetry('play-request', { finalPartial: true });
          video.requestVideoFrameCallback(() => {
            if (active === run) telemetry('first-frame-presented');
          });
          video.play().catch(() => {
            if (active === run) play.hidden = false;
          });
        }
        break;
      }
      if (!response.ok) {
        const status = await (await fetch('/status')).json();
        if (active !== run) return;
        throw Error(
          status.run?.id === run.id && status.run.error
            ? status.run.error
            : 'Generation failed or run expired; see report',
        );
      }
      const data = await response.arrayBuffer();
      if (active !== run) return;
      await append(buffer, data, run.controller.signal);
      if (active !== run) return;
      telemetry('appended', { index });
      if (!requested && video.buffered.length) statusText.textContent = 'Buffering';
      index++;
      if (!requested && video.buffered.length && video.buffered.end(0) >= minimumBuffer) {
        requested = true;
        telemetry('play-request');
        video.requestVideoFrameCallback(() => {
          if (active === run) telemetry('first-frame-presented');
        });
        video.play().catch(() => {
          if (active === run) {
            play.hidden = false;
            statusText.textContent = 'Click Play to allow browser audio';
          }
        });
      }
      if (video.currentTime > 5 && !buffer.updating) {
        const removed = waitEvent(buffer, 'updateend', run.controller.signal);
        buffer.remove(0, video.currentTime - 2);
        await removed;
      }
    }
  } catch (error) {
    if (ticket !== epoch) return;
    statusText.textContent = String(error);
    notice = String(error);
    telemetry('client-failure', { message: String(error) });
    video.pause();
    if (active) await post('/stop', { run: active.id }).catch(() => {});
    release();
  } finally {
    submitting = false;
  }
};
play.onclick = () => {
  video
    .play()
    .then(() => {
      play.hidden = true;
    })
    .catch((error) => {
      statusText.textContent = String(error);
    });
};
setInterval(async () => {
  try {
    const status = await (await fetch('/status')).json();
    document.querySelector('#clip option[value="text"]').disabled = !status.speechEnabled;
    document.querySelector('#diagnostics').hidden = !status.diagnostics;
    if (!status.speechEnabled && document.querySelector('#clip').value === 'text')
      document.querySelector('#clip').value = 'six';
    start.disabled =
      !(status.ready && status.state === 'idle') || submitting || !!(active && !active.ended);
    if (!active) statusText.textContent = status.error || notice || `Model: ${status.state}`;
    report.textContent = JSON.stringify(status, null, 2);
  } catch (error) {
    statusText.textContent = String(error);
  }
}, 500);
