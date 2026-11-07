const { test, expect } = require('@playwright/test');
const { spawn } = require('node:child_process');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

test.beforeEach(async ({ page }, info) => {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'thead-browser-'));
  const python = process.env.THEAD_TEST_PYTHON || 'python';
  const child = spawn(
    python,
    ['scripts/conversation.py', '--test-backend', '--port', '0', '--output', output],
    {
      stdio: ['pipe', 'pipe', 'pipe'],
    },
  );
  info.app = child;
  info.output = output;
  const timeout = setTimeout(() => child.kill(), 180_000);
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
  // External media transport substitute: real playable synthetic colour/tone,
  // not an assertion of avatar/TTS quality. Conversation/backend remain real.
  await page.route('**/segment?*', async (route) => {
    const index = new URL(route.request().url()).searchParams.get('index');
    if (index === '0')
      await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
    else await route.fulfill({ status: 204, body: '' });
  });
  await page.goto(info.url);
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
});

test.afterEach(async ({ page }, info) => {
  try {
    await page.close();
  } finally {
    clearTimeout(info.appTimeout);
    if (info.app && info.app.exitCode === null) {
      const exited = new Promise((resolve) => info.app.once('exit', resolve));
      info.app.kill();
      await exited;
    }
    fs.rmSync(info.output, { recursive: true, force: true });
  }
});

test('complete answer, contextual follow-up, idle Stop and fresh conversation', async ({
  page,
  request,
}, info) => {
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#transcript')).toContainText('A black hole traps light.');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
    .toBe('complete');
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#transcript')).toContainText(
    'Earlier question: What is a black hole?',
  );
  const status = await (await request.get(`${info.url}/status`)).json();
  const dispatched = status.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages.some((message) => message.role === 'assistant')).toBe(true);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await page.getByLabel('Question', { exact: true }).fill('A new topic');
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#transcript')).toContainText('A new topic');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(page.locator('#transcript')).not.toContainText('Earlier question');
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
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await accept;
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect
    .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
    .toBe('stopped');
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  release();
  await expect(page.locator('#transcript')).toContainText('Interrupted');
});

test('busy reset rejects late text and safe rendering keeps provider markup literal', async ({
  page,
}) => {
  await page.getByLabel('Diagnostic fault').selectOption('tts-delay');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#transcript')).toContainText('You: What is a black hole?');
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
  await page.getByLabel('Diagnostic fault').selectOption('markup');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
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
    await page.getByRole('button', { name: 'Ask', exact: true }).click();
    await expect
      .poll(async () => (await (await request.get(`${info.url}/status`)).json()).run.state)
      .toBe('failed');
    await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
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
  const before = (await (await request.get(`${info.url}/status`)).json()).transcript.length;
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#status')).toContainText('budget');
  const after = (await (await request.get(`${info.url}/status`)).json()).transcript.length;
  expect(after).toBe(before);
});
