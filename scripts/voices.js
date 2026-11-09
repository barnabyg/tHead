/* Local cloning UI. The library owns validation, decoding, preview and persistence. */
const voicesDialog = document.querySelector('#voices-dialog');
const cloneForm = document.querySelector('#clone-form');
const cloneName = document.querySelector('#clone-name');
const cloneRecording = document.querySelector('#clone-recording');
const clonePermission = document.querySelector('#clone-permission');
const cloneFeedback = document.querySelector('#clone-status');
const cloneAudio = document.querySelector('#clone-audio');
const clonePreview = document.querySelector('#clone-preview');
const cloneSave = document.querySelector('#clone-save');
let voiceOperation = '';
let voiceSession = '';
let voiceRevision = 0;
let voiceBusy = false;
let voiceSaving = false;
let voiceController = null;
let voicePreviewed = false;
let voiceAudioKey = '';
let repairVoice = '';
let savedVoiceCatalogue = '';
let voiceReadiness = null;
let voiceReadinessVersion = 0;
let preparationStarting = false;
let preparationStartVersion = 0;
let preparationAttempt = 0;
let preparationAttempted = false;
let preparationActionError = '';
let preparationCancelling = false;
// Polls sampled before or during a preparation command must not replace its result.
window.voicePreparationRevision = 0;

function updateVoicePreparation(readiness) {
  if (JSON.stringify(readiness) !== JSON.stringify(voiceReadiness)) {
    voiceReadinessVersion++;
    preparationActionError = '';
  }
  voiceReadiness = readiness;
  if (
    voiceReadinessVersion !== preparationStartVersion &&
    ['preparing', 'ready', 'failed', 'cancelled'].includes(readiness.state)
  ) {
    preparationStarting = false;
  }
  if (readiness.state === 'preparing') preparationAttempted = true;
  else preparationCancelling = false;
  renderVoicePreparation();
}

function renderVoicePreparation() {
  const readiness = voiceReadiness;
  if (!readiness) return;
  const prepare = document.querySelector('#prepare-voices');
  const cancel = document.querySelector('#cancel-voice-preparation');
  const clone = document.querySelector('#clone-voice');
  const status = document.querySelector('#voice-readiness');
  const focused = document.activeElement;
  const starting = preparationStarting && voiceReadinessVersion === preparationStartVersion;
  const preparing = readiness.state === 'preparing';
  const failed = readiness.state === 'failed';
  const cancelled = readiness.state === 'cancelled';
  const ready = readiness.available && !starting && !preparing && !failed && !cancelled;
  let message;
  if (starting) {
    message = 'Starting local voice preparation…';
  } else if (preparing) {
    message = preparationCancelling
      ? 'Cancelling local voice preparation…'
      : 'Preparing local voices. Downloads and checks may take several minutes.';
  } else if (failed) {
    message = `Local voice preparation failed. ${readiness.error || 'Retry preparation.'}`;
  } else if (cancelled) {
    message = 'Preparation cancelled. Retry to resume verified downloads.';
  } else if (ready) {
    message =
      preparationAttempted && readiness.state === 'ready'
        ? 'Setup complete — ready to clone voices.'
        : 'Ready to clone voices.';
  } else {
    message =
      readiness.error || 'Local voice engine is not available. Prepare local voices to continue.';
  }
  if (preparationActionError) message = `${message} ${preparationActionError}`;
  prepare.textContent = starting
    ? 'Starting local voices…'
    : preparing
      ? 'Preparing local voices…'
      : failed || cancelled || preparationActionError
        ? 'Retry voice preparation'
        : 'Prepare local voices';
  prepare.hidden = !!ready;
  prepare.disabled = preparationStarting || preparing || !readiness.eligible;
  cancel.hidden = !preparing;
  cancel.disabled = preparationCancelling;
  clone.disabled = !ready;
  if (status.textContent !== message) status.textContent = message;
  // Keep focus on a useful control when preparation disables or hides its trigger.
  if (
    [prepare, cancel, status].includes(focused) &&
    (focused === status || focused.disabled || focused.hidden)
  ) {
    if (!cancel.hidden && !cancel.disabled) cancel.focus();
    else if (ready) clone.focus();
    else if (!prepare.disabled) prepare.focus();
    else status.focus();
  }
}

function stopVoiceAudio() {
  cloneAudio.pause();
  cloneAudio.removeAttribute('src');
  cloneAudio.load();
  cloneAudio.hidden = true;
  voiceAudioKey = '';
}

async function cancelVoiceOperation() {
  if (voiceSaving) return false;
  voiceRevision++;
  voiceController?.abort();
  stopVoiceAudio();
  const operation = voiceOperation;
  voiceOperation = '';
  voicePreviewed = false;
  voiceBusy = false;
  cloneSave.disabled = true;
  clonePreview.disabled = false;
  if (operation) {
    post('/voices/cancel', { session: voiceSession, operation }).catch(() => {});
  }
  return true;
}

async function closeVoices() {
  if (voicesDialog.hidden) return;
  if (!(await cancelVoiceOperation())) return;
  cloneForm.hidden = true;
  voicesDialog.hidden = true;
  document.querySelector('#settings-page').hidden = false;
  document.querySelector('#open-voices').focus();
}

document.querySelector('#open-voices').addEventListener('click', () => {
  document.querySelector('#settings-page').hidden = true;
  voicesDialog.hidden = false;
  document.querySelector('#voices-title').focus();
});
document.querySelector('#voices-back').addEventListener('click', closeVoices);
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || voicesDialog.hidden) return;
  event.preventDefault();
  closeVoices();
});
document.querySelector('#clone-voice').addEventListener('click', async () => {
  if (!(await cancelVoiceOperation())) return;
  cloneForm.reset();
  repairVoice = '';
  document.querySelector('#clone-title').textContent = 'Clone voice';
  cloneFeedback.textContent = '';
  cloneForm.hidden = false;
  cloneName.focus();
});
document.querySelector('#clone-cancel').addEventListener('click', async () => {
  await cancelVoiceOperation();
  cloneForm.hidden = true;
  document.querySelector('#clone-voice').focus();
});
cloneRecording.addEventListener('change', async () => {
  await cancelVoiceOperation();
  cloneFeedback.textContent = 'Recording changed. Preview it before saving.';
});
document.querySelector('#clone-stop').addEventListener('click', async () => {
  if (voiceBusy) {
    if (!(await cancelVoiceOperation())) return;
    cloneFeedback.textContent = 'Preview stopped. Preview again to continue.';
  } else {
    cloneAudio.pause();
    cloneAudio.currentTime = 0;
  }
});
document.querySelector('#reset').addEventListener('click', cancelVoiceOperation);
document.querySelector('#settings').addEventListener('click', async () => {
  if (voicesDialog.hidden || !(await cancelVoiceOperation())) return;
  cloneForm.hidden = true;
  voicesDialog.hidden = true;
});
document.querySelector('#stop').addEventListener('click', async () => {
  if (voiceOperation) {
    if (!(await cancelVoiceOperation())) return;
    cloneFeedback.textContent = 'Preview stopped. Preview again to continue.';
  }
});
document.querySelector('#prepare-voices').addEventListener('click', async () => {
  if (preparationStarting || !voiceReadiness?.eligible || voiceReadiness.state === 'preparing')
    return;
  preparationStarting = true;
  preparationAttempted = true;
  preparationActionError = '';
  preparationStartVersion = voiceReadinessVersion;
  const attempt = ++preparationAttempt;
  window.voicePreparationRevision++;
  const version = voiceReadinessVersion;
  document.querySelector('#voice-result').textContent = '';
  renderVoicePreparation();
  try {
    const readiness = await post('/voices/prepare', { session: sessionIdentity });
    // A status poll may already have observed a newer outcome than this reply.
    if (attempt === preparationAttempt && version === voiceReadinessVersion)
      updateVoicePreparation(readiness);
  } catch (error) {
    if (attempt === preparationAttempt && version === voiceReadinessVersion)
      preparationActionError = String(error);
  } finally {
    window.voicePreparationRevision++;
    if (attempt === preparationAttempt) preparationStarting = false;
    renderVoicePreparation();
  }
});
document.querySelector('#cancel-voice-preparation').addEventListener('click', async () => {
  if (preparationCancelling || voiceReadiness?.state !== 'preparing') return;
  preparationCancelling = true;
  preparationActionError = '';
  window.voicePreparationRevision++;
  const version = voiceReadinessVersion;
  renderVoicePreparation();
  try {
    const readiness = await post('/voices/prepare/cancel', { session: sessionIdentity });
    if (version === voiceReadinessVersion) updateVoicePreparation(readiness);
  } catch (error) {
    if (version === voiceReadinessVersion) {
      preparationCancelling = false;
      preparationActionError = String(error);
    }
  } finally {
    window.voicePreparationRevision++;
    renderVoicePreparation();
  }
});

clonePreview.addEventListener('click', async () => {
  if (voiceBusy) return;
  const file = cloneRecording.files[0];
  const name = cloneName.value.trim();
  if (
    !name ||
    name.length > 80 ||
    !file ||
    file.size > 20 * 1024 * 1024 ||
    !clonePermission.checked
  ) {
    cloneFeedback.textContent =
      'Enter a voice name, choose a WAV/MP3/M4A of at most 20 MiB, and confirm permission.';
    return;
  }
  if (voicePreviewed && cloneAudio.src) {
    cloneAudio.currentTime = 0;
    await cloneAudio.play().catch(() => {});
    return;
  }
  await cancelVoiceOperation();
  const revision = voiceRevision;
  voiceOperation = crypto.randomUUID();
  voiceSession = sessionIdentity;
  voiceController = new AbortController();
  const operation = voiceOperation;
  voiceBusy = true;
  clonePreview.disabled = true;
  cloneSave.disabled = true;
  cloneFeedback.textContent = 'Preparing recording locally…';
  try {
    const raw = new Uint8Array(await file.arrayBuffer());
    if (revision !== voiceRevision) return;
    // Chunk conversion avoids a large argument-list allocation for a bounded upload.
    let binary = '';
    for (let i = 0; i < raw.length; i += 32768) {
      binary += String.fromCharCode(...raw.subarray(i, i + 32768));
    }
    await post(
      '/voices/import',
      {
        session: voiceSession,
        operation,
        name,
        filename: file.name,
        permission: clonePermission.checked,
        audio: btoa(binary),
      },
      AbortSignal.any([voiceController.signal, AbortSignal.timeout(360000)]),
    );
    if (revision !== voiceRevision) return;
    cloneFeedback.textContent = 'Preparing synthetic preview locally…';
    await post('/voices/preview', { session: voiceSession, operation });
  } catch (error) {
    if (revision !== voiceRevision) return;
    await cancelVoiceOperation();
    cloneFeedback.textContent = String(error);
  }
});

cloneForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (voiceBusy || !voicePreviewed) return;
  voiceSaving = true;
  voiceBusy = true;
  cloneRecording.disabled = true;
  document.querySelector('#clone-cancel').disabled = true;
  document.querySelector('#voices-back').disabled = true;
  cloneSave.disabled = true;
  clonePreview.disabled = true;
  const revision = voiceRevision;
  try {
    const record = await post(repairVoice ? '/voices/repair' : '/voices/save', {
      session: voiceSession,
      operation: voiceOperation,
      name: cloneName.value,
      id: repairVoice,
    });
    if (revision !== voiceRevision) return;
    document.querySelector('#voice-result').textContent =
      `${repairVoice ? 'Repaired' : 'Saved'} ${record.name}. Use Create/Edit avatar in Settings to choose it.`;
    voiceOperation = '';
    stopVoiceAudio();
    cloneForm.hidden = true;
  } catch (error) {
    if (revision === voiceRevision) cloneFeedback.textContent = String(error);
  } finally {
    voiceSaving = false;
    cloneRecording.disabled = false;
    document.querySelector('#clone-cancel').disabled = false;
    document.querySelector('#voices-back').disabled = false;
    if (revision === voiceRevision) {
      voiceBusy = false;
      cloneSave.disabled = !voicePreviewed;
      clonePreview.disabled = false;
    }
  }
});

window.renderVoiceLibrary = (status, preparationRevision) => {
  if (!status.voiceLibrary) return;
  const library = status.voiceLibrary;
  const readiness = library.readiness;
  if (preparationRevision === window.voicePreparationRevision) updateVoicePreparation(readiness);
  if (voiceOperation && voiceSession !== status.session && !voiceSaving) cancelVoiceOperation();
  if (voiceOperation && library.operation === voiceOperation && !voiceSaving) {
    if (library.state === 'failed' || library.state === 'cancelled') {
      cloneFeedback.textContent = library.error || 'Preview cancelled. Try again.';
      voiceBusy = false;
      clonePreview.disabled = false;
    } else if (library.previewReady) {
      voiceBusy = false;
      voicePreviewed = true;
      clonePreview.disabled = false;
      cloneSave.disabled = false;
      cloneFeedback.textContent = 'Synthetic preview ready. Listen, then save or correct the name.';
      if (voiceAudioKey !== voiceOperation) {
        voiceAudioKey = voiceOperation;
        cloneAudio.src = `/voice-preview?session=${encodeURIComponent(voiceSession)}&operation=${encodeURIComponent(voiceOperation)}`;
        cloneAudio.hidden = false;
        cloneAudio.play().catch(() => {});
      }
    }
  }
  const records = status.voices.filter((voice) => voice.editable);
  const catalogue = JSON.stringify(records);
  if (catalogue === savedVoiceCatalogue) return;
  savedVoiceCatalogue = catalogue;
  const list = document.querySelector('#saved-voices');
  list.replaceChildren();
  for (const record of records) {
    const item = document.createElement('li');
    const name = document.createElement('input');
    name.value = record.name;
    name.maxLength = 80;
    name.setAttribute('aria-label', `Rename ${record.name}`);
    const note = document.createElement('p');
    note.textContent = record.error || 'Ready';
    item.append(name, note);
    for (const action of ['Rename', 'Delete', 'Repair']) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${action} ${record.name}`;
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          if (action === 'Repair') {
            if (!(await cancelVoiceOperation())) return;
            repairVoice = record.id;
            cloneName.value = record.name;
            cloneRecording.value = '';
            clonePermission.checked = false;
            cloneForm.hidden = false;
            cloneFeedback.textContent =
              'Choose a replacement recording. Saving preserves this voice and its avatars.';
            document.querySelector('#clone-title').textContent = `Repair ${record.name}`;
            cloneRecording.focus();
          } else {
            await post(`/voices/${action.toLowerCase()}`, {
              session: sessionIdentity,
              id: record.id,
              name: action === 'Rename' ? name.value : record.name,
            });
            document.querySelector('#voice-result').textContent = `${action} completed.`;
          }
        } catch (error) {
          document.querySelector('#voice-result').textContent = String(error);
        } finally {
          button.disabled = false;
        }
      });
      item.append(button);
    }
    list.append(item);
  }
};
