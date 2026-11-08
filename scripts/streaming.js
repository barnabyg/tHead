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
const conversation = document.querySelector('#conversation');
const portrait = document.querySelector('#portrait');
portrait?.addEventListener('load', () => {
  portrait.classList.add('loaded');
  document.querySelector('#portrait-notice').textContent = '';
});
portrait?.addEventListener('error', () => {
  portrait.classList.remove('loaded');
  document.querySelector('#portrait-notice').textContent =
    'Portrait unavailable. Rerun the launch command to prepare assets.';
});
// Keep the still portrait underneath until a decoded video frame is presented.
video.addEventListener('ended', () => video.classList.remove('presenting'));

let sessionIdentity = null;
let pendingRequest = null;
let pendingController = null;
let selecting = false;
let stopping = 0;
let resetting = 0;
const settingsButton = document.querySelector('#settings');
const settingsPage = document.querySelector('#settings-page');
const chatPage = document.querySelector('.chat');
settingsButton?.addEventListener('click', () => {
  settingsPage.hidden = false;
  chatPage.hidden = true;
  settingsButton.setAttribute('aria-expanded', 'true');
  document.querySelector('#settings-title').focus();
});
document.querySelector('#settings-back')?.addEventListener('click', () => {
  settingsPage.hidden = true;
  chatPage.hidden = false;
  settingsButton.setAttribute('aria-expanded', 'false');
  settingsButton.focus();
});
const modelSelector = document.querySelector('#model');
const thinkingSelector = document.querySelector('#thinking-level');
let savingSettings = false;
let settingsRevision = 0;
let modelCatalog = '';
let thinkingCatalog = '';
function renderSettings(settings) {
  const catalog = JSON.stringify([settings.models, settings.model]);
  if (catalog !== modelCatalog) {
    modelSelector.replaceChildren(
      ...settings.models.map((model) => {
        const option = new Option(model.id + (model.available ? '' : ' — unavailable'), model.id);
        option.disabled = !model.available;
        return option;
      }),
    );
    if (!settings.models.some((model) => model.id === settings.model)) {
      modelSelector.add(new Option(`${settings.model} — unsupported`, settings.model));
    }
    modelCatalog = catalog;
  }
  modelSelector.value = settings.model;
  modelSelector.disabled = false;
  const levels = settings.models.find((model) => model.id === settings.model)?.levels || [];
  const levelCatalog = JSON.stringify(levels);
  if (levelCatalog !== thinkingCatalog) {
    thinkingSelector.replaceChildren(
      ...(levels.length ? levels : ['Unavailable']).map((level) => new Option(level, level)),
    );
    thinkingCatalog = levelCatalog;
  }
  if (levels.length) thinkingSelector.value = settings.thinkingLevel;
  thinkingSelector.disabled = !levels.length;
  document.querySelector('#model-availability').textContent = settings.models
    .filter((model) => !model.available)
    .map((model) => model.error)
    .join('. ');
}
async function saveSettings(change) {
  if (savingSettings) return;
  savingSettings = true;
  settingsRevision++;
  modelSelector.disabled = true;
  thinkingSelector.disabled = true;
  const feedback = document.querySelector('#settings-status');
  feedback.textContent = 'Saving…';
  try {
    const saved = await post('/settings', { session: sessionIdentity, ...change });
    renderSettings(saved.settings);
    feedback.textContent = `Saved. ${saved.settings.message || 'Applies to the next question.'}`;
  } catch (error) {
    feedback.textContent = String(error);
  } finally {
    savingSettings = false;
  }
}
modelSelector?.addEventListener('change', () => saveSettings({ model: modelSelector.value }));
thinkingSelector?.addEventListener('change', () =>
  saveSettings({ thinkingLevel: thinkingSelector.value }),
);
const pairSelector = document.querySelector('#pair');
const avatarEditor = document.querySelector('#avatar-editor');
const avatarForm = document.querySelector('#avatar-form');
const imagePicker = document.querySelector('#avatar-image');
const voicePicker = document.querySelector('#avatar-voice');
let savingAvatar = false;
let previewUrl = '';
document.querySelector('#create-avatar')?.addEventListener('click', () => {
  document.querySelector('#avatar-result').textContent = '';
  avatarEditor.showModal();
});
function closeAvatarEditor() {
  if (savingAvatar) return;
  avatarEditor.close();
  avatarForm.reset();
  document.querySelector('#avatar-save-status').textContent = '';
  URL.revokeObjectURL(previewUrl);
  previewUrl = '';
  document.querySelector('#avatar-preview').hidden = true;
}
document.querySelector('#cancel-avatar')?.addEventListener('click', closeAvatarEditor);
avatarEditor?.addEventListener('cancel', (event) => {
  event.preventDefault();
  closeAvatarEditor();
});
imagePicker?.addEventListener('change', () => {
  URL.revokeObjectURL(previewUrl);
  const file = imagePicker.files[0];
  previewUrl = file ? URL.createObjectURL(file) : '';
  const preview = document.querySelector('#avatar-preview');
  preview.hidden = !file;
  preview.src = previewUrl;
});
avatarForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (savingAvatar) return;
  const feedback = document.querySelector('#avatar-save-status');
  const name = document.querySelector('#avatar-name').value.trim();
  const file = imagePicker.files[0];
  if (!name || name.length > 80) {
    feedback.textContent = 'Enter an Avatar name of 1–80 characters';
    return;
  }
  if (!file || file.size > 5 * 1024 * 1024) {
    feedback.textContent = 'Choose a JPEG or PNG of at most 5 MiB';
    return;
  }
  if (!voicePicker.value) {
    feedback.textContent = 'Choose an available supported local English voice';
    return;
  }
  savingAvatar = true;
  for (const control of avatarForm.elements) control.disabled = true;
  feedback.textContent = 'Saving avatar…';
  try {
    const image = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(Error('Cannot read image; choose the file again'));
      reader.readAsDataURL(file);
    });
    const saved = await post(
      '/avatars',
      {
        session: sessionIdentity,
        name,
        voice: voicePicker.value,
        image,
      },
      AbortSignal.timeout(360000),
    );
    document.querySelector('#avatar-result').textContent =
      `Created ${saved.name}. Select it from Avatar when ready.`;
    savingAvatar = false;
    closeAvatarEditor();
  } catch (error) {
    feedback.textContent = String(error);
  } finally {
    savingAvatar = false;
    for (const control of avatarForm.elements) control.disabled = false;
  }
});
pairSelector?.addEventListener('change', async () => {
  if (selecting) return;
  selecting = true;
  epoch++;
  release();
  notice = '';
  start.disabled = true;
  pairSelector.disabled = true;
  document.querySelector('#pair-status').textContent = 'Switching avatar…';
  try {
    await post('/select', {
      session: sessionIdentity,
      pair: pairSelector.value,
      fault: document.querySelector('#pair-fault').value,
    });
  } catch (error) {
    notice = String(error);
  } finally {
    selecting = false;
  }
});
document.querySelector('#reset')?.addEventListener('click', async () => {
  resetting++;
  start.disabled = true;
  if (pairSelector) pairSelector.disabled = true;
  epoch++;
  pendingController?.abort();
  const before = performance.now();
  const beforeRms = outputRms();
  const run = active;
  release();
  observeSilence(run, before, beforeRms);
  document.querySelector('#turn-usage').replaceChildren();
  document.querySelector('#transcript').replaceChildren();
  delete document.querySelector('#transcript').dataset.rendered;
  try {
    const fresh = await post('/reset', { session: sessionIdentity });
    sessionIdentity = fresh.session;
    document.querySelector('#turn-usage').replaceChildren();
    document.querySelector('#transcript').replaceChildren();
    delete document.querySelector('#transcript').dataset.rendered;
    notice = 'New conversation';
  } catch (error) {
    statusText.textContent = String(error);
  } finally {
    resetting--;
    epoch++;
  }
});
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
  if (!run || run.ended || beforeRms === null) return;
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
async function post(path, data, signal = AbortSignal.timeout(30000)) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
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
    if (!active) return;
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
  video.classList.remove('presenting');
  video.removeAttribute('src');
  video.load();
  if (run?.url) URL.revokeObjectURL(run.url);
  play.hidden = true;
  return run;
}
function observeVideo(run) {
  video.requestVideoFrameCallback((_now, first) => {
    if (active !== run) return;
    video.classList.add('presenting');
    telemetry('first-frame-presented', { mediaTime: first.mediaTime });
    const next = (_time, frame) => {
      if (active !== run) return;
      if (frame.mediaTime > first.mediaTime)
        telemetry('moving-video', { mediaTime: frame.mediaTime });
      else video.requestVideoFrameCallback(next);
    };
    video.requestVideoFrameCallback(next);
  });
}
document.querySelector('#stop').onclick = async () => {
  stopping++;
  start.disabled = true;
  if (pairSelector) pairSelector.disabled = true;
  epoch++;
  pendingController?.abort();
  const before = performance.now();
  const beforeRms = outputRms();
  const run = active;
  telemetry('stop-action');
  release();
  observeSilence(run, before, beforeRms);
  statusText.textContent = 'Stopped; waiting for inference resources if needed';
  notice = statusText.textContent;
  const cancellations = [];
  if (run && !run.ended)
    cancellations.push(
      post('/stop', { run: run.id, clientPauseMilliseconds: performance.now() - before }).catch(
        (error) => {
          statusText.textContent = String(error);
        },
      ),
    );
  if (conversation && pendingRequest)
    cancellations.push(
      post('/cancel', { session: sessionIdentity, request: pendingRequest }).catch((error) => {
        statusText.textContent = String(error);
      }),
    );
  await Promise.all(cancellations);
  epoch++;
  stopping--;
};
function waitEvent(target, event, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => failure(), 120000);
    const cleanup = () => {
      clearTimeout(timer);
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
  const submittedAt = performance.now();
  const submittedUtc = new Date().toISOString();
  if (submitting) return;
  submitting = true;
  notice = '';
  const ticket = ++epoch;
  const requestId = crypto.randomUUID();
  const requestController = new AbortController();
  pendingController = requestController;
  if (conversation) pendingRequest = requestId;
  const previous = release();
  if (previous && !previous.ended) await post('/stop', { run: previous.id }).catch(() => {});
  start.disabled = true;
  if (pairSelector) pairSelector.disabled = true;
  play.hidden = true;
  try {
    await prepareAudioOutput().context.resume();
    if (ticket !== epoch) return;
    const clip = document.querySelector('#clip').value;
    const mode = document.querySelector('#mode').value;
    const run = conversation
      ? await post(
          '/ask',
          {
            question: document.querySelector('#text').value,
            session: sessionIdentity,
            request: requestId,
            fault: document.querySelector('#fault').value,
          },
          AbortSignal.any([requestController.signal, AbortSignal.timeout(30000)]),
        )
      : clip === 'text'
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
    telemetry('submit-action', {
      clientMilliseconds: submittedAt,
      utc: submittedUtc,
      request: requestId,
    });
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
    const deadline = performance.now() + 600000;
    while (active === run) {
      if (performance.now() > deadline) throw Error('Response exceeded ten minutes; ask again');
      if (
        video.buffered.length &&
        video.buffered.end(video.buffered.length - 1) - video.currentTime > 2.88
      ) {
        await sleep(100);
        continue;
      }
      const response = await fetch(`/segment?run=${run.id}&index=${index}`, {
        signal: AbortSignal.any([run.controller.signal, AbortSignal.timeout(30000)]),
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
          observeVideo(run);
          video.play().catch(() => {
            if (active === run) {
              telemetry('autoplay-blocked');
              play.hidden = false;
            }
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
        observeVideo(run);
        video.play().catch(() => {
          if (active === run) {
            telemetry('autoplay-blocked');
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
    if (conversation)
      await post('/cancel', { session: sessionIdentity, request: requestId }).catch(() => {});
    release();
  } finally {
    if (pendingRequest === requestId) pendingRequest = null;
    if (pendingController === requestController) pendingController = null;
    submitting = false;
  }
};
play.onclick = () => {
  telemetry('manual-play');
  video
    .play()
    .then(() => {
      play.hidden = true;
    })
    .catch((error) => {
      statusText.textContent = String(error);
    });
};
let polling = false;
setInterval(async () => {
  if (polling) return;
  polling = true;
  const ticket = epoch;
  const configTicket = settingsRevision;
  try {
    const status = await (await fetch('/status', { signal: AbortSignal.timeout(10000) })).json();
    if (ticket !== epoch) return;
    if (conversation) {
      if (status.settings && !savingSettings && configTicket === settingsRevision) {
        renderSettings(status.settings);
      }
      document.querySelector('#pair-diagnostics').hidden = !status.diagnostics;
      const pair = status.pairs.find((item) => item.id === status.activePair);
      for (const item of status.pairs) {
        if (![...pairSelector.options].some((option) => option.value === item.id)) {
          pairSelector.add(new Option(item.name, item.id));
        }
      }
      if (voicePicker.options.length === 1) {
        for (const voice of status.voices) {
          const option = new Option(
            voice.name + (voice.available ? '' : ' — unavailable'),
            voice.id,
          );
          option.disabled = !voice.available;
          voicePicker.add(option);
        }
      }
      document.querySelector('#avatar-storage-error').textContent = status.avatarStorageError;
      if (!selecting) pairSelector.value = status.selectedPair;
      pairSelector.disabled =
        selecting ||
        stopping ||
        resetting ||
        !status.pairSelectable ||
        submitting ||
        status.state !== 'idle' ||
        !!(active && !active.ended);
      document.querySelector('#pair-status').textContent =
        status.state === 'selecting' || status.state === 'loading'
          ? `Preparing ${status.pairs.find((item) => item.id === status.selectedPair)?.name}…`
          : status.error || `Active: ${pair?.name || 'none'}${status.ready ? ' — Ready' : ''}`;
      conversation.textContent = pair
        ? `Active avatar: ${pair.name}. Synthetic speech.`
        : 'Preparing avatar';
      if (sessionIdentity && status.session !== sessionIdentity) {
        epoch++;
        release();
        notice = 'Server session lost or reset; conversation cleared';
      }
      sessionIdentity = status.session;
      const displayPair = pair || status.pairs.find((item) => item.id === status.selectedPair);
      if (portrait && displayPair) {
        const source = `/portrait?pair=${encodeURIComponent(displayPair.id)}`;
        if (portrait.getAttribute('src') !== source) {
          portrait.classList.remove('loaded');
          portrait.src = source;
          portrait.alt = `${displayPair.name} portrait`;
        }
      }
      const transcript = document.querySelector('#transcript');
      const rendered = JSON.stringify([status.transcript, status.contextOmitted]);
      if (transcript.dataset.rendered !== rendered) {
        const history = transcript.closest('.history');
        const follow =
          !history || history.scrollHeight - history.scrollTop - history.clientHeight < 80;
        transcript.replaceChildren();
        const turnUsage = document.querySelector('#turn-usage');
        turnUsage.replaceChildren();
        for (const [index, turn] of status.transcript.entries()) {
          const entry = document.createElement('article');
          entry.className = 'exchange';
          for (const [role, text, kind] of [
            ['You', turn.question, 'question'],
            [
              status.avatars.find((item) => item.id === turn.pair)?.name || 'Avatar',
              turn.answer,
              'answer',
            ],
          ]) {
            if (!text) continue;
            const message = document.createElement('div');
            message.className = `message ${kind}`;
            const label = document.createElement('strong');
            label.textContent = `${role}: `;
            message.append(label, document.createTextNode(text));
            entry.append(message);
          }
          const note = document.createElement('p');
          note.className = 'turn-note';
          note.textContent = `${turn.state === 'stopped' ? 'Interrupted' : turn.state}${turn.truncated ? ' (output limit reached)' : ''} — Generated text may not all have been spoken.`;
          entry.append(note);
          const usageEntry = document.createElement('li');
          const heading = document.createElement('strong');
          heading.textContent = `Turn ${index + 1}: ${turn.question}`;
          const usage = document.createElement('p');
          const tokens = `Tokens: ${turn.usage?.input_tokens ?? 'unknown'} input / ${turn.usage?.output_tokens ?? 'unknown'} output${turn.usage?.reasoning_tokens !== undefined ? ` (${turn.usage.reasoning_tokens} reasoning, included in output)` : ''}`;
          const cost =
            turn.usage?.estimated_usd !== undefined
              ? `estimated USD ${turn.usage.estimated_usd.toFixed(6)}${turn.usage.estimated ? ' (conservative allowance; final usage unavailable)' : ''}`
              : 'estimated cost pending; reserved allowance is included in monthly totals';
          usage.textContent = `${turn.model || status.model}; Thinking: ${turn.thinkingLevel || 'unknown'} — ${turn.state === 'stopped' ? 'Interrupted' : turn.state} — ${tokens}; ${cost}.`;
          usageEntry.append(heading, usage);
          turnUsage.append(usageEntry);
          transcript.append(entry);
        }
        if (status.contextOmitted) {
          const note = document.createElement('p');
          note.className = 'turn-note';
          note.textContent = `${status.contextOmitted} earlier exchanges omitted from model context to fit the input allowance.`;
          transcript.append(note);
        }
        transcript.dataset.rendered = rendered;
        if (follow && history) history.scrollTop = history.scrollHeight;
      }
      document.querySelector('#usage').textContent = status.budget?.usable
        ? `${status.budget.month} (UTC): estimated USD ${status.budget.estimated_usd.toFixed(6)} spent; USD ${status.budget.reserved_usd.toFixed(6)} reserved; USD ${status.budget.remaining_usd.toFixed(6)} remaining of USD 40. Application estimates, not authoritative billing.`
        : status.budget?.error || '';
    }
    document.querySelector('#clip option[value="text"]').disabled = !status.speechEnabled;
    document.querySelector('#diagnostics').hidden = !status.diagnostics;
    if (!status.speechEnabled && document.querySelector('#clip').value === 'text')
      document.querySelector('#clip').value = 'six';
    start.disabled =
      !(status.ready && status.state === 'idle') ||
      submitting ||
      selecting ||
      stopping ||
      resetting ||
      !!(active && !active.ended) ||
      !!status.configurationError;
    if (!active)
      statusText.textContent =
        status.configurationError || status.error || notice || `Model: ${status.state}`;
    report.textContent = JSON.stringify(status, null, 2);
  } catch (error) {
    statusText.textContent = String(error);
  } finally {
    polling = false;
  }
}, 500);
