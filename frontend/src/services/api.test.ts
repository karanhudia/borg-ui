/**
 * Tests for api.ts
 * Focus: Interceptor logic that handles auth and redirects
 * WHY: Incorrect auth handling = users stuck at login or get 401s everywhere
 */

import { describe, it, expect, beforeEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import api from './api'

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

  it('attaches Authorization header when token exists', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'test-token-123'

    mock.onGet('/test').reply((config) => {
      // Verify the Authorization header was added
      expect(config.headers?.Authorization).toBe('Bearer test-token-123')
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('does not add Authorization header when no token exists', async () => {
    const mock = new MockAdapter(api)
    // No token in localStorage

    mock.onGet('/test').reply((config) => {
      // Authorization header should not be present
      expect(config.headers?.Authorization).toBeUndefined()
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
  })

  it('preserves other headers while adding Authorization', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'test-token'

    mock.onGet('/test').reply((config) => {
      // Check both headers are present
      expect(config.headers?.Authorization).toBe('Bearer test-token')
      expect(config.headers?.['Content-Type']).toBe('application/json')
      return [200, { success: true }]
    })

    await api.get('/test')
    mock.restore()
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
    } catch (error) {
      // Error is expected
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

  it('clears localStorage token on 401 redirect', async () => {
    const mock = new MockAdapter(api)
    localStorageMock['access_token'] = 'expired-token'

    mock.onGet('/dashboard/status').reply(401)

    try {
      await api.get('/dashboard/status')
    } catch (error) {
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
    } catch (error) {
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
      } catch (error) {
        // Expected
      }

      // All should redirect except /auth/login
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
