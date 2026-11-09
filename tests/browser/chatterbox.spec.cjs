const { test, expect } = require('@playwright/test');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

test.beforeEach(async ({ page }, info) => {
  info.output = fs.mkdtempSync(path.join(os.tmpdir(), 'thead-clone-browser-'));
  info.app = spawn(
    process.env.THEAD_TEST_PYTHON || 'python',
    ['scripts/chatterbox_app.py', '--test-backend', '--port', '0', '--output', info.output],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );
  info.closed = new Promise((resolve) => info.app.once('close', resolve));
  info.stderr = '';
  info.app.stderr.on('data', (chunk) => {
    info.stderr = (info.stderr + chunk).slice(-4000);
  });
  info.wallLimit = setTimeout(() => kill(info.app), 300_000);
  info.url = await new Promise((resolve, reject) => {
    const deadline = setTimeout(
      () => reject(Error('Clone fixture startup exceeded 60 seconds')),
      60_000,
    );
    let text = '';
    info.app.once('exit', (code) => {
      clearTimeout(deadline);
      reject(Error(`Clone fixture exited ${code}: ${info.stderr}`));
    });
    info.app.stdout.on('data', (chunk) => {
      text = (text + chunk).slice(-20000);
      const match = text.match(/LISTEN (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(deadline);
        resolve(match[1]);
      }
    });
  });
  await page.route('**/segment?*', async (route) => {
    const response = await route.fetch();
    if (response.status() !== 200) {
      await route.fulfill({ response });
      return;
    }
    const index = new URL(route.request().url()).searchParams.get('index');
    if (index === '0')
      await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
    else await route.fulfill({ status: 204, body: '' });
  });
  await page.goto(info.url);
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
});

function kill(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32')
    execFileSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { timeout: 30_000 });
  else child.kill('SIGKILL');
}

test.afterEach(async ({ page, request }, info) => {
  clearTimeout(info.wallLimit);
  await page.close();
  try {
    await request.post(`${info.url}/shutdown`, { timeout: 10_000 });
    await Promise.race([
      info.closed,
      new Promise((_, reject) => {
        const timer = setTimeout(() => reject(Error('Clone fixture did not close')), 30_000);
        timer.unref();
      }),
    ]);
  } catch {
    kill(info.app);
    await info.closed;
  }
  const directory = fs.realpathSync(info.output);
  if (
    path.dirname(directory).toLowerCase() !== fs.realpathSync(os.tmpdir()).toLowerCase() ||
    !path.basename(directory).startsWith('thead-clone-browser-')
  )
    throw Error('Unsafe clone-fixture cleanup path');
  fs.rmSync(directory, { recursive: true });
});

async function status(request, info) {
  return (await request.get(`${info.url}/status`)).json();
}

async function select(page, request, info, identity) {
  if (await page.locator('#settings-page').isHidden())
    await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByLabel('Avatar', { exact: true }).selectOption(identity);
  await expect
    .poll(async () => {
      const value = await status(request, info);
      return value.ready && value.activeAvatar === identity;
    })
    .toBe(true);
  await page.getByRole('button', { name: 'Back to conversation', exact: true }).click();
}

test('Stop abandons experimental PCM and replacement retains the reference', async ({
  page,
  request,
}, info) => {
  await select(page, request, info, 'chatterbox-nano-1089');
  const selected = await status(request, info);
  await request.post(`${info.url}/experimental`, {
    data: { session: selected.session, fault: 'delay' },
  });
  await page.getByLabel('Question', { exact: true }).fill('short-1');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect
    .poll(async () =>
      (await status(request, info)).run?.events.some((e) => e.event === 'tts-start'),
    )
    .toBe(true);
  const old = (await status(request, info)).run.id;
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await expect.poll(async () => (await status(request, info)).experimental.worker_alive).toBe(true);
  expect((await request.get(`${info.url}/segment?run=${old}&index=0`)).status()).toBe(410);
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const replacement = await status(request, info);
  expect(replacement.run.id).not.toBe(old);
  expect(replacement.experimental.reference_id).toBe('librispeech-1089-10s');
  expect(replacement.run.pair).toBe('chatterbox-nano-1089');
});

test('worker failure, New conversation and repeated SAPI/reference switches recover explicitly', async ({
  page,
  request,
}, info) => {
  await select(page, request, info, 'chatterbox-nano-1089');
  const selected = await status(request, info);
  await request.post(`${info.url}/experimental`, {
    data: { session: selected.session, fault: 'crash' },
  });
  await page.getByLabel('Question', { exact: true }).fill('short-1');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#status')).toContainText('worker exited');
  expect((await status(request, info)).run.error).toContain('worker exited');
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  for (const identity of [
    'jfk-zira',
    'chatterbox-nano-121',
    'hopper-hazel',
    'chatterbox-nano-1089',
  ]) {
    await select(page, request, info, identity);
    await page.getByLabel('Question', { exact: true }).fill('short-1');
    await page.getByRole('button', { name: 'Ask', exact: true }).click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    expect((await status(request, info)).run.pair).toBe(identity);
  }
});
