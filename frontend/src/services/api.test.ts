/**
 * Tests for api.ts
 * Focus: Interceptor logic that handles auth and redirects
 * WHY: Incorrect auth handling = users stuck at login or get 401s everywhere
 */

import { describe, it, expect, beforeEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import api, { authAPI, backupAPI, backupPlansAPI, repositoriesAPI } from './api'

describe('API Request Interceptor', () => {
  let localStorageMock: { [key: string]: string }

  beforeEach(() => {
    // Mock localStorage
    localStorageMock = {}
    Object.defineProperty(globalThis, 'localStorage', {
      value: {
        getItem: (key: string) => localStorageMock[key] || null,
        setItem: (key: string, value: string) => {
          localStorageMock[key] = value
        },
        removeItem: (key: string) => {
          delete localStorageMock[key]
        },
        clear: () => {
          localStorageMock = {}
        },
        length: 0,
        key: () => null,
      },
      writable: true,
    })
  })

  it('attaches X-Borg-Authorization header when token exists', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'test-token-123'

    mock.onGet('/test').reply((config) => {
      // Verify the Authorization header was added
      expect(config.headers?.['X-Borg-Authorization']).toBe('Bearer test-token-123')
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('does not add X-Borg-Authorization header when no token exists', async () => {
    const mock = new MockAdapter(api)
    // No token in localStorage

    mock.onGet('/test').reply((config) => {
      // Authorization header should not be present
      expect(config.headers?.['X-Borg-Authorization']).toBeUndefined()
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('preserves other headers while adding X-Borg-Authorization', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'test-token'

    mock.onGet('/test').reply((config) => {
      // Check both headers are present
      expect(config.headers?.['X-Borg-Authorization']).toBe('Bearer test-token')
      expect(config.headers?.['Content-Type']).toBe('application/json')
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('uses the active remote backend API base for requests', async () => {
    const { createRemoteBackendClient, setActiveBackendTarget } =
      await import('./remoteBackends/storage')
    const remote = createRemoteBackendClient({
      name: 'Remote',
      backendUrl: 'https://remote.example.com/borg',
    })
    setActiveBackendTarget(remote.id)
    const mock = new MockAdapter(api)

    mock.onGet('/test').reply((config) => {
      expect(config.baseURL).toBe('https://remote.example.com/borg/api')
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('builds OIDC URLs from the active backend API base', async () => {
    const { createRemoteBackendClient, setActiveBackendTarget } =
      await import('./remoteBackends/storage')
    const remote = createRemoteBackendClient({
      name: 'Remote',
      backendUrl: 'https://remote.example.com/borg',
    })
    setActiveBackendTarget(remote.id)

    expect(authAPI.getOidcLoginUrl('https://app.example.com/login')).toBe(
      'https://remote.example.com/borg/api/auth/oidc/login?return_to=https%3A%2F%2Fapp.example.com%2Flogin'
    )
    expect(authAPI.getOidcLinkUrl()).toBe('https://remote.example.com/borg/api/auth/oidc/link')
  })
})

describe('API Response Interceptor - 401 Handling', () => {
  let localStorageMock: { [key: string]: string }
  let windowLocationHref: string

  beforeEach(() => {
    // Mock localStorage
    localStorageMock = {}
    Object.defineProperty(globalThis, 'localStorage', {
      value: {
        getItem: (key: string) => localStorageMock[key] || null,
        setItem: (key: string, value: string) => {
          localStorageMock[key] = value
        },
        removeItem: (key: string) => {
          delete localStorageMock[key]
        },
        clear: () => {
          localStorageMock = {}
        },
        length: 0,
        key: () => null,
      },
      writable: true,
    })

    // Mock window.location.href
    windowLocationHref = ''
    Object.defineProperty(window, 'location', {
      value: {
        get href() {
          return windowLocationHref
        },
        set href(value: string) {
          windowLocationHref = value
        },
      },
      writable: true,
    })
  })

  it('redirects to /login on 401 error from authenticated endpoint', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'expired-token'

    mock.onGet('/repositories/').reply(401, { detail: 'Unauthorized' })

    try {
      await api.get('/repositories/')
    } catch {
      // Expected
    }

    // Should redirect to login
    expect(windowLocationHref).toBe('/login')

    // Should clear token
    expect(localStorageMock['access_token']).toBeUndefined()

    mock.restore()
  })

  it('does NOT redirect on 401 from /auth/login endpoint', async () => {
    const mock = new MockAdapter(api)

    mock.onPost('/auth/login').reply(401, { detail: 'Invalid credentials' })

    try {
      await api.post('/auth/login', 'username=test&password=wrong')
    } catch (error) {
      // Error should propagate so UI can show "wrong password"
      expect(error).toBeDefined()
    }

    // Should NOT redirect
    expect(windowLocationHref).toBe('')

    // Should NOT clear token (user is trying to log in)
    // Note: There's no token to clear anyway in this scenario

    mock.restore()
  })

  it('does NOT redirect on 401 from /auth/login/totp endpoint', async () => {
    const mock = new MockAdapter(api)

    mock.onPost('/auth/login/totp').reply(401, { detail: 'Invalid code' })

    try {
      await api.post('/auth/login/totp', {
        login_challenge_token: 'challenge-token',
        code: '123456',
      })
    } catch (error) {
      expect(error).toBeDefined()
    }

    expect(windowLocationHref).toBe('')

    mock.restore()
  })

  it('does NOT redirect on 401 from /auth/passkeys/authenticate/verify endpoint', async () => {
    const mock = new MockAdapter(api)

    mock.onPost('/auth/passkeys/authenticate/verify').reply(401, { detail: 'Invalid passkey' })

    try {
      await api.post('/auth/passkeys/authenticate/verify', {
        ceremony_token: 'ceremony-token',
        credential: {},
      })
    } catch (error) {
      expect(error).toBeDefined()
    }

    expect(windowLocationHref).toBe('')
    mock.restore()
  })

  it('clears localStorage token on 401 redirect', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'expired-token'

    mock.onGet('/dashboard/status').reply(401)

    try {
      await api.get('/dashboard/status')
    } catch {
      // Expected
    }

    expect(localStorageMock['access_token']).toBeUndefined()
    expect(windowLocationHref).toBe('/login')

    mock.restore()
  })

  it('does not redirect on other error codes (404, 500)', async () => {
    const mock = new MockAdapter(api)

    // Test 404
    mock.onGet('/repositories/999').reply(404, { detail: 'Not found' })

    try {
      await api.get('/repositories/999')
    } catch (error) {
      // Error should propagate normally
      expect(error).toBeDefined()
    }

    expect(windowLocationHref).toBe('') // No redirect

    // Test 500
    mock.onGet('/backup/start').reply(500, { detail: 'Internal server error' })

    try {
      await api.get('/backup/start')
    } catch (error) {
      expect(error).toBeDefined()
    }

    expect(windowLocationHref).toBe('') // Still no redirect

    mock.restore()
  })

  it('passes through successful responses without interference', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'valid-token'

    mock.onGet('/repositories/').reply(200, [{ id: 1, name: 'test-repo' }])

    const response = await api.get('/repositories/')

    expect(response.status).toBe(200)
    expect(response.data).toEqual([{ id: 1, name: 'test-repo' }])
    expect(windowLocationHref).toBe('') // No redirect

    mock.restore()
  })
})

describe('API Response Interceptor - Edge Cases', () => {
  let localStorageMock: { [key: string]: string }
  let windowLocationHref: string

  beforeEach(() => {
    localStorageMock = {}
    Object.defineProperty(globalThis, 'localStorage', {
      value: {
        getItem: (key: string) => localStorageMock[key] || null,
        setItem: (key: string, value: string) => {
          localStorageMock[key] = value
        },
        removeItem: (key: string) => {
          delete localStorageMock[key]
        },
        clear: () => {
          localStorageMock = {}
        },
        length: 0,
        key: () => null,
      },
      writable: true,
    })

    windowLocationHref = ''
    Object.defineProperty(window, 'location', {
      value: {
        get href() {
          return windowLocationHref
        },
        set href(value: string) {
          windowLocationHref = value
        },
      },
      writable: true,
    })
  })

  it('handles 401 when no token was present initially', async () => {
    const mock = new MockAdapter(api)
    // No token in localStorage

    mock.onGet('/repositories/').reply(401)

    try {
      await api.get('/repositories/')
    } catch {
      // Expected
    }

    // Should still redirect (user needs to log in)
    expect(windowLocationHref).toBe('/login')

    mock.restore()
  })

  it('handles 401 with different URL patterns', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'token'

    // Test various endpoint patterns
    const endpoints = [
      '/repositories/1',
      '/backup/status/123',
      '/settings/users',
      '/auth/refresh', // Should redirect (not /auth/login)
      '/auth/logout', // Should redirect
    ]

    for (const endpoint of endpoints) {
      mock.onPost(endpoint).reply(401)
      mock.onGet(endpoint).reply(401)

      windowLocationHref = '' // Reset

      try {
        await api.get(endpoint)
      } catch {
        // Expected
      }

      // All should redirect except /auth/login and /auth/login/totp
      expect(windowLocationHref).toBe('/login')
    }

    mock.restore()
  })
})

describe('API Configuration', () => {
  it('uses correct base URL from environment or default', () => {
    // The api instance should have baseURL set
    expect(api.defaults.baseURL).toBeDefined()
    // Default should be '/api' if VITE_API_URL is not set
    expect(api.defaults.baseURL).toBe('/api')
  })

  it('has correct default Content-Type header', () => {
    expect(api.defaults.headers['Content-Type']).toBe('application/json')
  })
})

describe('Repositories API - Repository wipe', () => {
  it('posts wipe preview requests to the repository preview endpoint', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/repositories/7/wipe-preview').reply((config) => {
      expect(JSON.parse(config.data)).toEqual({ run_compact: false })
      return [200, { id: 11, status: 'previewed' }]
    })

    const response = await repositoriesAPI.previewRepositoryWipe(7, { run_compact: false })

    expect(response.data).toEqual({ id: 11, status: 'previewed' })
    mock.restore()
  })

  it('posts wipe execution confirmations to the repository wipe endpoint', async () => {
    const mock = new MockAdapter(api)
    const payload = {
      preview_id: 11,
      preview_fingerprint: 'sha256:abc',
      confirmation_phrase: 'WIPE Primary',
      understood: true,
      run_compact: true,
    }
    mock.onPost('/repositories/7/wipe').reply((config) => {
      expect(JSON.parse(config.data)).toEqual(payload)
      return [200, { id: 11, status: 'pending' }]
    })

    const response = await repositoriesAPI.executeRepositoryWipe(7, payload)

    expect(response.data).toEqual({ id: 11, status: 'pending' })
    mock.restore()
  })

  it('gets and cancels repository wipe jobs by repository and job id', async () => {
    const mock = new MockAdapter(api)
    mock.onGet('/repositories/7/wipe-jobs/11').reply(200, { id: 11, status: 'running' })
    mock.onPost('/repositories/7/wipe-jobs/11/cancel').reply(200, {
      id: 11,
      status: 'cancelled',
    })

    const status = await repositoriesAPI.getRepositoryWipeJob(7, 11)
    const cancelled = await repositoriesAPI.cancelRepositoryWipeJob(7, 11)

    expect(status.data).toEqual({ id: 11, status: 'running' })
    expect(cancelled.data).toEqual({ id: 11, status: 'cancelled' })
    mock.restore()
  })
})

describe('Retry API helpers', () => {
  it('retries backup jobs through the backend retry endpoint', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/backup/jobs/42/retry').reply(202, {
      job_id: 108,
      status: 'pending',
      retry_source_job_id: 42,
    })

    const response = await backupAPI.retryJob(42)

    expect(response.data).toEqual({
      job_id: 108,
      status: 'pending',
      retry_source_job_id: 42,
    })
    mock.restore()
  })

  it('retries backup plan runs through the backend retry endpoint', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/backup-plans/runs/77/retry').reply(202, {
      id: 93,
      status: 'pending',
      trigger: 'retry',
      retry_source_run_id: 77,
    })

    const response = await backupPlansAPI.retryRun(77)

    expect(response.data).toEqual({
      id: 93,
      status: 'pending',
      trigger: 'retry',
      retry_source_run_id: 77,
    })
    mock.restore()
  })
})
