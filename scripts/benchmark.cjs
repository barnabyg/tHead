// Explicit evidence capture: questions and answers are saved only by this command.
const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

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

async function main() {
  const output = process.argv[2];
  if (!output || fs.existsSync(output)) throw Error('Supply a new evidence JSON path');
  const browser = await chromium.launch({ headless: true });
  const wallLimit = setTimeout(() => browser.close(), 30 * 60 * 1000);
  const page = await browser.newPage();
  page.setDefaultTimeout(180_000);
  const report = {
    source: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    trackedDiff: execFileSync('git', ['diff', 'HEAD'], { encoding: 'utf8' }),
    captured: new Date().toISOString(),
    browser: browser.version(),
    measurement: 'digital audio graph and advancing video; no physical speaker or perceptual claim',
    warmupExclusions: 1,
    requestLimit: 11,
    maximumAdditionalReservationUsd: 0.05,
    turns: [],
  };
  const save = () => fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`);
  try {
    await page.goto('http://127.0.0.1:8765');
    const ask = page.getByRole('button', { name: 'Ask', exact: true });
    await ask.waitFor();
    await page.waitForFunction(() => !document.querySelector('#start').disabled);
    const initial = await (await page.request.get('http://127.0.0.1:8765/status')).json();
    if (initial.fixtureProvider || initial.configurationError || initial.model !== 'gpt-6-luna')
      throw Error('Ready real gpt-6-luna provider required for declared cost bound');
    report.readiness = initial.loading;
    report.initialBudget = initial.budget;
    // At most 8192 input and 384 output tokens per request, using current guard rates.
    // Reserve <= $0.05 for this bounded experiment; stop if accounting grows beyond it.
    await page.getByRole('button', { name: 'New conversation' }).click();
    for (const [index, question] of ['What is gravity?', ...prompts].entries()) {
      const turn = { index, question, excludedWarmup: index === 0 };
      report.turns.push(turn);
      try {
        await page.waitForFunction(() => !document.querySelector('#start').disabled);
        const before = await (await page.request.get('http://127.0.0.1:8765/status')).json();
        if (before.budget.estimated_usd - initial.budget.estimated_usd > 0.04)
          throw Error('Experiment cost bound reached');
        await page.getByLabel('Question', { exact: true }).fill(question);
        await ask.click();
        await page.waitForFunction((previous) => {
          const status = JSON.parse(document.querySelector('#report').textContent || '{}');
          return status.run && status.run.id !== previous;
        }, before.run?.id);
        await page.waitForFunction(() => {
          const status = JSON.parse(document.querySelector('#report').textContent || '{}');
          return (
            status.run &&
            (['failed', 'stopped'].includes(status.run.state) ||
              (document.querySelector('#video').ended && status.state === 'idle'))
          );
        });
        // Allow final asynchronous player telemetry to reach the server.
        await page.waitForFunction(() => {
          const status = JSON.parse(document.querySelector('#report').textContent || '{}');
          return (
            status.run?.events.some((e) => e.event === 'ended') ||
            ['failed', 'stopped'].includes(status.run?.state)
          );
        });
        turn.status = await (await page.request.get('http://127.0.0.1:8765/status')).json();
        const events = turn.status.run.events;
        const event = (name) => events.find((e) => e.event === name);
        const origin = event('submit-action')?.clientMilliseconds;
        const audio = event('digital-audio-onset')?.clientMilliseconds;
        const moving = event('moving-video')?.clientMilliseconds;
        turn.valid =
          [origin, audio, moving].every(Number.isFinite) &&
          !event('autoplay-blocked') &&
          !event('manual-play') &&
          turn.status.run.state === 'complete' &&
          !!event('ended');
        turn.seconds = turn.valid ? (Math.max(audio, moving) - origin) / 1000 : null;
        const playing = event('playing')?.clientMilliseconds;
        turn.stalls = events.filter(
          (e) => ['waiting', 'stalled'].includes(e.event) && e.clientMilliseconds > playing,
        ).length;
        turn.failedExperience = !turn.valid || turn.seconds >= 10;
      } catch (error) {
        turn.error = String(error);
        turn.failedExperience = true;
        await page.getByRole('button', { name: 'Stop', exact: true }).click();
      }
      save();
      process.stdout.write(`Turn ${index}: ${turn.seconds ?? turn.error ?? 'invalid'} seconds\n`);
    }
    const turns = report.turns.filter((t) => !t.excludedWarmup);
    const values = turns
      .filter((t) => t.valid)
      .map((t) => t.seconds)
      .sort((a, b) => a - b);
    report.summary = {
      attempts: turns.length,
      valid: values.length,
      failedExperiences: turns.filter((t) => t.failedExperience).length,
      stalls: turns.reduce((sum, t) => sum + (t.stalls || 0), 0),
      median: values.length
        ? (values[Math.floor((values.length - 1) / 2)] + values[Math.floor(values.length / 2)]) / 2
        : null,
      p95: values.length ? values[Math.ceil(values.length * 0.95) - 1] : null,
      p95Method: 'nearest rank on valid attempts; failures retained separately',
      minimum: values[0] ?? null,
      maximum: values.at(-1) ?? null,
    };
    report.finalBudget = (
      await (await page.request.get('http://127.0.0.1:8765/status')).json()
    ).budget;
    save();
  } finally {
    clearTimeout(wallLimit);
    save();
    await browser.close();
  }
}
main().catch((error) => {
  process.stderr.write(`${error}\n`);
  process.exitCode = 1;
});
