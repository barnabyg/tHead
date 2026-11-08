// Explicit no-cost native evidence capture. Shared GPU measurements run serially.
const { chromium, expect: baseExpect } = require('@playwright/test');
// A cold reference worker is measured separately from its first-audio latency.
// Give readiness/assertions the same generous bound as browser operations.
const expect = baseExpect.configure({ timeout: 240_000 });
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const questions = [
  'short-1',
  'multi-1',
  'short-2',
  'multi-2',
  'short-3',
  'multi-1',
  'short-1',
  'multi-2',
  'short-2',
  'multi-1',
];
function summary(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  return {
    count: sorted.length,
    median: sorted.length
      ? (sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.floor(sorted.length / 2)]) / 2
      : null,
    minimum: sorted[0] ?? null,
    maximum: sorted.at(-1) ?? null,
    exploratoryP95: sorted.length ? sorted[Math.ceil(sorted.length * 0.95) - 1] : null,
    p95Method: 'nearest rank; ten warmed samples are exploratory, failures retained separately',
  };
}
async function main() {
  const output = process.argv[2];
  if (!output || fs.existsSync(output)) throw Error('Supply a new evidence JSON path');
  const url = process.env.THEAD_URL || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({ headless: true });
  const limit = setTimeout(() => browser.close(), 3600_000);
  const page = await browser.newPage();
  page.setDefaultTimeout(240_000);
  const report = {
    revision: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    captured: new Date().toISOString(),
    browser: browser.version(),
    measurement: 'digital audio onset plus decoded moving frame; not physical-speaker latency',
    timing: 'client performance clock in milliseconds; status polling 100 ms',
    source_files: [
      'scripts/chatterbox_app.py',
      'scripts/chatterbox_voice.py',
      'scripts/chatterbox_worker.py',
      'scripts/conversation.py',
      'scripts/speech.py',
      'scripts/streaming.py',
      'scripts/streaming.js',
      'scripts/chatterbox-benchmark.cjs',
      'chatterbox-lock.json',
    ].map((file) => ({
      path: file,
      sha256: createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
    })),
    configurations: [],
    probes: [],
  };
  const save = () => fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`);
  const status = async () => (await page.request.get(`${url}/status`)).json();
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  const reset = async () => {
    await page.getByRole('button', { name: 'New conversation', exact: true }).click();
    await expect.poll(async () => (await status()).state).toBe('idle');
    await expect(ask).toBeEnabled();
  };
  const select = async (identity) => {
    if (await page.locator('#settings-page').isHidden())
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
    const started = performance.now();
    await page.getByLabel('Avatar', { exact: true }).selectOption(identity);
    await expect
      .poll(
        async () => {
          const value = await status();
          return value.ready && value.activeAvatar === identity;
        },
        { timeout: 240_000, intervals: [100] },
      )
      .toBe(true);
    await page.getByRole('button', { name: 'Back to conversation', exact: true }).click();
    return (performance.now() - started) / 1000;
  };
  const submit = async (question) => {
    await expect(ask).toBeEnabled();
    await page.getByLabel('Question', { exact: true }).fill(question);
    const accepted = page.waitForResponse((r) => new URL(r.url()).pathname === '/ask');
    await ask.click();
    const response = await accepted;
    if (!response.ok()) throw Error(await response.text());
    return (await response.json()).id;
  };
  const turn = async (question, cold = false) => {
    const result = { question, cold, started_epoch: Date.now() / 1000 };
    try {
      const id = await submit(question);
      await expect
        .poll(
          async () => {
            const value = await status();
            return (
              value.run?.id === id &&
              (value.run.state === 'failed' ||
                (value.state === 'idle' && value.run.events.some((e) => e.event === 'ended')))
            );
          },
          { timeout: 240_000, intervals: [100] },
        )
        .toBe(true);
      result.status = await status();
      const events = result.status.run.events;
      const event = (kind) => events.find((e) => e.event === kind);
      const origin = event('submit-action')?.clientMilliseconds;
      const audio = event('digital-audio-onset')?.clientMilliseconds;
      const moving = event('moving-video')?.clientMilliseconds;
      result.valid =
        [origin, audio, moving].every(Number.isFinite) &&
        result.status.run.state === 'complete' &&
        !!event('ended') &&
        !event('autoplay-blocked') &&
        !event('manual-play');
      result.first_speech_seconds = result.valid ? (Math.max(audio, moving) - origin) / 1000 : null;
      result.first_pcm_seconds = event('tts-segment')?.seconds ?? null;
      result.total_seconds = event('ended')?.seconds ?? null;
      const playing = event('playing')?.clientMilliseconds;
      result.stalls = events.filter(
        (e) => ['waiting', 'stalled'].includes(e.event) && e.clientMilliseconds > playing,
      ).length;
      const tts = events.filter((e) => e.event === 'tts-segment');
      result.tts_seconds = tts.reduce((sum, e) => sum + e.preparation_seconds, 0);
      result.audio_seconds = (event('tts-complete')?.samples || 0) / 16000;
      result.tts_rtf = result.audio_seconds ? result.tts_seconds / result.audio_seconds : null;
      result.meets_five_seconds = result.valid && result.first_speech_seconds <= 5;
      result.failed_experience = !result.valid || result.first_speech_seconds >= 10;
      if (!result.valid)
        result.error = result.status.run.error || 'No complete digital onset evidence';
    } catch (error) {
      result.error = String(error);
      result.valid = false;
      const value = await status();
      if (value.run && value.state !== 'idle') {
        await page.getByRole('button', { name: 'Stop', exact: true }).click();
        await expect.poll(async () => (await status()).state).toBe('idle');
      }
    }
    result.finished_epoch = Date.now() / 1000;
    return result;
  };
  try {
    const startupDeadline = Date.now() + 240_000;
    while (true) {
      try {
        await page.goto(url);
        break;
      } catch (error) {
        if (Date.now() > startupDeadline) throw error;
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    }
    await expect(ask).toBeEnabled();
    report.initial = await status();
    if (!report.initial.fixtureProvider || !report.initial.experimental?.enabled)
      throw Error('Explicit no-cost experimental application required');
    const identities = process.argv[3]
      ? [process.argv[3]]
      : ['jfk-zira', 'chatterbox-nano-1089', 'chatterbox-nano-121'];
    for (const identity of process.argv.includes('--probes-only') ? [] : identities) {
      await reset();
      const preparation = await select(identity);
      const configuration = {
        identity,
        preparation_seconds: preparation,
        readiness: await status(),
        turns: [],
      };
      report.configurations.push(configuration);
      configuration.turns.push(await turn('multi-1', true));
      save();
      let errors = 0;
      for (const question of process.argv.includes('--smoke-only') ? [] : questions) {
        const measured = await turn(question);
        configuration.turns.push(measured);
        errors = measured.valid ? 0 : errors + 1;
        save();
        console.log(
          identity,
          configuration.turns.length - 1,
          measured.first_speech_seconds ?? measured.error,
        );
        if (errors >= 3) {
          configuration.stopped = 'Three consecutive failed turns; reassess instead of repeating';
          break;
        }
      }
      const warmed = configuration.turns.filter((value) => !value.cold);
      configuration.summary = {
        first_speech: summary(warmed.map((value) => value.first_speech_seconds)),
        first_pcm: summary(warmed.map((value) => value.first_pcm_seconds)),
        total_turn: summary(warmed.map((value) => value.total_seconds)),
        tts_rtf: summary(warmed.map((value) => value.tts_rtf)),
        valid: warmed.filter((value) => value.valid).length,
        above_five_seconds: warmed.filter((value) => !value.meets_five_seconds).length,
        failed_experiences: warmed.filter((value) => value.failed_experience).length,
        stalls: warmed.reduce((sum, value) => sum + (value.stalls || 0), 0),
      };
      save();
    }
    if (process.argv[3] && !process.argv.includes('--probes')) return;
    await reset();
    const state = path.resolve(
      '.runtime',
      report.initial.experimental.configuration === 'cuda'
        ? 'chatterbox-eval-gpu'
        : 'chatterbox-eval',
    );
    for (const [kind, relative] of [
      ['missing-reference', 'references/librispeech-1089-10s.wav'],
      ['missing-model', 'model/ve.safetensors'],
    ]) {
      await select('jfk-zira');
      const asset = path.join(state, relative);
      const backup = `${asset}.issue54-probe`;
      if (!fs.existsSync(asset) || fs.existsSync(backup))
        throw Error('Asset probe requires an intact pinned asset and no backup');
      const digest = createHash('sha256').update(fs.readFileSync(asset)).digest('hex');
      fs.renameSync(asset, backup);
      try {
        await page.getByRole('button', { name: 'Settings', exact: true }).click();
        await page.getByLabel('Avatar', { exact: true }).selectOption('chatterbox-nano-1089');
        await expect
          .poll(async () => (await status()).error, { intervals: [100] })
          .toContain(kind === 'missing-reference' ? 'Reference' : 'model');
        const failed = await status();
        if (failed.ready || failed.experimental.worker_alive)
          throw Error('Missing asset silently substituted or retained worker');
        report.probes.push({ action: kind, failed, asset_sha256: digest });
        save();
      } finally {
        fs.renameSync(backup, asset);
      }
      if (createHash('sha256').update(fs.readFileSync(asset)).digest('hex') !== digest)
        throw Error('Restored asset changed');
      await select('jfk-zira');
      await select('chatterbox-nano-1089');
      report.probes.at(-1).recovery = await turn('short-1');
      save();
    }
    await reset();
    await select('chatterbox-nano-1089');
    for (const action of ['stop-synthesis', 'reset-synthesis', 'stop-playback']) {
      const id = await submit('multi-2');
      await expect
        .poll(
          async () =>
            (await status()).run?.events.some(
              (e) => e.event === (action === 'stop-playback' ? 'playing' : 'tts-start'),
            ),
          { intervals: [50] },
        )
        .toBe(true);
      const before = await status();
      const began = performance.now();
      await page
        .getByRole('button', {
          name: action === 'reset-synthesis' ? 'New conversation' : 'Stop',
          exact: true,
        })
        .click();
      await expect.poll(async () => (await status()).state, { intervals: [50] }).toBe('idle');
      const stopped = await status();
      const obsolete = await page.request.get(`${url}/segment?run=${id}&index=0`);
      report.probes.push({
        action,
        seconds_to_idle: (performance.now() - began) / 1000,
        obsolete_status: obsolete.status(),
        before,
        stopped,
        recovery: await turn('short-2'),
      });
      save();
      await reset();
    }
    const beforeCrash = await status();
    await page.request.post(`${url}/experimental`, {
      data: { session: beforeCrash.session, fault: 'crash' },
    });
    const crashed = await turn('short-1');
    await reset();
    report.probes.push({ action: 'worker-crash', crashed, recovery: await turn('short-1') });
    save();
    for (const identity of [
      'jfk-zira',
      'chatterbox-nano-121',
      'hopper-hazel',
      'chatterbox-nano-1089',
    ]) {
      await reset();
      const seconds = await select(identity);
      report.probes.push({
        action: 'switch',
        identity,
        seconds,
        status: await status(),
        turn: await turn('short-1'),
      });
      save();
    }
    report.final = await status();
    save();
  } finally {
    clearTimeout(limit);
    await browser.close();
    save();
  }
}
main().catch((error) => {
  console.error(String(error));
  process.exitCode = 1;
});
