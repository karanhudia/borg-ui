import type { APIRequestContext, Page } from 'playwright/test'

export const STORAGE_STATE = 'e2e-results/.auth/admin.json'

// Fresh-database defaults and the throwaway sshd from tests/e2e/setup-sshd.sh.
export const ADMIN = { username: 'admin', password: 'admin123' }
export const SSH = {
  host: process.env.E2E_SSH_HOST || '127.0.0.1',
  port: Number(process.env.E2E_SSH_PORT || 2222),
  user: process.env.E2E_SSH_USER || 'borge2e',
  password: process.env.E2E_SSH_PASSWORD || 'borg-e2e-password',
}

export async function login(request: APIRequestContext): Promise<string> {
  const response = await request.post('/api/auth/login', { form: ADMIN })
  if (!response.ok()) throw new Error(`login failed: ${response.status()} ${await response.text()}`)
  return (await response.json()).access_token
}

/** Request helpers that send the app's auth header. */
export function api(request: APIRequestContext, token: string) {
  const headers = { 'X-Borg-Authorization': `Bearer ${token}` }
  return {
    get: (url: string) => request.get(url, { headers }),
    post: (url: string, data?: unknown) => request.post(url, { headers, data }),
    put: (url: string, data?: unknown) => request.put(url, { headers, data }),
  }
}

/** Never let a test run reach the real analytics endpoint. */
export async function blockAnalytics(page: Page) {
  await page.route('https://t.borgui.com/**', (route) => route.abort())
}
