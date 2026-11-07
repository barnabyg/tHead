// Native fixture evidence only: never dispatches paid requests.
const { chromium, expect } = require('@playwright/test');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

async function main() {
  const output = process.argv[2];
  if (!output || fs.existsSync(output)) throw Error('Supply a new evidence JSON path');
  const browser = await chromium.launch({ headless: true });
  const limit = setTimeout(() => browser.close(), 30 * 60 * 1000);
  const page = await browser.newPage();
  page.setDefaultTimeout(180_000);
  const snapshots = [
    {
      label: 'configuration',
      source: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      browser: browser.version(),
    },
  ];
  const status = async () => (await page.request.get('http://127.0.0.1:8765/status')).json();
  const save = () => fs.writeFileSync(output, `${JSON.stringify(snapshots, null, 2)}\n`);
  const capture = async (label) => {
    snapshots.push({ label, status: await status() });
    save();
  };
  try {
    await page.goto('http://127.0.0.1:8765');
    const ask = page.getByRole('button', { name: 'Ask', exact: true });
    const stop = page.getByRole('button', { name: 'Stop', exact: true });
    const reset = page.getByRole('button', { name: 'New conversation' });
    const fault = page.getByLabel('Diagnostic fault');
    const submit = async () => {
      const accepted = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === '/ask' && response.request().method() === 'POST',
      );
      await ask.click();
      const response = await accepted;
      if (!response.ok()) throw Error(`Submit rejected: ${response.status()}`);
      return (await response.json()).id;
    };
    await expect(ask).toBeEnabled({ timeout: 180_000 });
    if (!(await status()).fixtureProvider) throw Error('Fixture provider required');
    await capture('initial');
    const successful = async (label) => {
      await fault.selectOption('');
      await page.getByLabel('Question', { exact: true }).fill(label);
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      const id = await submit();
      await expect(page.locator('#status')).toHaveText('Playback ended', { timeout: 180_000 });
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      expect((await status()).run.id).toBe(id);
      await capture(label);
    };
    for (const [probe, event] of [
      ['llm-connect', 'llm-connect'],
      ['llm-delay', 'llm-first-text'],
      ['tts-delay', 'tts-start'],
      ['long', 'inference-start'],
      ['buffer-delay', 'buffer-delay'],
      ['long', 'playing'],
    ]) {
      await fault.selectOption(probe);
      const id = await submit();
      await expect
        .poll(
          async () =>
            (await status()).run.id === id &&
            (await status()).run.events.some((e) => e.event === event),
          {
            timeout: 180_000,
          },
        )
        .toBe(true);
      if (event === 'playing') {
        await page.waitForFunction(() => document.querySelector('#video').currentTime > 1);
        await expect
          .poll(async () =>
            (await status()).run.events.some((e) => e.event === 'digital-audio-onset'),
          )
          .toBe(true);
      }
      await capture(`before-stop-${probe}-${event}`);
      await stop.click();
      await stop.click();
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      // Polling continues until the separate digital-silence callback arrives when applicable.
      if (event === 'playing')
        await expect
          .poll(
            async () =>
              (await status()).run.events.some(
                (e) => e.event === 'digital-silence' && e.status === 'observed',
              ),
            { timeout: 30_000 },
          )
          .toBe(true);
      await capture(`released-${probe}-${event}`);
      await successful(`Replacement after ${probe}-${event}`);
    }
    await fault.selectOption('tts-delay');
    const resetId = await submit();
    await expect
      .poll(
        async () =>
          (await status()).run.id === resetId &&
          (await status()).run.events.some((e) => e.event === 'tts-start'),
      )
      .toBe(true);
    await reset.click();
    await expect(page.locator('#transcript')).toBeEmpty();
    await successful('Fresh topic after busy reset');
    for (let repeat = 0; repeat < 2; repeat++) {
      for (const probe of ['llm', 'missing-completion', 'tts', 'media']) {
        await fault.selectOption(probe);
        const id = await submit();
        await expect
          .poll(async () => ((await status()).run.id === id ? (await status()).run.state : null), {
            timeout: 180_000,
          })
          .toBe('failed');
        await expect(ask).toBeEnabled({ timeout: 180_000 });
        await capture(`failure-${probe}-${repeat}`);
        await successful(`Recovery after ${probe}-${repeat}`);
      }
    }
  } catch (error) {
    snapshots.push({ error: String(error) });
    save();
    throw error;
  } finally {
    clearTimeout(limit);
    await browser.close();
  }
}
main().catch((error) => {
  process.stderr.write(`${error}\n`);
  process.exitCode = 1;
});
