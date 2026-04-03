import { expect, afterEach, beforeAll, afterAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import * as matchers from '@testing-library/jest-dom/matchers'
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import '../i18n'
import api from '../services/api'
import { httpClient as borgApiHttpClient } from '../services/borgApi/client'

// Mock usePlan globally — plan gating uses useQuery which requires a QueryClientProvider.
// Unit tests that don't set one up should not fail because of plan feature checks.
vi.mock('../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'free',
    isLoading: false,
    isPro: false,
    isFree: true,
    can: () => true,
  }),
}))

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers)

const createDefaultFetchResponse = () =>
  Promise.resolve({
    ok: false,
    status: 503,
    statusText: 'Test fetch not mocked',
    json: async () => ({}),
    text: async () => '',
  } as Response)

const defaultFetchMock = vi.fn(createDefaultFetchResponse)
vi.stubGlobal('fetch', defaultFetchMock)

const testAxiosAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => ({
  data: {},
  status: 503,
  statusText: 'Test request not mocked',
  headers: {},
  config,
})

api.defaults.adapter = testAxiosAdapter
borgApiHttpClient.defaults.adapter = testAxiosAdapter

// Cleanup after each test
afterEach(() => {
  cleanup()
  vi.clearAllTimers()
  vi.useRealTimers()
  defaultFetchMock.mockClear()
  vi.stubGlobal('fetch', defaultFetchMock)
  api.defaults.adapter = testAxiosAdapter
  borgApiHttpClient.defaults.adapter = testAxiosAdapter
})

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock IntersectionObserver
globalThis.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  takeRecords() {
    return []
  }
  unobserve() {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any

// Mock ResizeObserver
globalThis.ResizeObserver = class ResizeObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any

// Mock scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

// Suppress console errors during tests (but fail tests that throw)
const originalError = console.error

beforeAll(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  console.error = (...args: any[]) => {
    // Only suppress React Testing Library's specific warnings
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Warning: ReactDOM.render') ||
        args[0].includes('Warning: useLayoutEffect') ||
        args[0].includes('Not implemented: HTMLFormElement.prototype.submit'))
    ) {
      return
    }

    originalError.call(console, ...args)
  }
})

afterAll(() => {
  console.error = originalError
})
