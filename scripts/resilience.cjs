// Native fixture evidence only: never dispatches paid requests.
const { chromium, expect } = require('@playwright/test');
const fs = require('node:fs');

async function main() {
  const output = process.argv[2];
  if (!output || fs.existsSync(output)) throw Error('Supply a new evidence JSON path');
  const browser = await chromium.launch({ headless: true });
  const limit = setTimeout(() => browser.close(), 30 * 60 * 1000);
  const page = await browser.newPage();
  page.setDefaultTimeout(180_000);
  const snapshots = [];
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
    await expect(ask).toBeEnabled({ timeout: 180_000 });
    if (!(await status()).fixtureProvider) throw Error('Fixture provider required');
    await capture('initial');
    const successful = async (label) => {
      await fault.selectOption('');
      await page.getByLabel('Question', { exact: true }).fill(label);
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      await ask.click();
      await expect(page.locator('#status')).toHaveText('Playback ended', { timeout: 180_000 });
      await expect(ask).toBeEnabled({ timeout: 180_000 });
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
      await ask.click();
      await expect
        .poll(async () => (await status()).run.events.some((e) => e.event === event), {
          timeout: 180_000,
        })
        .toBe(true);
      await capture(`before-stop-${probe}-${event}`);
      await stop.click();
      await stop.click();
      await expect(ask).toBeEnabled({ timeout: 180_000 });
      // Polling continues until the separate digital-silence callback arrives when applicable.
      if (event === 'playing')
        await expect
          .poll(
            async () => (await status()).run.events.some((e) => e.event === 'digital-silence'),
            { timeout: 30_000 },
          )
          .toBe(true);
      await capture(`released-${probe}-${event}`);
      await successful(`Replacement after ${probe}-${event}`);
    }
    await fault.selectOption('tts-delay');
    await ask.click();
    await expect
      .poll(async () => (await status()).run.events.some((e) => e.event === 'tts-start'))
      .toBe(true);
    await reset.click();
    await expect(page.locator('#transcript')).toBeEmpty();
    await successful('Fresh topic after busy reset');
    for (let repeat = 0; repeat < 2; repeat++) {
      for (const probe of ['llm', 'missing-completion', 'tts', 'media']) {
        await fault.selectOption(probe);
        await ask.click();
        await expect
          .poll(async () => (await status()).run.state, { timeout: 180_000 })
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
