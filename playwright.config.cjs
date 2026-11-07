const { defineConfig } = require('@playwright/test');

// Playwright sets FORCE_COLOR for workers; avoid inheriting a conflicting Node flag.
delete process.env.NO_COLOR;

module.exports = defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  workers: process.env.CI ? 4 : undefined,
  maxFailures: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: { headless: true, actionTimeout: 30_000 },
});
