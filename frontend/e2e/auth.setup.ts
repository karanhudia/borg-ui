import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { expect, test as setup } from 'playwright/test'
import { STORAGE_STATE, api, login } from './helpers'

// Logs in once on the fresh database and clears the first-run prompts through the
// API, so no test has to click past them and no analytics consent event is sent.
setup('log in as the default admin', async ({ request, baseURL }) => {
  const token = await login(request)
  const authed = api(request, token)

  const skip = await authed.post('/api/auth/password-setup/skip')
  expect(skip.ok(), await skip.text()).toBeTruthy()

  const prefs = await authed.put('/api/settings/preferences', {
    analytics_enabled: false,
    analytics_consent_given: true,
  })
  expect(prefs.ok(), await prefs.text()).toBeTruthy()

  // The app reads its token from localStorage, not a cookie.
  mkdirSync(dirname(STORAGE_STATE), { recursive: true })
  writeFileSync(
    STORAGE_STATE,
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: new URL(baseURL!).origin,
          localStorage: [{ name: 'access_token', value: token }],
        },
      ],
    })
  )
})
