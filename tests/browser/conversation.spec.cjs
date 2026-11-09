const { test, expect } = require('@playwright/test');
const { spawn } = require('node:child_process');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

async function preparationStatus(page, readiness) {
  const backend = { readiness, starts: 0 };
  await page.route('**/status', async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    status.voiceLibrary.readiness = backend.readiness;
    await route.fulfill({ json: status });
  });
  await page.route('**/voices/prepare', async (route) => {
    backend.starts++;
    backend.readiness = {
      state: 'preparing',
      available: false,
      eligible: true,
      error: '',
      message: 'Preparing local voices. Downloads and checks may take several minutes.',
    };
    const response = backend.readiness;
    if (backend.startGate) await backend.startGate;
    await route.fulfill({ json: response });
  });
  await page.reload();
  await expect(page.locator('#voices-title')).toBeHidden();
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  return backend;
}

test('voice preparation distinguishes unprepared and installed engines without starting downloads', async ({
  page,
}) => {
  const backend = await preparationStatus(page, {
    state: 'idle',
    available: false,
    eligible: true,
    error: 'Local voice engine is not prepared. Choose Prepare local voices.',
    message: 'Verified RTX 3090 configuration.',
  });
  await expect(page.locator('#voice-readiness')).toContainText('not prepared');
  await expect(
    page.getByRole('button', { name: 'Prepare local voices', exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Clone voice', exact: true })).toBeDisabled();
  await expect(page.locator('#cancel-voice-preparation')).toBeHidden();
  backend.readiness = {
    state: 'idle',
    available: true,
    eligible: true,
    error: '',
    message: 'Verified RTX 3090 configuration.',
  };
  await expect(page.locator('#voice-readiness')).toContainText('Ready to clone voices');
  await expect(page.locator('#voice-readiness')).not.toContainText('Setup complete');
  await expect(page.locator('#prepare-voices')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Clone voice', exact: true })).toBeEnabled();
  await page.reload();
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await expect(page.locator('#voice-readiness')).toContainText('Ready to clone voices');
  expect(backend.starts).toBe(0);
});

test('voice preparation follows backend completion and ignores a late start acknowledgement', async ({
  page,
}) => {
  const backend = await preparationStatus(page, {
    state: 'idle',
    available: false,
    eligible: true,
    error: 'Local voice engine is not prepared.',
    message: 'Verified RTX 3090 configuration.',
  });
  let release;
  backend.startGate = new Promise((resolve) => {
    release = resolve;
  });
  const prepare = page.locator('#prepare-voices');
  const cancel = page.getByRole('button', { name: 'Cancel preparation', exact: true });
  const clone = page.getByRole('button', { name: 'Clone voice', exact: true });
  await expect(prepare).toBeEnabled();
  await prepare.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
  await expect(prepare).toBeDisabled();
  await expect(cancel).toBeVisible();
  await expect(cancel).toBeFocused();
  await expect(clone).toBeDisabled();
  await expect(page.locator('#voices-dialog')).not.toContainText('Preparation requested.');
  expect(backend.starts).toBe(1);
  backend.readiness = {
    state: 'ready',
    available: false,
    eligible: true,
    error: 'Engine validation is incomplete.',
  };
  await expect(page.locator('#voice-readiness')).toContainText('Engine validation is incomplete');
  await expect(clone).toBeDisabled();
  backend.readiness = { state: 'ready', available: true, eligible: true, error: '' };
  await expect(page.locator('#voice-readiness')).toContainText(
    'Setup complete — ready to clone voices',
  );
  await expect(page.locator('#voice-readiness')).toHaveAttribute('role', 'status');
  await expect(page.locator('#voice-readiness')).toHaveAttribute('aria-live', 'polite');
  await expect(clone).toBeEnabled();
  const acknowledgement = page.waitForResponse('**/voices/prepare');
  release();
  await (await acknowledgement).finished();
  await expect(prepare).toBeHidden();
  await expect(cancel).toBeHidden();
  await expect(page.locator('#voice-result')).toBeEmpty();
  await expect(clone).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Voice name', { exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await expect(page.locator('#voice-readiness')).toContainText('ready to clone voices');
  await page.reload();
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await expect(page.locator('#voice-readiness')).toHaveText('Ready to clone voices.');
  await expect(clone).toBeEnabled();
  expect(backend.starts).toBe(1);
});

for (const outcome of ['failed', 'cancelled']) {
  test(`voice preparation retries after ${outcome} without stale outcomes`, async ({ page }) => {
    const backend = await preparationStatus(page, {
      state: 'idle',
      available: false,
      eligible: true,
      error: 'Local voice engine is not prepared.',
    });
    const prepare = page.locator('#prepare-voices');
    const clone = page.getByRole('button', { name: 'Clone voice', exact: true });
    await expect(page.locator('#voice-readiness')).toContainText('not prepared');
    await prepare.click();
    await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
    backend.readiness = {
      state: outcome,
      available: true,
      eligible: true,
      error: outcome === 'failed' ? 'Download checksum mismatch; see app-preparation.log.' : '',
    };
    await expect(page.locator('#voice-readiness')).toContainText(
      outcome === 'failed' ? 'Download checksum mismatch' : 'Preparation cancelled',
    );
    await expect(page.locator('#voice-readiness')).not.toContainText('ready to clone');
    await expect(clone).toBeDisabled();
    await expect(
      page.getByRole('button', { name: 'Retry voice preparation', exact: true }),
    ).toBeEnabled();
    await expect(page.locator('#cancel-voice-preparation')).toBeHidden();
    await expect(page.locator('#voice-result')).toBeEmpty();
    await prepare.click();
    await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
    await expect(page.locator('#voices-dialog')).not.toContainText(
      /checksum mismatch|Preparation cancelled|Preparation requested\./,
    );
    backend.readiness = { state: 'ready', available: true, eligible: true, error: '' };
    await expect(page.locator('#voice-readiness')).toContainText(
      'Setup complete — ready to clone voices',
    );
    await expect(clone).toBeEnabled();
    await expect(prepare).toBeHidden();
    expect(backend.starts).toBe(2);
  });
}

test('voice preparation cancellation waits for the backend outcome and can retry', async ({
  page,
}) => {
  const backend = await preparationStatus(page, {
    state: 'preparing',
    available: false,
    eligible: true,
    error: '',
  });
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let cancels = 0;
  await page.route('**/voices/prepare/cancel', async (route) => {
    cancels++;
    await gate;
    await route.fulfill({
      json: { state: 'preparing', available: false, eligible: true, error: '' },
    });
  });
  const cancel = page.getByRole('button', { name: 'Cancel preparation', exact: true });
  await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
  await cancel.click();
  await expect(cancel).toBeVisible();
  await expect(cancel).toBeDisabled();
  await expect(page.locator('#voice-readiness')).toContainText(
    'Cancelling local voice preparation',
  );
  await expect(page.locator('#clone-voice')).toBeDisabled();
  backend.readiness = { state: 'cancelled', available: false, eligible: true, error: '' };
  await expect(page.locator('#voice-readiness')).toContainText('Preparation cancelled');
  await expect(
    page.getByRole('button', { name: 'Retry voice preparation', exact: true }),
  ).toBeFocused();
  const acknowledgement = page.waitForResponse('**/voices/prepare/cancel');
  release();
  await (await acknowledgement).finished();
  await expect(page.locator('#voice-readiness')).toContainText('Preparation cancelled');
  await expect(cancel).toBeHidden();
  await page.keyboard.press('Enter');
  await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
  await expect(cancel).toBeEnabled();
  await expect(cancel).toBeFocused();
  await expect(page.locator('#voice-result')).toBeEmpty();
  expect(cancels).toBe(1);
  expect(backend.starts).toBe(1);
});

test('voice preparation rejects duplicate pending starts and clears request errors on retry', async ({
  page,
}) => {
  const backend = await preparationStatus(page, {
    state: 'idle',
    available: false,
    eligible: true,
    error: 'Local voice engine is not prepared.',
  });
  let release;
  let accepted;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const acceptance = new Promise((resolve) => {
    accepted = resolve;
  });
  let starts = 0;
  await page.route('**/voices/prepare', async (route) => {
    starts++;
    accepted();
    await gate;
    await route.fulfill({
      status: 409,
      json: { error: 'Choose Zira/Hazel and wait before preparing local voices' },
    });
  });
  const prepare = page.locator('#prepare-voices');
  await expect(page.locator('#voice-readiness')).toContainText('not prepared');
  await prepare.click();
  await acceptance;
  await expect(prepare).toBeDisabled();
  await expect(page.locator('#voice-readiness')).toContainText('Starting local voice preparation');
  await page.keyboard.press('Enter');
  expect(starts).toBe(1);
  release();
  await expect(page.locator('#voice-readiness')).toContainText('Choose Zira/Hazel and wait');
  await expect(
    page.getByRole('button', { name: 'Retry voice preparation', exact: true }),
  ).toBeEnabled();
  await expect(page.locator('#clone-voice')).toBeDisabled();
  await expect(page.locator('#voice-result')).toBeEmpty();
  await page.route('**/voices/prepare', async (route) => {
    backend.readiness = { state: 'preparing', available: false, eligible: true, error: '' };
    await route.fulfill({ json: backend.readiness });
  });
  await prepare.click();
  await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
  await expect(page.locator('#voices-dialog')).not.toContainText('Choose Zira/Hazel and wait');
  await page.route('**/voices/prepare/cancel', async (route) => {
    await route.fulfill({
      status: 503,
      json: { error: 'Cancellation could not be requested. Try Cancel preparation again.' },
    });
  });
  const cancel = page.getByRole('button', { name: 'Cancel preparation', exact: true });
  await cancel.click();
  await expect(page.locator('#voice-readiness')).toContainText(
    'Cancellation could not be requested',
  );
  await expect(cancel).toBeEnabled();
  await expect(page.locator('#voice-result')).toBeEmpty();
  backend.readiness = { state: 'ready', available: true, eligible: true, error: '' };
  await expect(page.locator('#voice-readiness')).toContainText(
    'Setup complete — ready to clone voices',
  );
  await expect(page.locator('#voices-dialog')).not.toContainText(
    'Cancellation could not be requested',
  );
});

for (const action of ['start', 'cancel']) {
  test(`voice preparation ignores a status poll sampled before ${action}`, async ({ page }) => {
    const backend = await preparationStatus(page, {
      state: action === 'start' ? 'idle' : 'preparing',
      available: false,
      eligible: true,
      error: action === 'start' ? 'Local voice engine is not prepared.' : '',
    });
    await expect(page.locator('#voice-readiness')).toContainText(
      action === 'start' ? 'not prepared' : 'Preparing local voices',
    );
    let sampled;
    let release;
    const snapshot = new Promise((resolve) => {
      sampled = resolve;
    });
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    await page.route(
      '**/status',
      async (route) => {
        const response = await route.fetch();
        const status = await response.json();
        status.voiceLibrary.readiness = backend.readiness;
        sampled();
        await gate;
        await route.fulfill({ json: status });
      },
      { times: 1 },
    );
    await snapshot;
    // Keep subsequent polls from concealing a regression caused by this stale reply.
    await page.route('**/status', (route) => route.abort());
    await page.route('**/voices/prepare/cancel', async (route) => {
      backend.readiness = { state: 'cancelled', available: false, eligible: true, error: '' };
      await route.fulfill({ json: backend.readiness });
    });
    await page
      .locator(action === 'start' ? '#prepare-voices' : '#cancel-voice-preparation')
      .click();
    const expected = action === 'start' ? 'Preparing local voices' : 'Preparation cancelled';
    await expect(page.locator('#voice-readiness')).toContainText(expected);
    const staleResponse = page.waitForResponse('**/status');
    release();
    await (await staleResponse).finished();
    await expect(page.locator('#voice-readiness')).toContainText(expected);
    await expect(page.locator('#clone-voice')).toBeDisabled();
    if (action === 'start') {
      await expect(page.locator('#prepare-voices')).toBeDisabled();
      await expect(page.locator('#cancel-voice-preparation')).toBeVisible();
    } else {
      await expect(
        page.getByRole('button', { name: 'Retry voice preparation', exact: true }),
      ).toBeEnabled();
      await expect(page.locator('#cancel-voice-preparation')).toBeHidden();
    }
  });
}

for (const outcome of ['failed', 'cancelled']) {
  test(`voice preparation can retry ${outcome} while the previous start reply is delayed`, async ({
    page,
  }) => {
    const backend = await preparationStatus(page, {
      state: 'idle',
      available: false,
      eligible: true,
      error: 'Local voice engine is not prepared.',
    });
    let releaseOld;
    backend.startGate = new Promise((resolve) => {
      releaseOld = resolve;
    });
    await expect(page.locator('#voice-readiness')).toContainText('not prepared');
    await page.locator('#prepare-voices').click();
    await expect(page.locator('#voice-readiness')).toContainText('Preparing local voices');
    backend.readiness = { state: outcome, available: false, eligible: true, error: '' };
    await expect(page.locator('#voice-readiness')).toContainText(
      outcome === 'failed' ? 'Local voice preparation failed' : 'Preparation cancelled',
    );
    const retry = page.getByRole('button', { name: 'Retry voice preparation', exact: true });
    // Retry must follow the polled outcome, well before the 30 s POST timeout.
    await expect(retry).toBeEnabled({ timeout: 10_000 });
    let releaseNew;
    let accepted;
    const gate = new Promise((resolve) => {
      releaseNew = resolve;
    });
    const acceptance = new Promise((resolve) => {
      accepted = resolve;
    });
    await page.route('**/voices/prepare', async (route) => {
      accepted();
      await gate;
      backend.readiness = { state: 'ready', available: true, eligible: true, error: '' };
      await route.fulfill({ json: backend.readiness });
    });
    await retry.click();
    await acceptance;
    await expect(page.locator('#voice-readiness')).toContainText(
      'Starting local voice preparation',
    );
    const oldReply = page.waitForResponse('**/voices/prepare');
    releaseOld();
    await (await oldReply).finished();
    await expect(page.locator('#voice-readiness')).toContainText(
      'Starting local voice preparation',
    );
    await expect(page.locator('#prepare-voices')).toBeDisabled();
    releaseNew();
    await expect(page.locator('#voice-readiness')).toContainText(
      'Setup complete — ready to clone voices',
    );
    await expect(page.locator('#clone-voice')).toBeEnabled();
    await expect(page.locator('#voice-result')).toBeEmpty();
  });
}

for (const [state, error] of [
  ['idle', 'Local cloned voices require the verified RTX 3090 CUDA configuration.'],
  ['ready', 'Local GPU runtime unavailable. Prepare the normal app and retry.'],
]) {
  test(`voice preparation keeps ${state} device/runtime blockers separate from readiness`, async ({
    page,
    request,
  }, info) => {
    const before = await (await request.get(`${info.url}/status`)).json();
    const backend = await preparationStatus(page, {
      state,
      available: false,
      eligible: false,
      error,
    });
    await expect(page.locator('#voice-readiness')).toHaveText(error);
    await expect(page.locator('#prepare-voices')).toBeVisible();
    await expect(page.locator('#prepare-voices')).toBeDisabled();
    await expect(page.locator('#clone-voice')).toBeDisabled();
    await expect(page.locator('#cancel-voice-preparation')).toBeHidden();
    await expect(page.locator('#voice-result')).toBeEmpty();
    await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
    await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
    for (const voice of ['zira', 'hazel']) {
      await expect(page.locator(`#avatar-voice option[value="${voice}"]`)).toBeEnabled();
    }
    const after = await (await request.get(`${info.url}/status`)).json();
    expect(after.voices).toEqual(before.voices);
    expect(after.avatars).toEqual(before.avatars);
    expect(backend.starts).toBe(0);
  });
}

test('edit saved avatar retains identity and unchanged portrait across restart', async ({
  page,
  request,
}, info) => {
  const initial = await (await request.get(`${info.url}/status`)).json();
  const image = fs.readFileSync('tests/fixtures/portrait.jpg');
  const created = await (
    await request.post(`${info.url}/avatars`, {
      data: {
        session: initial.session,
        name: 'Editable',
        voice: 'zira',
        image: image.toString('base64'),
      },
    })
  ).json();
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(created.id);
  await expect(page.locator('#pair-status')).toContainText('Active: Editable');
  await page.getByRole('button', { name: 'Edit avatar', exact: true }).click();
  await expect(page.getByLabel('Avatar name', { exact: true })).toHaveValue('Editable');
  await expect(page.locator('#avatar-preview')).toBeVisible();
  await page.getByLabel('Voice', { exact: true }).selectOption('hazel');
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-result')).toContainText('Updated Editable');
  await expect(page.locator('#pair-status')).toContainText('Active: Editable');
  let status = await (await request.get(`${info.url}/status`)).json();
  expect(status.avatars).toHaveLength(3);
  expect(status.avatars.find((a) => a.id === created.id).voice).toBe('hazel');
  expect(await (await request.get(`${info.url}/portrait?avatar=${created.id}`)).body()).toEqual(
    image,
  );
  await stopFixture(info);
  await startFixture(info);
  await page.goto(info.url);
  status = await (await request.get(`${info.url}/status`)).json();
  expect(status.avatars.find((a) => a.id === created.id)).toMatchObject({
    name: 'Editable',
    voice: 'hazel',
  });
});

async function openSettings(page) {
  if (await page.locator('#settings-page').isHidden()) {
    await page.getByRole('button', { name: 'Settings', exact: true }).click();
  }
}

async function settledStatus(request, url) {
  let status;
  // Playback can end before reservation settlement and the final transcript save.
  await expect
    .poll(async () => {
      status = await (await request.get(`${url}/status`)).json();
      return status.state === 'idle' && status.budget.reserved_usd === 0;
    })
    .toBe(true);
  return status;
}

test('clone preview saves one private reusable voice without changing avatar, context or budget', async ({
  page,
  request,
}, info) => {
  const before = await (await request.get(`${info.url}/status`)).json();
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await page.getByRole('button', { name: 'Clone voice', exact: true }).click();
  await page.getByLabel('Voice name', { exact: true }).fill('Local reader');
  const sourceRecording = path.join(info.output, 'source.wav');
  fs.copyFileSync('docs/runtime/chatterbox/reference-1089-10s.wav', sourceRecording);
  await page.getByLabel('Recording', { exact: true }).setInputFiles(sourceRecording);
  await page.getByLabel('I own this recording or have permission to use it').check();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.locator('#clone-status')).toContainText('Synthetic preview ready');
  await page.screenshot({ path: info.outputPath('clone-screen.png') });
  await page.getByRole('button', { name: 'Stop preview', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save voice', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Save voice', exact: true }).click();
  await expect(page.locator('#voice-result')).toContainText('Saved Local reader');
  const saved = await (await request.get(`${info.url}/status`)).json();
  fs.unlinkSync(sourceRecording);
  const voice = saved.voices.find((v) => v.name === 'Local reader');
  expect(voice.id).toMatch(/^voice-/);
  expect(saved.activeAvatar).toBe(before.activeAvatar);
  expect(saved.transcript).toEqual(before.transcript);
  expect(saved.budget.estimated_usd).toBe(before.budget.estimated_usd);
  await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
  for (const name of ['Reader one', 'Reader two']) {
    await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
    await page.getByLabel('Avatar name', { exact: true }).fill(name);
    await page
      .getByLabel('Portrait image', { exact: true })
      .setInputFiles('tests/fixtures/portrait.jpg');
    await page.getByLabel('Voice', { exact: true }).selectOption(voice.id);
    await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
    await expect(page.locator('#avatar-result')).toContainText(`Created ${name}`);
  }
  const assigned = await (await request.get(`${info.url}/status`)).json();
  expect(assigned.avatars.filter((a) => a.voice === voice.id)).toHaveLength(2);
  const rejected = await request.post(`${info.url}/voices/delete`, {
    data: { session: assigned.session, id: voice.id, name: voice.name },
  });
  expect(rejected.status()).toBe(409);
  expect((await rejected.json()).error).toContain('Reader one');
  await stopFixture(info);
  await startFixture(info);
  await page.goto(info.url);
  await expect
    .poll(async () => {
      const status = await (await request.get(`${info.url}/status`)).json();
      return status.voices.filter((v) => v.id === voice.id && v.available).length;
    })
    .toBe(1);
});

test('changing a recording and leaving Voices invalidates preview and cannot save stale audio', async ({
  page,
  request,
}, info) => {
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await page.getByRole('button', { name: 'Clone voice', exact: true }).click();
  await page.getByLabel('Voice name', { exact: true }).fill('Unsaved reader');
  await page
    .getByLabel('Recording', { exact: true })
    .setInputFiles('docs/runtime/chatterbox/reference-1089-10s.wav');
  await page.getByLabel('I own this recording or have permission to use it').check();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.locator('#clone-status')).toContainText('Synthetic preview ready');
  const before = await (await request.get(`${info.url}/status`)).json();
  const oldPreview = await page.locator('#clone-audio').getAttribute('src');
  await page.getByLabel('Recording', { exact: true }).setInputFiles({
    name: 'invalid.wav',
    mimeType: 'audio/wav',
    buffer: Buffer.from('not audio'),
  });
  await expect(page.getByRole('button', { name: 'Save voice', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Voice name', { exact: true })).toHaveValue('Unsaved reader');
  await expect.poll(async () => (await request.get(info.url + oldPreview)).status()).toBe(410);
  const staleSave = await request.post(`${info.url}/voices/save`, {
    data: {
      session: before.session,
      operation: before.voiceLibrary.operation,
      name: 'Wrong voice',
    },
  });
  expect(staleSave.status()).toBe(409);
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.locator('#clone-status')).toContainText('corrupt or unsupported');
  await expect(page.getByLabel('Voice name', { exact: true })).toHaveValue('Unsaved reader');
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
  expect(
    (await (await request.get(`${info.url}/status`)).json()).voices.filter((v) => v.editable),
  ).toHaveLength(0);
});

test('an atomic save result remains visible when reset happens before its reply arrives', async ({
  page,
  request,
}, info) => {
  await openSettings(page);
  await page.getByRole('button', { name: 'Voices', exact: true }).click();
  await page.getByRole('button', { name: 'Clone voice', exact: true }).click();
  await page.getByLabel('Voice name', { exact: true }).fill('Save result');
  await page
    .getByLabel('Recording', { exact: true })
    .setInputFiles('docs/runtime/chatterbox/reference-1089-10s.wav');
  await page.getByLabel('I own this recording or have permission to use it').check();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.locator('#clone-status')).toContainText('Synthetic preview ready');
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let committed;
  const commit = new Promise((resolve) => {
    committed = resolve;
  });
  await page.route('**/voices/save', async (route) => {
    const response = await route.fetch();
    committed();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Save voice', exact: true }).click();
  await commit;
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Back to Settings', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  release();
  await expect(page.locator('#voice-result')).toContainText('Saved Save result');
  const status = await (await request.get(`${info.url}/status`)).json();
  expect(status.voices.filter((v) => v.name === 'Save result')).toHaveLength(1);
});

test('cancel editing and deletion; confirmed selected deletion falls back permanently without losing context', async ({
  page,
  request,
}, info) => {
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const initial = await (await request.get(`${info.url}/status`)).json();
  const created = await (
    await request.post(`${info.url}/avatars`, {
      data: {
        session: initial.session,
        name: 'Delete me',
        voice: 'hazel',
        image: fs.readFileSync('tests/fixtures/portrait.jpg').toString('base64'),
      },
    })
  ).json();
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(created.id);
  await expect(page.locator('#pair-status')).toContainText('Active: Delete me');
  await page.getByRole('button', { name: 'Edit avatar', exact: true }).click();
  await page.getByLabel('Avatar name', { exact: true }).fill('Discarded');
  await page.getByLabel('Voice', { exact: true }).selectOption('zira');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  let status = await (await request.get(`${info.url}/status`)).json();
  expect(status.avatars.find((a) => a.id === created.id)).toMatchObject({
    name: 'Delete me',
    voice: 'hazel',
  });
  await page.getByRole('button', { name: 'Delete avatar', exact: true }).click();
  await expect(page.locator('#delete-confirmation')).toContainText('Delete me');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await (await request.get(`${info.url}/status`)).json()).avatars).toHaveLength(3);
  await page.getByRole('button', { name: 'Delete avatar', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.locator('#avatar-result')).toContainText(
    'Deleted Delete me. Switched to default JFK',
  );
  await expect(page.locator('#pair-status')).toContainText('Active: JFK');
  expect(fs.existsSync(path.join(info.output, 'imported-portrait.png'))).toBe(false);
  await expect(page.getByLabel('Avatar', { exact: true }).locator('option')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Delete avatar', exact: true })).toBeHidden();
  status = await (await request.get(`${info.url}/status`)).json();
  expect(status.transcript).toEqual(initial.transcript);
  expect(status.session).toBe(initial.session);
  expect(status.budget.estimated_usd).toBe(initial.budget.estimated_usd);
  await stopFixture(info);
  await startFixture(info);
  await page.goto(info.url);
  expect((await (await request.get(`${info.url}/status`)).json()).avatars).toHaveLength(2);
  expect(fs.readdirSync(path.join(info.output, 'user-data'))).toEqual(['avatars.sqlite3']);
});

async function backToConversation(page) {
  if (await page.locator('#settings-page').isVisible()) {
    await page.getByRole('button', { name: 'Back to conversation' }).click();
  }
}

test('editing validates replacement images and failed writes preserve the old portrait and voice', async ({
  page,
  request,
}, info) => {
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  const initial = await (await request.get(`${info.url}/status`)).json();
  const original = fs.readFileSync('tests/fixtures/portrait.jpg');
  const created = await (
    await request.post(`${info.url}/avatars`, {
      data: {
        session: initial.session,
        name: 'Replace portrait',
        voice: 'zira',
        image: original.toString('base64'),
      },
    })
  ).json();
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(created.id);
  await expect(page.locator('#pair-status')).toContainText('Active: Replace portrait');
  await page.getByRole('button', { name: 'Edit avatar', exact: true }).click();
  await page
    .getByLabel('Portrait image', { exact: true })
    .setInputFiles({ name: 'bad.png', mimeType: 'image/png', buffer: Buffer.from('bad') });
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-save-status')).toContainText('valid JPEG or PNG');
  const replacement = execFileSync(
    python,
    [
      '-c',
      "import io,sys;from PIL import Image;b=io.BytesIO();Image.new('RGB',(32,32),'blue').save(b,format='PNG');sys.stdout.buffer.write(b.getvalue())",
    ],
    { timeout: 30_000 },
  );
  await page
    .getByLabel('Portrait image', { exact: true })
    .setInputFiles({ name: 'new.png', mimeType: 'image/png', buffer: replacement });
  await page.getByLabel('Voice', { exact: true }).selectOption('hazel');
  const db = path.join(info.output, 'user-data', 'avatars.sqlite3');
  execFileSync(
    python,
    [
      '-c',
      'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("CREATE TRIGGER reject_update AFTER UPDATE ON avatars BEGIN SELECT RAISE(ABORT, \'fixture write failure\'); END");c.commit();c.close()',
      db,
    ],
    { timeout: 30_000 },
  );
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-save-status')).toContainText('storage unavailable');
  expect(
    (await (await request.get(`${info.url}/status`)).json()).avatars.find(
      (a) => a.id === created.id,
    ).voice,
  ).toBe('zira');
  expect(await (await request.get(`${info.url}/portrait?avatar=${created.id}`)).body()).toEqual(
    original,
  );
  execFileSync(
    python,
    [
      '-c',
      "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('DROP TRIGGER reject_update');c.commit();c.close()",
      db,
    ],
    { timeout: 30_000 },
  );
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-result')).toContainText('Updated Replace portrait');
  await expect(page.locator('#pair-status')).toContainText('Active: Replace portrait');
  expect(await (await request.get(`${info.url}/portrait?avatar=${created.id}`)).body()).toEqual(
    replacement,
  );
  const status = await (await request.get(`${info.url}/status`)).json();
  expect(status.avatars.find((a) => a.id === created.id).voice).toBe('hazel');
  await expect(page.locator('#portrait')).toHaveAttribute(
    'src',
    new RegExp(`revision=${status.pairSequence}$`),
  );
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await openSettings(page);
  await expect(page.getByRole('button', { name: 'Edit avatar', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Delete avatar', exact: true })).toBeDisabled();
  await backToConversation(page);
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
});

async function startFixture(info) {
  const output = info.output;
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  const child = spawn(
    python,
    [
      'scripts/conversation.py',
      '--test-backend',
      '--port',
      '0',
      '--output',
      output,
      '--inputs',
      output,
      '--user-data',
      path.join(output, 'user-data'),
    ],
    {
      stdio: ['pipe', 'pipe', 'pipe'],
    },
  );
  info.app = child;
  info.appClosed = new Promise((resolve) => child.once('close', resolve));
  info.output = output;
  // Drain stderr and retain a bounded tail so CI fixture failures expose their cause.
  let stderr = '';
  child.stderr.on('data', (chunk) => {
    stderr = (stderr + chunk).slice(-8000);
  });
  info.appDiagnostics = () => ({
    pid: child.pid,
    exitCode: child.exitCode,
    signalCode: child.signalCode,
    stderr,
  });
  const timeout = setTimeout(() => killFixture(child), 960_000);
  info.appTimeout = timeout;
  info.url = await new Promise((resolve, reject) => {
    let text = '';
    const startup = setTimeout(() => reject(Error('Fixture startup exceeded 60 seconds')), 60_000);
    child.once('exit', (code) => {
      clearTimeout(startup);
      reject(Error(`Fixture exited ${code}`));
    });
    child.stdout.on('data', (chunk) => {
      text += chunk;
      const match = text.match(/LISTEN (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(startup);
        resolve(match[1]);
      }
    });
  });
}

function killFixture(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === 'win32') {
    // Fixed task-owned PID; terminate the venv launcher and its interpreter together.
    execFileSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { timeout: 30_000 });
  } else child.kill('SIGKILL');
}

async function stopFixture(info, interrupted = false) {
  clearTimeout(info.appTimeout);
  const child = info.app;
  if (!child) return;
  const closed = info.appClosed;
  let timer;
  try {
    if (child.exitCode === null && child.signalCode === null) {
      if (interrupted) killFixture(child);
      else {
        // Let the backend cancel/join its worker and release SQLite handles before cleanup.
        await fetch(`${info.url}/shutdown`, {
          method: 'POST',
          signal: AbortSignal.timeout(10_000),
        });
      }
    }
    await Promise.race([
      closed,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error('Fixture shutdown exceeded 30 seconds')), 30_000);
      }),
    ]);
  } catch (error) {
    killFixture(child);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function removeFixtureOutput(directory) {
  const output = fs.realpathSync(directory);
  const temporary = fs.realpathSync(os.tmpdir());
  if (
    path.dirname(output).toLowerCase() !== temporary.toLowerCase() ||
    !path.basename(output).startsWith('thead-browser-')
  ) {
    throw Error('Unexpected fixture cleanup path');
  }
  // Windows may retain a handle briefly after process exit or antivirus scanning.
  fs.rmSync(output, { recursive: true, force: true, maxRetries: 10, retryDelay: 250 });
}

test.beforeEach(async ({ page }, info) => {
  info.output = fs.mkdtempSync(path.join(os.tmpdir(), 'thead-browser-'));
  for (const filename of ['portrait.jpg', 'hopper.jpg']) {
    fs.copyFileSync('tests/fixtures/portrait.jpg', path.join(info.output, filename));
  }
  await startFixture(info);
  // External media transport substitute: real playable synthetic colour/tone,
  // not an assertion of avatar/TTS quality. Conversation/backend remain real.
  await page.route('**/segment?*', async (route) => {
    const index = new URL(route.request().url()).searchParams.get('index');
    if (index === '0')
      await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
    else await route.fulfill({ status: 204, body: '' });
  });
  await page.goto(info.url);
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await page.getByText('Session details', { exact: true }).click();
});

for (const custom of [false, true]) {
  test(`default avatar saves ${custom ? 'a user avatar' : 'a built-in avatar'} for startup without switching the current conversation`, async ({
    page,
    request,
  }, info) => {
    const before = await (await request.get(`${info.url}/status`)).json();
    let identity = 'hopper-hazel';
    let name = 'Grace';
    if (custom) {
      const response = await request.post(`${info.url}/avatars`, {
        data: {
          session: before.session,
          name: 'My default',
          voice: 'hazel',
          image: fs.readFileSync('tests/fixtures/portrait.jpg').toString('base64'),
        },
      });
      expect(response.ok()).toBe(true);
      identity = (await response.json()).id;
      name = 'My default';
    }
    await openSettings(page);
    const selector = page.getByLabel('Default avatar', { exact: true });
    await expect(selector).toHaveValue('jfk-zira');
    await expect(selector.locator(`option[value="${identity}"]`)).toHaveText(name);
    await selector.selectOption(identity);
    await expect(page.locator('#settings-status')).toContainText('app next starts');
    await expect(page.getByLabel('Avatar', { exact: true })).toHaveValue('jfk-zira');
    const saved = await (await request.get(`${info.url}/status`)).json();
    expect(saved.activeAvatar).toBe(before.activeAvatar);
    expect(saved.transcript).toEqual(before.transcript);
    expect(saved.budget).toEqual(before.budget);
    await page.reload();
    await openSettings(page);
    await expect(selector).toHaveValue(identity);
    await stopFixture(info);
    await startFixture(info);
    await page.goto(info.url);
    await expect(page.locator('#conversation')).toContainText(`Active avatar: ${name}`);
    await openSettings(page);
    await expect(selector).toHaveValue(identity);
    await page.getByLabel('Avatar', { exact: true }).selectOption('jfk-zira');
    await expect(page.locator('#pair-status')).toContainText('Active: JFK');
    await expect(selector).toHaveValue(identity);
    if (custom) {
      const session = (await (await request.get(`${info.url}/status`)).json()).session;
      const deleted = await request.post(`${info.url}/avatars/delete`, {
        data: { session, id: identity, name },
      });
      expect(deleted.ok()).toBe(true);
      await expect(selector).toHaveValue('jfk-zira');
      await stopFixture(info);
      await startFixture(info);
      await page.goto(info.url);
      await expect(page.locator('#conversation')).toContainText('Active avatar: JFK');
    }
  });
}

test('default avatar reports a failed save and restores the saved choice', async ({
  page,
  request,
}, info) => {
  const before = await (await request.get(`${info.url}/status`)).json();
  const db = path.join(info.output, 'user-data', 'avatars.sqlite3');
  execFileSync(
    process.env.THEAD_TEST_PYTHON || 'python',
    [
      '-c',
      'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("CREATE TRIGGER reject_preference AFTER INSERT ON preferences BEGIN SELECT RAISE(ABORT, \'fixture write failure\'); END");c.commit();c.close()',
      db,
    ],
    { timeout: 30_000 },
  );
  await openSettings(page);
  const selector = page.getByLabel('Default avatar', { exact: true });
  await selector.selectOption('hopper-hazel');
  await expect(page.locator('#settings-status')).toContainText('storage unavailable');
  await expect(selector).toHaveValue('jfk-zira');
  await expect(selector).toBeEnabled();
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.settings.defaultAvatar).toBe('jfk-zira');
  expect(after.activeAvatar).toBe(before.activeAvatar);
});

test('Settings navigation preserves draft, transcript, context and budget with keyboard focus', async ({
  page,
  request,
}, info) => {
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  const before = await (await request.get(`${info.url}/status`)).json();
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(page.getByLabel('Avatar', { exact: true })).toBeHidden();
    const workspace = await page.locator('.workspace').boundingBox();
    await page.getByRole('button', { name: 'Settings', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeFocused();
    await expect(page.locator('.avatar-panel')).toBeHidden();
    await expect(page.getByLabel('Question', { exact: true })).toBeHidden();
    const settings = await page.locator('#settings-page').boundingBox();
    expect(settings.x).toBe(workspace.x);
    expect(settings.width).toBe(workspace.width);
    expect(settings.height).toBeGreaterThan(0);
    await expect(page.getByLabel('Avatar', { exact: true })).toHaveValue('jfk-zira');
    await expect(page.getByLabel('Avatar', { exact: true })).toBeInViewport({ ratio: 1 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.getByRole('button', { name: 'Back to conversation' }).click();
    await expect(page.locator('.avatar-panel')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Settings', exact: true })).toBeFocused();
    await expect(page.getByLabel('Question', { exact: true })).toHaveValue('How do we detect one?');
  }
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.transcript).toEqual(before.transcript);
  expect(after.budget).toEqual(before.budget);
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.answer)
    .toContain('Earlier question: What is a black hole?');
});

test('model settings validate exact identifiers and switch contextual turns with captured accounting', async ({
  page,
  request,
}, info) => {
  await openSettings(page);
  await expect(page.getByLabel('Model', { exact: true })).toHaveValue('gpt-6-luna');
  await expect(page.locator('#model-availability')).toContainText('gpt-6.1-lunar is unavailable');
  const initial = await (await request.get(`${info.url}/status`)).json();
  for (const model of ['gpt-6.1-lunar', 'unknown']) {
    const rejected = await request.post(`${info.url}/settings`, {
      data: { session: initial.session, model },
    });
    expect(rejected.status()).toBe(409);
    expect((await rejected.json()).error).toContain('model');
  }
  await backToConversation(page);
  await page.getByLabel('Diagnostic fault').selectOption('llm-connect');
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await openSettings(page);
  await page.getByLabel('Model', { exact: true }).selectOption('gpt-6.1-sol');
  await expect(page.locator('#settings-status')).toContainText('Saved');
  const during = await (await request.get(`${info.url}/status`)).json();
  expect(during.run.model).toBe('gpt-6-luna');
  expect(during.settings.model).toBe('gpt-6.1-sol');
  await backToConversation(page);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect
    .poll(
      async () => (await (await request.get(`${info.url}/status`)).json()).run.usage.estimated_usd,
    )
    .toBe(0.000025);
  await page.getByLabel('Diagnostic fault').selectOption('');
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect
    .poll(
      async () => (await (await request.get(`${info.url}/status`)).json()).run.usage.estimated_usd,
    )
    .toBe(0.0005);
  const done = await (await request.get(`${info.url}/status`)).json();
  expect(done.run.model).toBe('gpt-6.1-sol');
  expect(done.run.answer).toContain('Earlier question: What is a black hole?');
  expect(
    done.run.events.find((event) => event.event === 'provider-request').configuration.model,
  ).toBe('gpt-6.1-sol');
  await expect(page.locator('#turn-usage')).toContainText('gpt-6.1-sol');
});

for (const [model, levels] of [
  ['gpt-6.1-sol', ['low', 'medium', 'high', 'xhigh', 'max']],
  ['gpt-6-luna', ['none', 'low', 'medium', 'high', 'xhigh', 'max']],
]) {
  test(`thinking levels for ${model} reach subsequent provider requests and usage`, async ({
    page,
    request,
  }, info) => {
    await openSettings(page);
    await page.getByLabel('Model', { exact: true }).selectOption(model);
    await expect(page.locator('#settings-status')).toContainText('Saved');
    for (const [index, level] of levels.entries()) {
      await openSettings(page);
      await page.getByLabel('Thinking level', { exact: true }).selectOption(level);
      await expect(page.locator('#settings-status')).toContainText('Saved');
      await backToConversation(page);
      await expect(
        page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
      ).toBeEnabled();
      await page.getByLabel('Question', { exact: true }).fill(`Thinking question ${index}`);
      await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
      await expect
        .poll(async () => {
          const status = await (await request.get(`${info.url}/status`)).json();
          return (
            status.transcript.at(-1)?.question === `Thinking question ${index}` &&
            status.run.usage.estimated_usd
          );
        })
        .toBe(model === 'gpt-6.1-sol' ? 0.0005 : 0.000025);
      const done = await (await request.get(`${info.url}/status`)).json();
      const config = done.run.events.find(
        (event) => event.event === 'provider-request',
      ).configuration;
      expect(config).toEqual({ model, reasoning: { effort: level }, max_output_tokens: 384 });
      expect(done.run.usage.reasoning_tokens).toBe(10);
      await expect(page.locator('#turn-usage')).toContainText(`Thinking: ${level}`);
      await expect(page.locator('#status')).toHaveText('Playback ended');
    }
  });
}

test('thinking compatibility, active capture and provider rejection recover without losing context', async ({
  page,
  request,
}, info) => {
  await openSettings(page);
  await page.getByLabel('Model', { exact: true }).selectOption('gpt-6.1-sol');
  await expect(page.locator('#settings-status')).toContainText('medium');
  await expect(page.getByLabel('Thinking level', { exact: true })).toHaveValue('medium');
  const before = await (await request.get(`${info.url}/status`)).json();
  const invalid = await request.post(`${info.url}/settings`, {
    data: { session: before.session, thinkingLevel: 'none' },
  });
  expect(invalid.status()).toBe(409);
  expect((await invalid.json()).error).toContain('Unsupported thinking level');
  await page.getByLabel('Thinking level', { exact: true }).selectOption('high');
  await expect(page.locator('#settings-status')).toContainText('Saved');
  await backToConversation(page);
  await page.getByLabel('Diagnostic fault').selectOption('llm-connect');
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await openSettings(page);
  await page.getByLabel('Thinking level', { exact: true }).selectOption('low');
  await expect(page.locator('#settings-status')).toContainText('Saved');
  const during = await (await request.get(`${info.url}/status`)).json();
  expect(during.run.thinkingLevel).toBe('high');
  expect(during.settings.thinkingLevel).toBe('low');
  await backToConversation(page);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await page.unroute('**/segment?*');
  await page.getByLabel('Diagnostic fault').selectOption('llm-settings');
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toContainText('change Settings and retry');
  await page.route('**/segment?*', async (route) => {
    const index = new URL(route.request().url()).searchParams.get('index');
    if (index === '0')
      await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
    else await route.fulfill({ status: 204, body: '' });
  });
  await page.getByLabel('Diagnostic fault').selectOption('');
  await page.getByLabel('Question', { exact: true }).fill('Recovery follow-up');
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.answer)
    .toContain('Earlier question: What is a black hole?');
  await openSettings(page);
  await page.getByLabel('Model', { exact: true }).selectOption('gpt-6-luna');
  await expect(page.locator('#settings-status')).toContainText('Saved');
  await expect(page.getByLabel('Thinking level', { exact: true })).toHaveValue('low');
});

test('Settings keeps active-turn controls usable and preserves playback', async ({
  page,
  request,
}, info) => {
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#video')).toHaveClass('presenting');
  const before = await (await request.get(`${info.url}/status`)).json();
  const source = await page.locator('#video').getAttribute('src');
  await openSettings(page);
  await expect(page.getByLabel('Avatar', { exact: true })).toBeDisabled();
  await expect(page.locator('#video')).toHaveAttribute('src', source);
  await expect(page.locator('#video')).toHaveJSProperty('paused', false);
  await backToConversation(page);
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.run.id).toBe(before.run.id);
  expect(after.budget).toEqual(before.budget);
  await openSettings(page);
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.locator('#video')).not.toHaveAttribute('src');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await backToConversation(page);
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
});

test('create a named avatar without changing selection or making a provider request', async ({
  page,
  request,
}, info) => {
  const before = await (await request.get(`${info.url}/status`)).json();
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await page.getByLabel('Avatar name', { exact: true }).fill('  My avatar  ');
  await page
    .getByLabel('Portrait image', { exact: true })
    .setInputFiles('tests/fixtures/portrait.jpg');
  await expect(page.getByRole('img', { name: 'Portrait preview' })).toBeVisible();
  await page.getByLabel('Voice', { exact: true }).selectOption('hazel');
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Created My avatar' })).toBeVisible();
  await expect(
    page.getByLabel('Avatar', { exact: true }).locator('option', { hasText: 'My avatar' }),
  ).toHaveCount(1);
  const saved = await (await request.get(`${info.url}/status`)).json();
  expect(saved.activePair).toBe(before.activePair);
  expect(saved.transcript).toEqual(before.transcript);
  expect(saved.budget.estimated_usd).toBe(before.budget.estimated_usd);
  const avatar = saved.avatars.find((item) => item.name === 'My avatar');
  expect(avatar.voice).toBe('hazel');
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(avatar.id);
  await expect(page.locator('#pair-status')).toContainText('Active: My avatar');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  expect((await (await request.get(`${info.url}/status`)).json()).run.pair).toBe(avatar.id);
});

test('avatar editor explains square cropping before upload and flags non-square portraits', async ({
  page,
  request,
}, info) => {
  const portrait = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1854;
    canvas.height = 2670;
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await expect(page.locator('#avatar-image-guidance')).toContainText('square');
  const warning = page.locator('#avatar-image-warning');
  await expect(warning).toBeEmpty();
  const picker = page.getByLabel('Portrait image', { exact: true });
  await picker.setInputFiles({
    name: 'tall.png',
    mimeType: 'image/png',
    buffer: Buffer.from(portrait, 'base64'),
  });
  await expect(warning).toContainText('1854 × 2670');
  await expect(warning).toContainText('Crop it to a square');
  await picker.setInputFiles('tests/fixtures/portrait.jpg');
  await expect(warning).toBeEmpty();
  await picker.setInputFiles({
    name: 'tall.png',
    mimeType: 'image/png',
    buffer: Buffer.from(portrait, 'base64'),
  });
  await expect(warning).toContainText('1854 × 2670');
  await picker.setInputFiles({
    name: 'broken.png',
    mimeType: 'image/png',
    buffer: Buffer.from('not an image'),
  });
  await expect(warning).toBeEmpty();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await expect(warning).toBeEmpty();
  await picker.setInputFiles({
    name: 'tall.png',
    mimeType: 'image/png',
    buffer: Buffer.from(portrait, 'base64'),
  });
  await page.getByLabel('Avatar name', { exact: true }).fill('Tall portrait');
  await page.getByLabel('Voice', { exact: true }).selectOption('zira');
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-editor')).toBeHidden();
  const status = await (await request.get(`${info.url}/status`)).json();
  const avatar = status.avatars.find((item) => item.name === 'Tall portrait');
  expect(await (await request.get(`${info.url}/portrait?avatar=${avatar.id}`)).body()).toEqual(
    Buffer.from(portrait, 'base64'),
  );
  await page.getByLabel('Avatar', { exact: true }).selectOption(avatar.id);
  await expect(page.locator('#pair-status')).toContainText('Active: Tall portrait');
  await page.getByRole('button', { name: 'Edit avatar', exact: true }).click();
  await expect(warning).toContainText('1854 × 2670');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
});

test('creation validates decoded uploads and names, retains fields and cancels without saving', async ({
  page,
  request,
}, info) => {
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await page.getByLabel('Avatar name', { exact: true }).fill('My corrected avatar');
  await page.getByLabel('Voice', { exact: true }).selectOption('zira');
  await page.getByLabel('Portrait image', { exact: true }).setInputFiles({
    name: '../../broken.png',
    mimeType: 'image/png',
    buffer: Buffer.from('not an image'),
  });
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-save-status')).toContainText('valid JPEG or PNG');
  await expect(page.getByLabel('Avatar name', { exact: true })).toHaveValue('My corrected avatar');
  await expect(page.getByLabel('Voice', { exact: true })).toHaveValue('zira');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await (await request.get(`${info.url}/status`)).json()).avatars).toHaveLength(2);
  const status = await (await request.get(`${info.url}/status`)).json();
  const valid = {
    session: status.session,
    name: 'My avatar',
    voice: 'zira',
    image: fs.readFileSync('tests/fixtures/portrait.jpg').toString('base64'),
  };
  for (const [override, message] of [
    [{ name: '   ' }, '1–80'],
    [{ name: 'x'.repeat(81) }, '1–80'],
    [{ name: 'gRaCe' }, 'already exists'],
    [{ name: 'JFK' }, 'already exists'],
    [{ voice: 'unsupported' }, 'Voice unavailable'],
    [{ image: Buffer.from('broken').toString('base64') }, 'valid JPEG or PNG'],
    [{ image: '%%%invalid' }, 'valid JPEG or PNG'],
    [{ image: Buffer.alloc(5 * 1024 * 1024 + 1).toString('base64') }, '5 MiB'],
    [
      {
        image: Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64').toString(
          'base64',
        ),
      },
      'JPEG or PNG',
    ],
  ]) {
    const result = await request.post(`${info.url}/avatars`, { data: { ...valid, ...override } });
    expect(result.status()).toBe(409);
    expect((await result.json()).error).toContain(message);
  }
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  const large = execFileSync(
    python,
    [
      '-c',
      "import io,base64;from PIL import Image;b=io.BytesIO();Image.new('RGB',(4097,1)).save(b,format='PNG');print(base64.b64encode(b.getvalue()).decode())",
    ],
    { timeout: 30000 },
  )
    .toString()
    .trim();
  const oversized = await request.post(`${info.url}/avatars`, { data: { ...valid, image: large } });
  expect((await oversized.json()).error).toContain('4096');
  const results = await Promise.all([
    request.post(`${info.url}/avatars`, { data: valid }),
    request.post(`${info.url}/avatars`, { data: { ...valid, name: 'MY AVATAR' } }),
  ]);
  expect(results.map((result) => result.status()).sort()).toEqual([200, 409]);
  const saved = await (await request.get(`${info.url}/status`)).json();
  expect(saved.avatars).toHaveLength(3);
  expect(saved.transcript).toEqual([]);
  expect(saved.budget.estimated_usd).toBe(status.budget.estimated_usd);
});

test('saved portrait survives source removal, failed save and restart; corrupt storage preserves built-ins', async ({
  page,
  request,
}, info) => {
  const source = path.join(info.output, 'source.jpg');
  fs.copyFileSync('tests/fixtures/portrait.jpg', source);
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await page.getByLabel('Avatar name', { exact: true }).fill('Persistent avatar');
  await page.getByLabel('Voice', { exact: true }).selectOption('hazel');
  await page.getByLabel('Portrait image', { exact: true }).setInputFiles(source);
  // Hold the response to verify UI submission protection without replacing the backend.
  let requests = 0;
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route('**/avatars', async (route) => {
    requests++;
    await gate;
    await route.continue();
  });
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
  await page.locator('#avatar-form').dispatchEvent('submit');
  release();
  await expect(page.locator('#avatar-result')).toContainText('Created Persistent avatar');
  expect(requests).toBe(1);
  await page.unroute('**/avatars');
  fs.unlinkSync(source);
  const before = await (await request.get(`${info.url}/status`)).json();
  const saved = before.avatars.find((item) => item.name === 'Persistent avatar');
  const db = path.join(info.output, 'user-data', 'avatars.sqlite3');
  // Real storage failure: the database path becomes an unwritable directory.
  fs.renameSync(db, `${db}.preserved`);
  fs.mkdirSync(db);
  try {
    await openSettings(page);
    await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
    await page.getByLabel('Avatar name', { exact: true }).fill('Failed save');
    await page.getByLabel('Voice', { exact: true }).selectOption('zira');
    await page
      .getByLabel('Portrait image', { exact: true })
      .setInputFiles('tests/fixtures/portrait.jpg');
    await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
    await expect(page.locator('#avatar-save-status')).toContainText('storage unavailable');
    await expect(page.getByLabel('Avatar name', { exact: true })).toHaveValue('Failed save');
  } finally {
    fs.rmdirSync(db);
    fs.renameSync(`${db}.preserved`, db);
  }
  await stopFixture(info);
  await startFixture(info);
  await page.goto(info.url);
  await expect(page.getByLabel('Avatar', { exact: true }).locator('option')).toHaveCount(3);
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(saved.id);
  await expect(page.locator('#pair-status')).toContainText('Active: Persistent avatar');
  const portrait = await request.get(`${info.url}/portrait?avatar=${saved.id}`);
  expect(await portrait.body()).toEqual(fs.readFileSync('tests/fixtures/portrait.jpg'));
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.locator('#transcript')).toContainText('Earlier question');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await stopFixture(info);
  fs.writeFileSync(db, 'corrupt database');
  await startFixture(info);
  await page.goto(info.url);
  await expect(page.locator('#avatar-storage-error')).toContainText('Preserve');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await expect(page.getByLabel('Avatar', { exact: true }).locator('option')).toHaveCount(2);
});

test('creating and cancelling during playback preserve active media and context', async ({
  page,
  request,
}, info) => {
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#video')).toHaveClass('presenting');
  const before = await (await request.get(`${info.url}/status`)).json();
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await page.getByLabel('Avatar name', { exact: true }).fill('During playback');
  await page.getByLabel('Voice', { exact: true }).selectOption('zira');
  await page.getByLabel('Portrait image', { exact: true }).setInputFiles({
    name: '../../outside.png',
    mimeType: 'image/jpeg',
    buffer: fs.readFileSync('tests/fixtures/portrait.jpg'),
  });
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.locator('#avatar-result')).toContainText('Created During playback');
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.run.id).toBe(before.run.id);
  expect(after.activePair).toBe(before.activePair);
  expect(after.session).toBe(before.session);
  expect(after.transcript).toHaveLength(1);
  await openSettings(page);
  await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByLabel('Avatar', { exact: true })).toBeEnabled();
  const saved = after.avatars.find((item) => item.name === 'During playback');
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(saved.id);
  await expect(page.locator('#pair-status')).toContainText('Active: During playback');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.locator('#transcript')).toContainText('Earlier question');
});

test('PNG creation and saved avatar preparation errors recover without losing healthy avatars', async ({
  page,
  request,
}, info) => {
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  const png = execFileSync(
    python,
    [
      '-c',
      "import io,base64;from PIL import Image;b=io.BytesIO();Image.open('tests/fixtures/portrait.jpg').save(b,format='PNG');print(base64.b64encode(b.getvalue()).decode())",
    ],
    { timeout: 30000 },
  )
    .toString()
    .trim();
  const initial = await (await request.get(`${info.url}/status`)).json();
  const saved = await (
    await request.post(`${info.url}/avatars`, {
      data: {
        session: initial.session,
        name: 'PNG avatar',
        voice: 'zira',
        image: png,
        filename: '../../outside.png',
      },
    })
  ).json();
  expect(
    (await request.get(`${info.url}/portrait?avatar=${saved.id}`)).headers()['content-type'],
  ).toBe('image/png');
  await expect(page.getByLabel('Avatar', { exact: true }).locator('option')).toHaveCount(3);
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-voice-missing');
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(saved.id);
  await expect(page.locator('#pair-status')).toContainText('PNG avatar preparation failed');
  expect((await (await request.get(`${info.url}/status`)).json()).activePair).toBe('jfk-zira');
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('');
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption('jfk-zira');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  // Simulate an invalid persisted record through the external storage boundary.
  execFileSync(
    python,
    [
      '-c',
      "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE avatars SET voice = ? WHERE id = ?',('invalid',sys.argv[2]));c.commit();c.close()",
      path.join(info.output, 'user-data', 'avatars.sqlite3'),
      saved.id,
    ],
    { timeout: 30000 },
  );
  await expect(page.locator('#avatar-storage-error')).toContainText('Invalid saved avatar record');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  const healthy = await request.post(`${info.url}/avatars`, {
    data: { session: initial.session, name: 'Healthy avatar', voice: 'hazel', image: png },
  });
  expect(healthy.status()).toBe(200);
  const healthyId = (await healthy.json()).id;
  await expect(
    page.getByLabel('Avatar', { exact: true }).locator('option', { hasText: 'Healthy avatar' }),
  ).toHaveCount(1);
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption(healthyId);
  await expect(page.locator('#pair-status')).toContainText('Active: Healthy avatar');
});

for (const editing of [false, true]) {
  test(`interrupted ${editing ? 'edit' : 'creation'} leaves existing avatars usable after restart`, async ({
    page,
    request,
  }, info) => {
    const initial = await (await request.get(`${info.url}/status`)).json();
    const data = {
      session: initial.session,
      name: 'Preserved avatar',
      voice: 'zira',
      image: fs.readFileSync('tests/fixtures/portrait.jpg').toString('base64'),
    };
    const created = await (await request.post(`${info.url}/avatars`, { data })).json();
    await openSettings(page);
    if (editing) {
      await page.getByLabel('Avatar', { exact: true }).selectOption(created.id);
      await expect(page.locator('#pair-status')).toContainText('Active: Preserved avatar');
    }
    await page
      .getByRole('button', { name: editing ? 'Edit avatar' : 'Create avatar', exact: true })
      .click();
    await page.getByLabel('Avatar name', { exact: true }).fill('Interrupted avatar');
    await page.getByLabel('Voice', { exact: true }).selectOption('hazel');
    await page
      .getByLabel('Portrait image', { exact: true })
      .setInputFiles('tests/fixtures/portrait.jpg');
    const python = process.env.THEAD_TEST_PYTHON || 'python';
    const locker = spawn(
      python,
      [
        '-u',
        '-c',
        "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN IMMEDIATE');print('locked',flush=True);sys.stdin.readline();c.rollback();c.close()",
        path.join(info.output, 'user-data', 'avatars.sqlite3'),
      ],
      { stdio: ['pipe', 'pipe', 'pipe'] },
    );
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(Error('storage lock exceeded 30s')), 30000);
        locker.stdout.once('data', () => {
          clearTimeout(timer);
          resolve();
        });
      });
      const dispatched = page.waitForRequest(editing ? '**/avatars/update' : '**/avatars');
      await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
      await dispatched;
      await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
      await stopFixture(info, true);
    } finally {
      const released = new Promise((resolve) => locker.once('exit', resolve));
      locker.stdin.end('\n');
      await released;
    }
    await startFixture(info);
    await page.goto(info.url);
    await expect(
      page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
    ).toBeEnabled();
    const avatars = (await (await request.get(`${info.url}/status`)).json()).avatars;
    expect(avatars.map((item) => item.name)).toEqual(['JFK', 'Grace', 'Preserved avatar']);
    expect(avatars.find((a) => a.id === created.id).voice).toBe('zira');
    expect(await (await request.get(`${info.url}/portrait?avatar=${created.id}`)).body()).toEqual(
      fs.readFileSync('tests/fixtures/portrait.jpg'),
    );
    expect(fs.readdirSync(path.join(info.output, 'user-data'))).toEqual(['avatars.sqlite3']);
  });
}

test('portrait stays visible through preparation, playback, Stop, reset and pair changes', async ({
  page,
  request,
}, info) => {
  const portrait = page.getByRole('img', {
    name: 'JFK portrait',
    exact: true,
    includeHidden: true,
  });
  await expect(portrait).toHaveClass('loaded');
  const response = await request.get(`${info.url}/portrait?pair=jfk-zira`);
  expect(response.headers()['content-type']).toBe('image/jpeg');
  expect(await response.body()).toEqual(fs.readFileSync('tests/fixtures/portrait.jpg'));
  expect((await request.get(`${info.url}/portrait?pair=../../README.md`)).status()).toBe(400);
  await page.getByLabel('Diagnostic fault').selectOption('llm-delay');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(portrait).toHaveCSS('opacity', '1');
  await expect(page.locator('#video')).toHaveCSS('opacity', '0');
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(portrait).toHaveClass('loaded');
  await expect(page.locator('#video')).not.toHaveAttribute('src');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(portrait).toHaveClass('loaded');
  await expect(page.locator('#transcript')).toBeEmpty();
  await page.getByLabel('Diagnostic fault').selectOption('');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#video')).toHaveClass('presenting');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.locator('#video')).toHaveCSS('opacity', '0');
  await expect(portrait).toHaveClass('loaded');
  await expect(page.getByLabel('Avatar', { exact: true })).toBeEnabled();
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption('hopper-hazel');
  await expect(
    page.getByRole('img', { name: 'Grace portrait', exact: true, includeHidden: true }),
  ).toHaveClass('loaded');
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-prepare');
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption('jfk-zira');
  await expect(page.locator('#pair-status')).toContainText('failed');
  await expect(
    page.getByRole('img', { name: 'Grace portrait', exact: true, includeHidden: true }),
  ).toHaveClass('loaded');
});

test('compact layout keeps portrait and composer on screen while the transcript scrolls', async ({
  page,
}) => {
  await page.getByText('Session details', { exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  for (let index = 0; index < 3; index++) {
    await expect(ask).toBeEnabled();
    await backToConversation(page);
    await page.getByLabel('Question', { exact: true }).fill(`Question ${index}`);
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
  }
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 320, height: 568 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(viewport);
    await page.locator('.history').evaluate((element) => {
      element.scrollTop = 0;
    });
    const panel = await page.locator('.avatar-panel').boundingBox();
    const settings = await page.locator('.avatar-settings').boundingBox();
    expect(settings.y).toBeGreaterThanOrEqual(panel.y);
    expect(settings.y + settings.height).toBeLessThanOrEqual(panel.y + panel.height);
    await expect(page.locator('#portrait')).toBeInViewport({ ratio: 1 });
    await expect(ask).toBeInViewport({ ratio: 1 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
});

test('missing portrait gives a useful fallback and another avatar can recover', async ({
  page,
  request,
}, info) => {
  fs.unlinkSync(path.join(info.output, 'portrait.jpg'));
  expect((await request.get(`${info.url}/portrait?pair=jfk-zira`)).status()).toBe(404);
  await page.reload();
  await expect(page.locator('#portrait-notice')).toContainText('Rerun the launch command');
  await expect(page.locator('#portrait')).not.toHaveClass('loaded');
  await expect(page.getByLabel('Avatar', { exact: true })).toBeEnabled();
  await openSettings(page);
  await page.getByLabel('Avatar', { exact: true }).selectOption('hopper-hazel');
  await expect(
    page.getByRole('img', { name: 'Grace portrait', exact: true, includeHidden: true }),
  ).toHaveClass('loaded');
});

test('bounded 100-turn session trims context, rejects turn 101 and resets', async ({
  page,
  request,
}, info) => {
  test.setTimeout(900_000);
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  for (let index = 0; index < 100; index++) {
    await expect(ask).toBeEnabled();
    const question = `Turn ${index}: ${'context '.repeat(120)}`;
    await backToConversation(page);
    await page.getByLabel('Question', { exact: true }).fill(question);
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#transcript')).toContainText(`You: Turn ${index}:`);
    await expect(page.locator('#status')).toHaveText('Playback ended');
  }
  await expect(ask).toBeEnabled();
  await expect(page.locator('#transcript')).toContainText('exchanges omitted');
  const before = await (await request.get(`${info.url}/status`)).json();
  expect(before.transcript).toHaveLength(100);
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('This turn must be rejected');
  await backToConversation(page);
  await ask.click();
  await expect(page.locator('#status')).toContainText('100 turns');
  const rejected = await (await request.get(`${info.url}/status`)).json();
  expect(rejected.transcript).toHaveLength(100);
  expect(rejected.budget.estimated_usd).toBe(before.budget.estimated_usd);
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(ask).toBeEnabled();
  await backToConversation(page);
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const fresh = await (await request.get(`${info.url}/status`)).json();
  expect(fresh.transcript).toHaveLength(1);
  const dispatched = fresh.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages).toHaveLength(1);
});

test.afterEach(async ({ page }, info) => {
  try {
    if (info.status !== info.expectedStatus) {
      console.error('Fixture diagnostics:', JSON.stringify(info.appDiagnostics?.()));
    }
    await page.close();
  } finally {
    await stopFixture(info);
    removeFixtureOutput(info.output);
  }
});

test('switch both directions between turns, reject busy selection, retain context after Stop and reset', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  const pair = page.getByLabel('Avatar', { exact: true });
  await expect(pair).toHaveValue('jfk-zira');
  await backToConversation(page);
  await ask.click();
  await expect(pair).toBeDisabled();
  const busy = await (await request.get(`${info.url}/status`)).json();
  const conflict = await request.post(`${info.url}/select`, {
    data: { session: busy.session, pair: 'hopper-hazel' },
  });
  expect(conflict.status()).toBe(409);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(pair).toBeEnabled();
  await openSettings(page);
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Active: Grace');
  await expect(ask).toBeEnabled();
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await backToConversation(page);
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const followup = await (await request.get(`${info.url}/status`)).json();
  expect(followup.run.pair).toBe('hopper-hazel');
  expect(followup.run.answer).toContain('Earlier question: What is a black hole?');
  await page.getByLabel('Diagnostic fault').selectOption('llm-delay');
  await expect(ask).toBeEnabled();
  await backToConversation(page);
  await ask.click();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(pair).toBeEnabled();
  const selected = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/select',
  );
  await openSettings(page);
  await pair.selectOption('jfk-zira');
  const selectedResponse = await selected;
  expect((await selectedResponse.json()).error).toBe('');
  await expect(page.locator('#pair-status')).toContainText('Active: JFK');
  await expect(ask).toBeEnabled();
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(pair).toHaveValue('jfk-zira');
  const fresh = await (await request.get(`${info.url}/status`)).json();
  expect(fresh.transcript).toHaveLength(0);
  expect(fresh.activePair).toBe('jfk-zira');
});

test('reset and Stop during loading retain choice, reject overlapping selection and expire old media', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  const pair = page.getByLabel('Avatar', { exact: true });
  await backToConversation(page);
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const before = await settledStatus(request, info.url);
  expect(before.budget.estimated_usd).toBeGreaterThan(0);
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-delay');
  await expect(pair).toBeEnabled();
  await openSettings(page);
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Preparing Grace');
  await expect(ask).toBeDisabled();
  await expect(pair).toBeDisabled();
  const conflict = await request.post(`${info.url}/select`, {
    data: { session: before.session, pair: 'jfk-zira' },
  });
  expect(conflict.status()).toBe(409);
  const stale = await request.get(`${info.url}/segment?run=${before.run.id}&index=0`);
  expect(stale.status()).toBe(410);
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(ask).toBeEnabled();
  await expect(pair).toHaveValue('hopper-hazel');
  const ready = await (await request.get(`${info.url}/status`)).json();
  expect(ready.session).not.toBe(before.session);
  expect(ready.budget.estimated_usd).toBe(before.budget.estimated_usd);
  expect(ready.budget.reserved_usd).toBe(0);
  expect(ready.activePair).toBe('hopper-hazel');
  await backToConversation(page);
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const after = await (await request.get(`${info.url}/status`)).json();
  const dispatched = after.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages).toHaveLength(1);
  expect(after.run.pair).toBe('hopper-hazel');
});

for (const fault of [
  'pair-portrait-missing',
  'pair-portrait-unreadable',
  'pair-portrait-invalid',
  'pair-voice-missing',
  'pair-voice-invalid',
  'pair-prepare',
  'pair-delay-fail',
]) {
  test(`pair failure ${fault} preserves active pair and accounting, then recovers context`, async ({
    page,
    request,
  }, info) => {
    const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
    const pair = page.getByLabel('Avatar', { exact: true });
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    const before = await settledStatus(request, info.url);
    expect(before.budget.estimated_usd).toBeGreaterThan(0);
    await page.getByLabel('Pair diagnostic', { exact: true }).selectOption(fault);
    await expect(pair).toBeEnabled();
    await openSettings(page);
    await pair.selectOption('hopper-hazel');
    await expect(page.locator('#pair-status')).toContainText('Grace');
    await expect(page.locator('#pair-status')).toContainText('failed');
    await expect(ask).toBeDisabled();
    const failed = await (await request.get(`${info.url}/status`)).json();
    expect(failed.activePair).toBe('jfk-zira');
    expect(failed.selectedPair).toBe('hopper-hazel');
    expect(failed.ready).toBe(false);
    expect(failed.budget.estimated_usd).toBe(before.budget.estimated_usd);
    expect(failed.transcript).toEqual(before.transcript);
    await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('');
    await openSettings(page);
    await pair.selectOption('jfk-zira');
    await expect(ask).toBeEnabled();
    await backToConversation(page);
    await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    const recovered = await (await request.get(`${info.url}/status`)).json();
    expect(recovered.run.answer).toContain('Earlier question: What is a black hole?');
    expect(recovered.run.pair).toBe('jfk-zira');
  });
}

test('late old media and delayed failed selection cannot revive playback after reset', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  const pair = page.getByLabel('Avatar', { exact: true });
  let releaseMedia;
  let receivedMedia;
  const mediaGate = new Promise((resolve) => {
    releaseMedia = resolve;
  });
  const received = new Promise((resolve) => {
    receivedMedia = resolve;
  });
  await page.route('**/segment?*', async (route) => {
    receivedMedia();
    await mediaGate;
    await route
      .fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' })
      .catch(() => {});
  });
  await backToConversation(page);
  await ask.click();
  await received;
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(pair).toBeEnabled();
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-delay-fail');
  await openSettings(page);
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Preparing Grace');
  await page.getByRole('button', { name: 'New conversation' }).click();
  releaseMedia();
  await expect(page.locator('#pair-status')).toContainText('failed');
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#video')).not.toHaveAttribute('src');
  const failed = await (await request.get(`${info.url}/status`)).json();
  expect(failed.selectedPair).toBe('hopper-hazel');
  expect(failed.activePair).toBe('jfk-zira');
  expect(failed.run).toBeNull();
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('');
  await openSettings(page);
  await pair.selectOption('jfk-zira');
  await expect(ask).toBeEnabled();
  expect((await (await request.get(`${info.url}/status`)).json()).activePair).toBe('jfk-zira');
});

test('reset acknowledgement gates the next selection and response', async ({ page }) => {
  let releaseReset;
  let resetAccepted;
  const gate = new Promise((resolve) => {
    releaseReset = resolve;
  });
  const accepted = new Promise((resolve) => {
    resetAccepted = resolve;
  });
  await page.route('**/reset', async (route) => {
    const response = await route.fetch();
    resetAccepted();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'New conversation' }).click();
  await accepted;
  const pair = page.getByLabel('Avatar', { exact: true });
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  try {
    expect(await pair.isDisabled()).toBe(true);
    expect(await ask.isDisabled()).toBe(true);
  } finally {
    releaseReset();
  }
  await expect(pair).toBeEnabled();
  await openSettings(page);
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Active: Grace');
  await expect(ask).toBeEnabled();
});

test('selection waits for backend playback completion acknowledgement', async ({ page }) => {
  let acknowledge;
  const gate = new Promise((resolve) => {
    acknowledge = resolve;
  });
  await page.route('**/telemetry', async (route) => {
    if (route.request().postDataJSON().event === 'ended') await gate;
    await route.continue();
  });
  const pair = page.getByLabel('Avatar', { exact: true });
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  try {
    // Wait for a post-ending status poll while the backend's ended event is held.
    await page.waitForResponse((response) => new URL(response.url()).pathname === '/status');
    await page.waitForFunction(
      () => JSON.parse(document.querySelector('#report').textContent).state === 'idle',
    );
    expect(await pair.isDisabled()).toBe(true);
  } finally {
    acknowledge();
  }
  await expect(pair).toBeEnabled();
  await openSettings(page);
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Active: Grace');
});

test('complete answer, contextual follow-up, idle Stop and fresh conversation', async ({
  page,
  request,
}, info) => {
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#transcript')).toContainText('A black hole traps light.');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const measured = (await (await request.get(`${info.url}/status`)).json()).run.events;
  const submitted = measured.find((event) => event.event === 'submit-action');
  const moving = measured.find((event) => event.event === 'moving-video');
  const audible = measured.find((event) => event.event === 'digital-audio-onset');
  expect(submitted.clientMilliseconds).toBeLessThan(moving.clientMilliseconds);
  expect(submitted.clientMilliseconds).toBeLessThan(audible.clientMilliseconds);
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
    .toBe('complete');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#transcript')).toContainText(
    'Earlier question: What is a black hole?',
  );
  const status = await (await request.get(`${info.url}/status`)).json();
  const dispatched = status.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages.some((message) => message.role === 'assistant')).toBe(true);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('A new topic');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#transcript')).toContainText('A new topic');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.locator('#transcript')).not.toContainText('Earlier question');
});

test('Session details combines turn usage, failures and interruptions without resetting budget', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  const details = page
    .locator('details')
    .filter({ has: page.getByText('Session details', { exact: true }) });
  const turns = details
    .getByRole('list', { name: 'Usage by conversation turn' })
    .getByRole('listitem');
  for (const [index, question] of ['First question', 'Second question'].entries()) {
    await expect(ask).toBeEnabled();
    await backToConversation(page);
    await page.getByLabel('Question', { exact: true }).fill(question);
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    await expect(turns.nth(index)).toContainText(`Turn ${index + 1}: ${question}`);
    await expect(turns.nth(index)).toContainText(
      'complete — Tokens: 100 input / 25 output (10 reasoning, included in output); estimated USD',
    );
  }
  await expect(page.locator('#transcript details')).toHaveCount(0);
  await expect(page.getByText('Turn usage', { exact: true })).toHaveCount(0);
  await expect(details).toContainText('Application estimates, not authoritative billing.');
  await expect(details.getByText('Timing diagnostics', { exact: true })).toBeVisible();
  await expect(details.getByLabel('Diagnostic fault')).toBeVisible();
  await expect(details.getByLabel('Pair diagnostic', { exact: true })).toBeVisible();

  await expect(ask).toBeEnabled();
  await page.getByLabel('Diagnostic fault').selectOption('llm-delay');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('Interrupted question');
  await backToConversation(page);
  await ask.click();
  await expect(turns.nth(2)).toContainText('Turn 3: Interrupted question');
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(turns.nth(2)).toContainText('Interrupted — Tokens: unknown input / unknown output');
  await expect(turns.nth(2)).toContainText('conservative allowance; final usage unavailable');

  await expect(ask).toBeEnabled();
  await page.getByLabel('Diagnostic fault').selectOption('llm');
  await backToConversation(page);
  await page.getByLabel('Question', { exact: true }).fill('Failed question');
  await backToConversation(page);
  await ask.click();
  await expect(turns.nth(3)).toContainText('Turn 4: Failed question');
  await expect(turns.nth(3)).toContainText('failed — Tokens: unknown input / unknown output');
  await expect(turns.nth(3)).toContainText('conservative allowance; final usage unavailable');
  for (const viewport of [
    { width: 1280, height: 900 },
    { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(turns.nth(3)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  const before = await (await request.get(`${info.url}/status`)).json();
  await expect(page.locator('#usage')).toContainText(
    `estimated USD ${before.budget.estimated_usd.toFixed(6)} spent`,
  );
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(turns).toHaveCount(0);
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#usage')).toContainText(
    `estimated USD ${before.budget.estimated_usd.toFixed(6)} spent`,
  );
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.budget.estimated_usd).toBe(before.budget.estimated_usd);
  expect(after.budget.reserved_usd).toBe(before.budget.reserved_usd);
});

test('Stop cancels an accepted request whose start reply is delayed', async ({
  page,
  request,
}, info) => {
  let release;
  let accepted;
  const accept = new Promise((resolve) => {
    accepted = resolve;
  });
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route('**/ask', async (route) => {
    const response = await route.fetch();
    accepted();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByLabel('Diagnostic fault').selectOption('llm-delay');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await accept;
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
    .toBe('stopped');
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  release();
  await expect(page.locator('#transcript')).toContainText('Interrupted');
});

test('repeated Stop across delayed stages retains questions and excludes interrupted answers', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true });
  for (const [fault, stage] of [
    ['llm-connect', 'llm-connect'],
    ['llm-delay', 'llm-first-text'],
    ['tts-delay', 'tts-start'],
  ]) {
    await expect(ask).toBeEnabled();
    await page.getByLabel('Diagnostic fault').selectOption(fault);
    await backToConversation(page);
    await ask.click();
    await expect
      .poll(async () => {
        const status = await (await request.get(`${info.url}/status`)).json();
        return status.run.events.some((event) => event.event === stage);
      })
      .toBe(true);
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await expect(ask).toBeEnabled();
    const stopped = await (await request.get(`${info.url}/status`)).json();
    expect(stopped.run.state).toBe('stopped');
    expect(stopped.run.events.some((event) => event.event === 'resources-released')).toBe(true);
    const question = stopped.transcript.at(-1).question;
    const spent = stopped.budget.estimated_usd;
    await page.getByLabel('Diagnostic fault').selectOption('');
    await backToConversation(page);
    await page.getByLabel('Question', { exact: true }).fill(`Replacement after ${fault}`);
    await backToConversation(page);
    await ask.click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    await expect(ask).toBeEnabled();
    const next = await (await request.get(`${info.url}/status`)).json();
    const messages = next.run.events.find((event) => event.event === 'provider-request').messages;
    expect(messages.at(-2)).toEqual({ role: 'user', content: question });
    expect(next.budget.estimated_usd).toBeGreaterThanOrEqual(spent);
    await page.getByRole('button', { name: 'New conversation' }).click();
    await expect(page.locator('#transcript')).toBeEmpty();
  }
});

test('busy reset rejects late text and safe rendering keeps provider markup literal', async ({
  page,
}) => {
  await page.getByLabel('Diagnostic fault').selectOption('tts-delay');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#transcript')).toContainText('You: What is a black hole?');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(
    page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
  ).toBeEnabled();
  await page.getByLabel('Diagnostic fault').selectOption('markup');
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#transcript')).toContainText("<script>alert('text')</script>");
  await expect(page.locator('#transcript script')).toHaveCount(0);
});

test('provider, TTS and media failures recover, then budget rejection prevents dispatch', async ({
  page,
  request,
}, info) => {
  // Here use the real diagnostic media endpoint, including its injected failures.
  await page.unroute('**/segment?*');
  for (const fault of ['llm', 'missing-completion', 'tts', 'media']) {
    await page.getByLabel('Diagnostic fault').selectOption(fault);
    await backToConversation(page);
    await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
    await expect
      .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
      .toBe('failed');
    await expect(
      page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
    ).toBeEnabled();
    await page.route('**/segment?*', async (route) => {
      const index = new URL(route.request().url()).searchParams.get('index');
      if (index === '0')
        await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
      else await route.fulfill({ status: 204, body: '' });
    });
    await page.getByLabel('Diagnostic fault').selectOption('');
    await backToConversation(page);
    await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    await expect(
      page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }),
    ).toBeEnabled();
    await page.unroute('**/segment?*');
  }
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  // Seed only this test-owned ledger through the public accounting interface.
  execFileSync(
    python,
    [
      '-c',
      "import sys;from pathlib import Path;sys.path.insert(0,'scripts');from budget import Budget;b=Budget(Path(sys.argv[1]));b.settle(b.reserve('gpt-6-luna',0,79000000))",
      path.join(info.output, 'budget.sqlite3'),
    ],
    { timeout: 30_000 },
  );
  // Remaining allowance is 50 cents; consume it exactly, allowing prior fixture costs.
  execFileSync(
    python,
    [
      '-c',
      "import sys;from pathlib import Path;sys.path.insert(0,'scripts');from budget import Budget;b=Budget(Path(sys.argv[1]));n=int(b.snapshot()['remaining_usd']*1000000000)//500;b.settle(b.reserve('gpt-6-luna',0,n))",
      path.join(info.output, 'budget.sqlite3'),
    ],
    { timeout: 30_000 },
  );
  await page.getByLabel('Diagnostic fault').selectOption('');
  const before = await (await request.get(`${info.url}/status`)).json();
  await backToConversation(page);
  await page.getByRole('button', { name: 'Ask', exact: true, includeHidden: true }).click();
  await expect(page.locator('#status')).toContainText('budget');
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.transcript.length).toBe(before.transcript.length);
  expect(after.run.id).toBe(before.run.id);
  expect(after.budget.estimated_usd).toBe(before.budget.estimated_usd);
  expect(after.budget.reserved_usd).toBe(before.budget.reserved_usd);
});
