// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.js',
  timeout: 600_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: 'http://localhost:3002',
    headless: true,
    viewport: { width: 1440, height: 900 },
    video: 'off',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  reporter: [['list'], ['json', { outputFile: '/tmp/marvin-c26-results.json' }]],
});
