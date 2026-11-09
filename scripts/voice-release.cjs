// Native normal-app release evidence. No paid calls; shared-GPU execution must be serial.
const fs = require('node:fs');
const path = require('node:path');
const { createHash, randomUUID } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium, expect: baseExpect } = require('@playwright/test');

const expect = baseExpect.configure({ timeout: 240_000 });
const ROOT = path.resolve(__dirname, '..');
const TEXTS = [
  'Yes, that sounds good.',
  'A black hole traps light. We detect one by its effects on nearby matter.',
  'The meeting starts at nine forty-five.',
  'First, check the microphone. Next, record one clear sentence. Finally, listen to the last word.',
  'I can help with that.',
  'The garden is quiet today. A small bird is singing near the window.',
  'Please bring a glass of water.',
  'Open the book and read the first page. Then tell me what you found.',
  'We can try again tomorrow.',
  'The train leaves at half past ten. Please arrive early and keep your ticket ready.',
];

function distribution(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  return {
    count: sorted.length,
    median: sorted.length
      ? (sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.floor(sorted.length / 2)]) / 2
      : null,
    minimum: sorted[0] ?? null,
    maximum: sorted.at(-1) ?? null,
  };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--help')) {
    console.log(
      'node scripts/voice-release.cjs NEW_REPORT.json [--restart-phase PREVIOUS_REPORT.json]',
    );
    console.log(
      'Launch the no-cost normal diagnostic candidate separately; THEAD_URL defaults to port8771.',
    );
    return;
  }
  const output = path.resolve(args[0] || '');
  if (!args[0] || fs.existsSync(output))
    throw Error('Supply a new evidence JSON path; results are never overwritten');
  const restartIndex = args.indexOf('--restart-phase');
  const previous =
    restartIndex < 0 ? null : JSON.parse(fs.readFileSync(args[restartIndex + 1], 'utf8'));
  const url = process.env.THEAD_URL || 'http://127.0.0.1:8771';
  const endpoint = new URL(url);
  if (!['127.0.0.1', 'localhost'].includes(endpoint.hostname) || endpoint.protocol !== 'http:')
    throw Error('The evidence runner only connects to the local normal application');
  const revision = execFileSync('git', ['rev-parse', 'HEAD'], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 30_000,
  }).trim();
  const sourceFiles = [
    'scripts/voice-release.cjs',
    'scripts/conversation.py',
    'scripts/voice_app.py',
    'scripts/voices.py',
    'scripts/voices.js',
    'scripts/chatterbox_engine.py',
    'scripts/chatterbox_voice.py',
    'scripts/chatterbox_worker.py',
    'scripts/streaming.py',
    'scripts/streaming.js',
    'scripts/provider.py',
    'chatterbox-maintained-lock.json',
    'docs/runtime/chatterbox/requirements-maintained.lock',
  ].map((file) => ({
    path: file,
    sha256: createHash('sha256')
      .update(fs.readFileSync(path.join(ROOT, file)))
      .digest('hex'),
  }));
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const temporary = fs.mkdtempSync(path.join(path.dirname(output), 'voice-release-inputs-'));
  const browser = await chromium.launch({ headless: true });
  let expired = false;
  const limit = setTimeout(() => {
    expired = true;
    browser.close().catch(() => {});
  }, 3600_000);
  const page = await browser.newPage();
  page.setDefaultTimeout(240_000);
  page.setDefaultNavigationTimeout(240_000);
  const report = {
    revision,
    captured: new Date().toISOString(),
    browser: browser.version(),
    phase: previous ? 'restart' : 'initial',
    previous_report: previous ? path.resolve(args[restartIndex + 1]) : null,
    measurement:
      'Browser digital audio onset plus a decoded moving frame. Physical-speaker latency is unmeasured.',
    timing:
      'One browser client performance clock; status polling100ms. Readiness waits are recorded separately.',
    human_confirmation:
      'Not supplied by automation; use one concise real listening/lip-sync scenario.',
    source_files: sourceFiles,
    voices: [],
    avatars: [],
    turns: [],
    cycles: [],
    failures: [],
    checkpoints: [],
  };
  const save = () => {
    const staging = `${output}.tmp`;
    fs.writeFileSync(staging, `${JSON.stringify(report, null, 2)}\n`);
    fs.renameSync(staging, output);
  };
  const status = async () => {
    const response = await page.request.get(`${url}/status`, { timeout: 240_000 });
    if (!response.ok()) throw Error(`Status HTTP${response.status()}: ${await response.text()}`);
    return response.json();
  };
  const post = async (route, data) => {
    const response = await page.request.post(`${url}${route}`, { data, timeout: 240_000 });
    if (!response.ok()) throw Error(`${route} HTTP${response.status()}: ${await response.text()}`);
    return response.json();
  };
  const boundedPool = (value) => {
    const engine = value.speechEngine;
    if (Number.isFinite(engine?.worker_count) && engine.worker_count > 2)
      throw Error(`Speech workers exceeded two: ${engine.worker_count}`);
  };
  const checkpoint = async (label) => {
    const value = await status();
    boundedPool(value);
    report.checkpoints.push({ label, epoch: Date.now() / 1000, status: value });
    save();
    return value;
  };
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  const waitIdle = async () => {
    await expect.poll(async () => (await status()).state, { intervals: [100] }).toBe('idle');
  };
  const stop = async () => {
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await waitIdle();
  };
  const settings = async () => {
    if (await page.locator('#settings-page').isHidden())
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#settings-page')).toBeVisible();
  };
  const select = async (identity) => {
    await settings();
    await expect(page.getByLabel('Avatar', { exact: true })).toBeEnabled();
    const started = performance.now();
    await page.getByLabel('Avatar', { exact: true }).selectOption(identity);
    await expect
      .poll(
        async () => {
          const value = await status();
          boundedPool(value);
          return value.ready && value.activeAvatar === identity;
        },
        { intervals: [100] },
      )
      .toBe(true);
    const seconds = (performance.now() - started) / 1000;
    await page.getByRole('button', { name: 'Back to conversation', exact: true }).click();
    return seconds;
  };
  const submit = async (text) => {
    await expect(ask).toBeEnabled();
    await page.getByLabel('Question', { exact: true }).fill(`Fixture speech: ${text}`);
    const accepted = page.waitForResponse((r) => new URL(r.url()).pathname === '/ask');
    await ask.click();
    const response = await accepted;
    if (!response.ok()) throw Error(`Ask HTTP${response.status()}: ${await response.text()}`);
    return (await response.json()).id;
  };
  let consecutiveFailures = 0;
  const turn = async (text, label, cold = false) => {
    const result = {
      label,
      text,
      cold,
      started_epoch: Date.now() / 1000,
      valid: false,
      failed_experience: true,
    };
    report.turns.push(result);
    save();
    try {
      const id = await submit(text);
      result.run = id;
      await expect
        .poll(
          async () => {
            const value = await status();
            boundedPool(value);
            return (
              value.run?.id === id &&
              (value.run.state === 'failed' ||
                (value.state === 'idle' &&
                  value.run.events.some((event) => event.event === 'ended')))
            );
          },
          { intervals: [100] },
        )
        .toBe(true);
      result.status = await status();
      const run = result.status.run;
      const event = (kind) => run.events.find((item) => item.event === kind);
      const origin = event('submit-action')?.clientMilliseconds;
      const audio = event('digital-audio-onset')?.clientMilliseconds;
      const moving = event('moving-video')?.clientMilliseconds;
      result.expected_voice = result.status.avatars.find((avatar) => avatar.id === run.pair)?.voice;
      const segments = run.events.filter((item) => item.event === 'tts-segment');
      result.correct_voice =
        run.pair === result.status.activeAvatar &&
        !!result.expected_voice &&
        (['zira', 'hazel'].includes(result.expected_voice) ||
          (segments.length > 0 &&
            segments.every((item) => item.engine_metrics?.reference_id === result.expected_voice)));
      result.valid =
        [origin, audio, moving].every(Number.isFinite) &&
        run.state === 'complete' &&
        !!event('ended') &&
        !event('autoplay-blocked') &&
        !event('manual-play') &&
        run.answer === text &&
        result.correct_voice;
      result.first_speech_seconds = result.valid ? (Math.max(audio, moving) - origin) / 1000 : null;
      result.first_pcm_seconds = event('tts-segment')?.seconds ?? null;
      result.total_seconds = event('ended')?.seconds ?? null;
      const playing = event('playing')?.clientMilliseconds;
      result.stalls = run.events.filter(
        (item) => ['waiting', 'stalled'].includes(item.event) && item.clientMilliseconds > playing,
      ).length;
      result.audio_seconds = (event('tts-complete')?.samples || 0) / 16000;
      result.meets_five_seconds = result.valid && result.first_speech_seconds <= 5;
      result.failed_experience = !result.valid || result.first_speech_seconds >= 10;
      if (!result.valid)
        result.error =
          run.error || 'Missing complete normal-provider digital onset/ending evidence';
    } catch (error) {
      result.error = String(error);
      try {
        await stop();
      } catch (cleanupError) {
        result.stop_error = String(cleanupError);
      }
    }
    result.finished_epoch = Date.now() / 1000;
    consecutiveFailures = result.valid ? 0 : consecutiveFailures + 1;
    save();
    if (consecutiveFailures >= 3)
      throw Error('Three consecutive failed turns: retain evidence and reassess');
    return result;
  };
  const readiness = async () => {
    const began = performance.now();
    await expect
      .poll(
        async () => {
          const value = await status();
          boundedPool(value);
          return value.speechEngine?.ready_workers === 2;
        },
        { intervals: [100] },
      )
      .toBe(true);
    return (performance.now() - began) / 1000;
  };
  const clone = async (speaker) => {
    const reference = path.join(ROOT, `docs/runtime/chatterbox/reference-${speaker}-10s.wav`);
    const copy = path.join(temporary, `licensed-${speaker}.wav`);
    fs.copyFileSync(reference, copy);
    const name = `Native ${speaker} ${randomUUID().slice(0, 8)}`;
    await settings();
    await page.getByRole('button', { name: 'Voices', exact: true }).click();
    await page.getByRole('button', { name: 'Clone voice', exact: true }).click();
    await page.getByLabel('Voice name', { exact: true }).fill(name);
    await page.getByLabel('Recording', { exact: true }).setInputFiles(copy);
    await page.locator('#clone-permission').check();
    const began = performance.now();
    const prepared = page.waitForResponse((r) => new URL(r.url()).pathname === '/voices/import');
    await page.getByRole('button', { name: 'Preview', exact: true }).click();
    const imported = await prepared;
    if (!imported.ok()) throw Error(await imported.text());
    const candidate = await imported.json();
    await expect
      .poll(
        async () => {
          const value = await status();
          if (value.voiceLibrary.state === 'failed') throw Error(value.voiceLibrary.error);
          return value.voiceLibrary.previewReady;
        },
        { intervals: [100] },
      )
      .toBe(true);
    const preview = {
      speaker,
      name,
      candidate,
      preparation_seconds: (performance.now() - began) / 1000,
    };
    await expect(page.locator('#clone-audio')).toBeVisible();
    await page.getByRole('button', { name: 'Stop preview', exact: true }).click();
    await page.getByRole('button', { name: 'Preview', exact: true }).click();
    await expect
      .poll(() => page.locator('#clone-audio').evaluate((audio) => audio.ended), {
        intervals: [100],
      })
      .toBe(true);
    preview.played_complete = true;
    const audioUrl = await page.locator('#clone-audio').getAttribute('src');
    const audioResponse = await page.request.get(new URL(audioUrl, url).href, { timeout: 240_000 });
    if (!audioResponse.ok()) throw Error('Native preview audio became unavailable before save');
    const previewFile = `${output}.preview-${speaker}.wav`;
    fs.writeFileSync(previewFile, await audioResponse.body());
    preview.preview_file = previewFile;
    const saved = page.waitForResponse((r) => new URL(r.url()).pathname === '/voices/save');
    await page.getByRole('button', { name: 'Save voice', exact: true }).click();
    const response = await saved;
    if (!response.ok()) throw Error(await response.text());
    const record = {
      ...preview,
      ...(await response.json()),
      source_copy: copy,
      source_copy_removed: false,
    };
    report.voices.push(record);
    fs.unlinkSync(copy);
    record.source_copy_removed = !fs.existsSync(copy);
    await expect(page.locator('#clone-form')).toBeHidden();
    await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
    save();
    return record;
  };
  const avatar = async (voice, suffix) => {
    await settings();
    await page.getByRole('button', { name: 'Create avatar', exact: true }).click();
    const name = `Release ${suffix} ${randomUUID().slice(0, 8)}`;
    await page.getByLabel('Avatar name', { exact: true }).fill(name);
    await page
      .getByLabel('Portrait image', { exact: true })
      .setInputFiles(path.join(ROOT, '.runtime/demo-inputs/portrait.jpg'));
    await page.getByLabel('Voice', { exact: true }).selectOption(voice.id);
    const saved = page.waitForResponse((r) => new URL(r.url()).pathname === '/avatars');
    await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
    const response = await saved;
    if (!response.ok()) throw Error(await response.text());
    const result = { ...(await response.json()), voice: voice.id };
    report.avatars.push(result);
    await expect(page.locator('#avatar-editor')).toBeHidden();
    save();
    return result;
  };
  const inUseDeletion = async (voice) => {
    await settings();
    await page.getByRole('button', { name: 'Voices', exact: true }).click();
    const accepted = page.waitForResponse((r) => new URL(r.url()).pathname === '/voices/delete');
    await page.getByRole('button', { name: `Delete ${voice.name}`, exact: true }).click();
    const response = await accepted;
    const result = {
      action: 'in-use-deletion',
      status: response.status(),
      body: await response.json(),
    };
    report.checkpoints.push(result);
    save();
    if (response.ok() || !String(result.body.error).includes('used by'))
      throw Error('Deleting a shared voice was not blocked clearly');
    await page.getByRole('button', { name: 'Back to Settings', exact: true }).click();
  };
  try {
    await page.goto(url);
    await expect(ask).toBeEnabled();
    report.initial = await checkpoint('initial');
    if (
      !report.initial.conversationEnabled ||
      !report.initial.fixtureProvider ||
      !report.initial.diagnostics ||
      report.initial.experimental?.enabled
    )
      throw Error(
        'An explicit no-cost NORMAL diagnostic candidate is required; experimental harness refused',
      );
    if (!report.initial.voiceLibrary?.readiness.available)
      throw Error(
        report.initial.voiceLibrary?.readiness.error || 'Candidate engine is unavailable',
      );
    if (previous) {
      report.voices = previous.voices;
      report.avatars = previous.avatars;
      if (
        report.voices.length < 2 ||
        report.avatars.length < 3 ||
        report.voices.some(
          (voice) => !voice.source_copy_removed || fs.existsSync(voice.source_copy),
        )
      )
        throw Error(
          'Restart phase requires two saved voices, three avatars and removed task source copies',
        );
      for (const record of report.voices) {
        if (!report.initial.voices.some((voice) => voice.id === record.id && voice.available))
          throw Error(`Saved voice ${record.id} did not survive restart`);
      }
      for (const record of report.avatars) {
        if (
          !report.initial.avatars.some(
            (item) => item.id === record.id && item.voice === record.voice,
          )
        )
          throw Error(`Saved avatar ${record.id} changed on restart`);
        const seconds = await select(record.id);
        report.checkpoints.push({
          action: 'restart-selection',
          avatar: record.id,
          preparation_seconds: seconds,
        });
        await turn(TEXTS[0], `restart-${record.id}`);
      }
      await inUseDeletion(report.voices[0]);
    } else {
      const first = await clone('1089');
      const second = await clone('121');
      const a = await avatar(first, 'shared-a');
      const b = await avatar(first, 'shared-b');
      const c = await avatar(second, 'other-reference');
      await inUseDeletion(first);
      report.cold_preparation_seconds = await select(a.id);
      await turn(TEXTS[1], 'cold-first-turn', true);
      for (const [index, text] of TEXTS.entries()) await turn(text, `warm-${index + 1}`);
      const actions = [
        'stop-synthesis',
        'stop-playback',
        'reset',
        'crash',
        'shared-switch',
        'reference-switch',
        'stop-synthesis',
        'reset',
        'crash',
        'zira-switch',
        'hazel-switch',
        'reference-switch',
      ];
      for (const [index, action] of actions.entries()) {
        const cycle = { action, index: index + 1, started_epoch: Date.now() / 1000, valid: false };
        report.cycles.push(cycle);
        save();
        try {
          const before = await status();
          cycle.before = before;
          if (action.includes('switch')) {
            const target =
              action === 'shared-switch'
                ? b.id
                : action === 'zira-switch'
                  ? 'jfk-zira'
                  : action === 'hazel-switch'
                    ? 'hopper-hazel'
                    : before.activeAvatar === c.id
                      ? a.id
                      : c.id;
            cycle.preparation_seconds = await select(target);
            cycle.replacement = await turn(
              TEXTS[index % TEXTS.length],
              `cycle-${index + 1}-${action}`,
            );
            if (target === 'jfk-zira' || target === 'hopper-hazel') {
              cycle.return_preparation_seconds = await select(a.id);
              cycle.return_speech = await turn(TEXTS[0], `cycle-${index + 1}-return-clone`);
            }
          } else {
            cycle.readiness_wait_seconds = await readiness();
            if (action === 'crash' || action === 'stop-synthesis')
              await post('/voices/diagnostic', {
                session: before.session,
                fault: action === 'crash' ? 'crash' : 'delay',
              });
            const old = await submit(TEXTS[3]);
            cycle.obsolete_run = old;
            if (action === 'crash') {
              await expect
                .poll(async () => (await status()).run?.state, { intervals: [50] })
                .toBe('failed');
              await waitIdle();
              cycle.intentional_failure = await status();
            } else {
              await expect
                .poll(
                  async () =>
                    (await status()).run?.events.some(
                      (event) =>
                        event.event === (action === 'stop-playback' ? 'playing' : 'tts-start'),
                    ),
                  { intervals: [50] },
                )
                .toBe(true);
              const began = performance.now();
              await page
                .getByRole('button', {
                  name: action === 'reset' ? 'New conversation' : 'Stop',
                  exact: true,
                })
                .click();
              await waitIdle();
              cycle.cancellation_seconds = (performance.now() - began) / 1000;
              const stale = await page.request.get(`${url}/segment?run=${old}&index=0`);
              cycle.obsolete_http_status = stale.status();
              if (stale.status() !== 410) throw Error('Obsolete media remained accessible');
              if (cycle.cancellation_seconds > 1) throw Error('Cancellation exceeded the1s target');
            }
            cycle.replacement = await turn(TEXTS[2], `cycle-${index + 1}-replacement`);
          }
          cycle.after = await status();
          boundedPool(cycle.after);
          cycle.valid =
            !!cycle.replacement?.valid &&
            !!cycle.replacement?.meets_five_seconds &&
            (!cycle.return_speech || cycle.return_speech.meets_five_seconds);
          if (!cycle.valid)
            cycle.error = 'Replacement/reference-switch speech failed the5s digital target';
        } catch (error) {
          cycle.error = String(error);
          report.failures.push({ action, error: String(error) });
          try {
            await stop();
          } catch {
            /* Retain original failure; final shutdown is externally owned. */
          }
          if (consecutiveFailures >= 3) throw error;
        }
        cycle.finished_epoch = Date.now() / 1000;
        save();
        const last = report.cycles.slice(-3);
        if (last.length === 3 && last.every((item) => !item.valid))
          throw Error('Three consecutive failed cycles: retain evidence and reassess');
      }
    }
    report.final = await checkpoint('final');
    report.summary = {
      warm_onset_seconds: distribution(
        report.turns
          .filter((item) => item.label.startsWith('warm-'))
          .map((item) => item.first_speech_seconds),
      ),
      warm_failures: report.turns.filter(
        (item) => item.label.startsWith('warm-') && !item.meets_five_seconds,
      ).length,
      cycles_passed: report.cycles.filter((item) => item.valid).length,
      cycles_failed: report.cycles.filter((item) => !item.valid).length,
      failed_experiences: report.turns.filter((item) => item.failed_experience).length,
      stalls: report.turns.reduce((sum, item) => sum + (item.stalls || 0), 0),
    };
    report.automated_pass =
      report.turns.every(
        (item) => item.valid && item.stalls === 0 && (item.cold || item.meets_five_seconds),
      ) &&
      report.cycles.every((item) => item.valid) &&
      report.failures.length === 0;
    if (!report.automated_pass) process.exitCode = 1;
  } catch (error) {
    report.fatal_error = String(error);
    report.automated_pass = false;
    process.exitCode = 1;
  } finally {
    report.finished = new Date().toISOString();
    report.wall_limit_expired = expired;
    save();
    clearTimeout(limit);
    await browser.close().catch((error) => {
      report.browser_close_error = String(error);
      process.exitCode = 1;
    });
    const resolved = fs.realpathSync(temporary);
    if (
      path.dirname(resolved) !== fs.realpathSync(path.dirname(output)) ||
      !path.basename(resolved).startsWith('voice-release-inputs-')
    ) {
      report.cleanup_error = 'Unsafe task input cleanup path; retained directory for inspection';
      process.exitCode = 1;
    } else {
      fs.rmSync(resolved, { recursive: true });
    }
    save();
  }
  console.log(
    JSON.stringify({
      output,
      pass: report.automated_pass,
      summary: report.summary,
      error: report.fatal_error,
    }),
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
