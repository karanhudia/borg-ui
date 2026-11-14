import { defineConfig, devices } from 'playwright/test'

// Browser e2e against a running backend on a fresh DATA_DIR. See tests/README.md.
export default defineConfig({
  testDir: './e2e',
  // *.e2e.ts keeps these out of vitest's default *.test / *.spec glob.
  testMatch: /.*\.(e2e|setup)\.ts$/,
  outputDir: './e2e-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8082',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // MUI fades can sit at opacity 0 in headless Chromium; skip the motion instead.
    contextOptions: { reducedMotion: 'reduce' },
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts$/ },
    {
      name: 'chromium',
      testMatch: /.*\.e2e\.ts$/,
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'e2e-results/.auth/admin.json' },
    },
  ],
})
