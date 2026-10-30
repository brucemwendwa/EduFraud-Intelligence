import { defineConfig } from '@playwright/test';

/**
 * Browser acceptance tests. Start the API and web client first (`make dev`), against freshly
 * seeded synthetic data (`make seed`). Override the target with E2E_BASE_URL.
 * Uses the locally installed Google Chrome, so no browser download is needed.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: 'chrome',
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
  },
});
