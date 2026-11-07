// Explicit bounded Phase 6 evidence capture. --real opts into <=18 paid turns, <=USD 0.05.
const { chromium, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const { createHash } = require('node:crypto');

const prompts = [
  'What is a black hole?',
  'How do we detect one?',
  'Why do seasons happen?',
  'What changes in the Southern Hemisphere?',
  'How does a rainbow form?',
  'What conditions do we need to see one?',
  'What causes ocean tides?',
  'Why are there usually two high tides each day?',
  'How do solar panels produce electricity?',
  'Do they still work on cloudy days?',
];
const ids = ['jfk-zira', 'hopper-hazel'];
function summary(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    count: sorted.length,
    median: sorted.length
      ? (sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.floor(sorted.length / 2)]) / 2
      : null,
    p95: sorted.length ? sorted[Math.ceil(sorted.length * 0.95) - 1] : null,
    minimum: sorted[0] ?? null,
    maximum: sorted.at(-1) ?? null,
  };
}
async function main() {
  const output = process.argv[2];
  const real = process.argv.includes('--real');
  if (!output || fs.existsSync(output)) throw Error('Supply a new evidence JSON path');
  const url = process.env.THEAD_URL || 'http://127.0.0.1:8765';
  const browser = await chromium.launch({ headless: true });
  const limit = setTimeout(() => browser.close(), 30 * 60 * 1000);
  const page = await browser.newPage();
  page.setDefaultTimeout(180_000);
  const report = {
    source: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    trackedDiff: execFileSync('git', ['diff', 'HEAD'], { encoding: 'utf8' }),
    runner: { sha256: createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') },
    captured: new Date().toISOString(),
    browser: browser.version(),
    real,
    requestLimit: 18,
    maximumAdditionalReservationUsd: 0.05,
    measurement:
      'browser digital audio and advancing video; no listening or physical-speaker claim',
    turns: [],
    switches: [],
    probes: [],
  };
  const save = () => fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`);
  const status = async () => (await page.request.get(`${url}/status`)).json();
  const idle = async () =>
    expect.poll(async () => (await status()).state, { timeout: 180_000 }).toBe('idle');
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  const pair = page.getByLabel('Avatar and voice', { exact: true });
  let requests = 0;
  try {
    await page.goto(url);
    await expect(ask).toBeEnabled({ timeout: 180_000 });
    report.initial = await status();
    if (report.initial.fixtureProvider === real || report.initial.model !== 'gpt-6-luna')
      throw Error('Provider mode/model does not match declared experiment');
    const submit = async (question) => {
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      const before = await status();
      if (
        ++requests > 18 ||
        before.budget.estimated_usd - report.initial.budget.estimated_usd > 0.048
      )
        throw Error('Experiment request/cost bound reached');
      await page.getByLabel('Question', { exact: true }).fill(question);
      const accepted = page.waitForResponse((r) => new URL(r.url()).pathname === '/ask');
      await ask.click();
      const response = await accepted;
      if (!response.ok()) throw Error(`Submit rejected: ${await response.text()}`);
      return (await response.json()).id;
    };
    const complete = async (question, warmup = false) => {
      const turn = { question, warmup };
      report.turns.push(turn);
      try {
        const id = await submit(question);
        await expect
          .poll(
            async () => {
              const s = await status();
              return (
                s.run?.id === id &&
                (s.run.state === 'failed' ||
                  (s.state === 'idle' && s.run.events.some((e) => e.event === 'ended')))
              );
            },
            { timeout: 180_000 },
          )
          .toBe(true);
        turn.status = await status();
        const event = (name) => turn.status.run.events.find((e) => e.event === name);
        const origin = event('submit-action')?.clientMilliseconds;
        const audio = event('digital-audio-onset')?.clientMilliseconds;
        const moving = event('moving-video')?.clientMilliseconds;
        turn.valid =
          [origin, audio, moving].every(Number.isFinite) &&
          turn.status.run.state === 'complete' &&
          !!event('ended') &&
          !event('autoplay-blocked') &&
          !event('manual-play');
        turn.seconds = turn.valid ? (Math.max(audio, moving) - origin) / 1000 : null;
        turn.stalls = turn.status.run.events.filter(
          (e) =>
            ['waiting', 'stalled'].includes(e.event) &&
            e.clientMilliseconds > event('playing')?.clientMilliseconds,
        ).length;
        turn.pair = turn.status.run.pair;
        turn.resources = event('resources-released');
        if (!turn.valid) throw Error('Turn did not establish complete digital playback');
      } catch (error) {
        turn.error = String(error);
        throw error;
      } finally {
        save();
        process.stdout.write(
          `Turn ${report.turns.length}: ${turn.pair} ${turn.seconds ?? turn.error}\n`,
        );
      }
    };
    const select = async (id, fault = '') => {
      await idle();
      await expect(pair).toBeEnabled();
      await page.getByLabel('Pair diagnostic', { exact: true }).selectOption(fault);
      const before = await status();
      const began = performance.now();
      const accepted = page.waitForResponse((r) => new URL(r.url()).pathname === '/select');
      await pair.selectOption(id);
      const response = await accepted;
      if (!response.ok()) throw Error(`Selection rejected: ${await response.text()}`);
      await expect
        .poll(
          async () => {
            const s = await status();
            return s.pairSequence > before.pairSequence && s.state === 'idle';
          },
          { timeout: 180_000 },
        )
        .toBe(true);
      const result = await status();
      report.switches.push({
        requested: id,
        fault,
        seconds: (performance.now() - began) / 1000,
        preparationSeconds: result.pairPreparationSeconds,
        active: result.activePair,
        ready: result.ready,
        error: result.error,
        tts: result.loading.tts,
      });
      expect(result.budget.estimated_usd).toBe(before.budget.estimated_usd);
      if (!fault) {
        expect(result.activePair).toBe(id);
        expect(result.ready).toBe(true);
      }
      save();
      return result;
    };
    if (process.argv.includes('--stop-only')) {
      if (real) throw Error('--stop-only requires the no-cost provider fixture');
      report.mode = 'audible-stop-and-replacement';
      for (const id of ids) {
        if ((await status()).activePair !== id) await select(id);
        await page.getByLabel('Diagnostic fault').selectOption('long');
        const run = await submit('Exercise Stop during audible moving playback.');
        await page.waitForFunction(
          () => document.querySelector('#video').currentTime > 1 && outputRms() > 0.0001,
        );
        report.probes.push({ label: `before-audible-stop-${id}`, status: await status() });
        await page.getByRole('button', { name: 'Stop', exact: true }).click();
        await expect(ask).toBeEnabled({ timeout: 180_000 });
        await expect
          .poll(
            async () =>
              (await status()).run?.events.some(
                (e) => e.event === 'digital-silence' && e.status === 'observed',
              ),
            { timeout: 30_000 },
          )
          .toBe(true);
        const stopped = await status();
        expect(stopped.run.id).toBe(run);
        expect(stopped.run.state).toBe('stopped');
        report.probes.push({ label: `after-audible-stop-${id}`, status: stopped });
        await expect(page.locator('#video')).not.toHaveAttribute('src');
        await page.getByLabel('Diagnostic fault').selectOption('');
        await complete('Replacement after audible Stop');
      }
      report.final = await status();
      report.elapsedSeconds = (Date.now() - Date.parse(report.captured)) / 1000;
      report.complete = true;
      return;
    }
    // Warm both pairs explicitly before measuring repeated switches/turns.
    if (report.initial.activePair !== ids[0]) await select(ids[0]);
    await complete('What is gravity?', true);
    await select(ids[1]);
    await complete('What is gravity?', true);
    await page.getByRole('button', { name: 'New conversation' }).click();
    for (let index = 0; index < prompts.length; index++) {
      await select(ids[index % 2]);
      await complete(prompts[index]);
    }
    // Stop after synthesis starts, replace, then reset another active response.
    for (const reset of [false, true]) {
      const id = await submit('Explain how a black hole affects nearby stars in four sentences.');
      await expect
        .poll(
          async () => {
            const s = await status();
            return s.run?.id === id && s.run.events.some((e) => e.event === 'tts-start');
          },
          { timeout: 180_000 },
        )
        .toBe(true);
      await page
        .getByRole('button', { name: reset ? 'New conversation' : 'Stop', exact: true })
        .click();
      await idle();
      report.probes.push({ label: reset ? 'busy-reset' : 'stop', status: await status() });
      await complete(reset ? 'What is a rainbow?' : 'How do we detect one?');
    }
    const current = (await status()).activePair;
    const other = ids.find((id) => id !== current);
    await select(other, 'pair-prepare');
    await select(current);
    await complete('How do we detect one?');
    // Late preparation is retained across reset; pending switches are rejected.
    await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-delay');
    await expect(pair).toBeEnabled();
    await pair.selectOption(other);
    await expect.poll(async () => (await status()).state).toBe('selecting');
    await page.getByRole('button', { name: 'New conversation' }).click();
    await idle();
    report.probes.push({ label: 'reset-during-loading', status: await status() });
    expect((await status()).activePair).toBe(other);
    expect((await status()).transcript).toHaveLength(0);
    report.summary = Object.fromEntries(
      ids.map((id) => [
        id,
        summary(
          report.turns
            .slice(2, 12)
            .filter((t) => t.valid && t.pair === id)
            .map((t) => t.seconds),
        ),
      ]),
    );
    report.switchSummary = summary(
      report.switches.filter((s) => !s.fault && s.ready).map((s) => s.seconds),
    );
    report.final = await status();
    report.elapsedSeconds = (Date.now() - Date.parse(report.captured)) / 1000;
    report.complete = true;
  } catch (error) {
    report.error = String(error);
    throw error;
  } finally {
    clearTimeout(limit);
    save();
    await browser.close();
  }
}
main().catch((error) => {
  process.stderr.write(`${error}\n`);
  process.exitCode = 1;
});
