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
  const timeout = setTimeout(() => child.kill(), 960_000);
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

test('bounded 100-turn session trims context, rejects turn 101 and resets', async ({
  page,
  request,
}, info) => {
  test.setTimeout(900_000);
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  for (let index = 0; index < 100; index++) {
    await expect(ask).toBeEnabled();
    const question = `Turn ${index}: ${'context '.repeat(120)}`;
    await page.getByLabel('Question', { exact: true }).fill(question);
    await ask.click();
    await expect(page.locator('#transcript')).toContainText(`You: Turn ${index}:`);
    await expect(page.locator('#status')).toHaveText('Playback ended');
  }
  await expect(ask).toBeEnabled();
  await expect(page.locator('#transcript')).toContainText('exchanges omitted');
  const before = await (await request.get(`${info.url}/status`)).json();
  expect(before.transcript).toHaveLength(100);
  await page.getByLabel('Question', { exact: true }).fill('This turn must be rejected');
  await ask.click();
  await expect(page.locator('#status')).toContainText('100 turns');
  const rejected = await (await request.get(`${info.url}/status`)).json();
  expect(rejected.transcript).toHaveLength(100);
  expect(rejected.budget.estimated_usd).toBe(before.budget.estimated_usd);
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(ask).toBeEnabled();
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const fresh = await (await request.get(`${info.url}/status`)).json();
  expect(fresh.transcript).toHaveLength(1);
  const dispatched = fresh.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages).toHaveLength(1);
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

test('switch both directions between turns, reject busy selection, retain context after Stop and reset', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  const pair = page.getByLabel('Avatar and voice', { exact: true });
  await expect(pair).toHaveValue('jfk-zira');
  await ask.click();
  await expect(pair).toBeDisabled();
  const busy = await (await request.get(`${info.url}/status`)).json();
  const conflict = await request.post(`${info.url}/select`, {
    data: { session: busy.session, pair: 'hopper-hazel' },
  });
  expect(conflict.status()).toBe(409);
  await expect(page.locator('#status')).toHaveText('Playback ended');
  await expect(pair).toBeEnabled();
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Active: Grace Hopper');
  await expect(ask).toBeEnabled();
  await page.getByLabel('Question', { exact: true }).fill('How do we detect one?');
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const followup = await (await request.get(`${info.url}/status`)).json();
  expect(followup.run.pair).toBe('hopper-hazel');
  expect(followup.run.answer).toContain('Earlier question: What is a black hole?');
  await page.getByLabel('Diagnostic fault').selectOption('llm-delay');
  await expect(ask).toBeEnabled();
  await ask.click();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(pair).toBeEnabled();
  const selected = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/select',
  );
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
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  const pair = page.getByLabel('Avatar and voice', { exact: true });
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const before = await (await request.get(`${info.url}/status`)).json();
  await page.getByLabel('Pair diagnostic', { exact: true }).selectOption('pair-delay');
  await expect(pair).toBeEnabled();
  await pair.selectOption('hopper-hazel');
  await expect(page.locator('#pair-status')).toContainText('Preparing Grace Hopper');
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
  expect(ready.activePair).toBe('hopper-hazel');
  await ask.click();
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const after = await (await request.get(`${info.url}/status`)).json();
  const dispatched = after.run.events.find((event) => event.event === 'provider-request');
  expect(dispatched.messages).toHaveLength(1);
  expect(after.run.pair).toBe('hopper-hazel');
});

test('complete answer, contextual follow-up, idle Stop and fresh conversation', async ({
  page,
  request,
}, info) => {
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#transcript')).toContainText('A black hole traps light.');
  await expect(page.locator('#status')).toHaveText('Playback ended');
  const measured = (await (await request.get(`${info.url}/status`)).json()).run.events;
  const submitted = measured.find((event) => event.event === 'submit-action');
  const moving = measured.find((event) => event.event === 'moving-video');
  const audible = measured.find((event) => event.event === 'digital-audio-onset');
  expect(submitted.clientMilliseconds).toBeLessThan(moving.clientMilliseconds);
  expect(submitted.clientMilliseconds).toBeLessThan(audible.clientMilliseconds);
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

test('repeated Stop across delayed stages retains questions and excludes interrupted answers', async ({
  page,
  request,
}, info) => {
  const ask = page.getByRole('button', { name: 'Ask', exact: true });
  for (const [fault, stage] of [
    ['llm-connect', 'llm-connect'],
    ['llm-delay', 'llm-first-text'],
    ['tts-delay', 'tts-start'],
  ]) {
    await expect(ask).toBeEnabled();
    await page.getByLabel('Diagnostic fault').selectOption(fault);
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
    await page.getByLabel('Question', { exact: true }).fill(`Replacement after ${fault}`);
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
    await page.route('**/segment?*', async (route) => {
      const index = new URL(route.request().url()).searchParams.get('index');
      if (index === '0')
        await route.fulfill({ path: 'tests/fixtures/browser.mp4', contentType: 'video/mp4' });
      else await route.fulfill({ status: 204, body: '' });
    });
    await page.getByLabel('Diagnostic fault').selectOption('');
    await page.getByRole('button', { name: 'Ask', exact: true }).click();
    await expect(page.locator('#status')).toHaveText('Playback ended');
    await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
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
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.locator('#status')).toContainText('budget');
  const after = await (await request.get(`${info.url}/status`)).json();
  expect(after.transcript.length).toBe(before.transcript.length);
  expect(after.run.id).toBe(before.run.id);
  expect(after.budget.estimated_usd).toBe(before.budget.estimated_usd);
  expect(after.budget.reserved_usd).toBe(before.budget.reserved_usd);
});
