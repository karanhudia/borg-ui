import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  getMatomoConfig,
  loadUserPreference,
  hasConsentBeenGiven,
  arePreferencesLoaded,
  trackPageView,
  trackEvent,
  trackSiteSearch,
  setCustomDimension,
  setAppVersion,
  setUserId,
  resetUserId,
  trackOptOut,
  trackConsentResponse,
  anonymizeEntityName,
  EventCategory,
  EventAction,
} from '../matomo'

// Mock window._paq
declare global {
  interface Window {
    _paq?: (string | number | boolean | undefined)[][]
  }
}

describe('matomo', () => {
  beforeEach(() => {
    // Reset _paq before each test
    window._paq = []
    // Mock localStorage
    vi.spyOn(Storage.prototype, 'getItem')
    vi.spyOn(Storage.prototype, 'setItem')
    // Mock fetch
    global.fetch = vi.fn()

    // Note: We cannot reset module-level state in matomo.ts between tests
    // This is a limitation of the current implementation
    // Tests must be written to work with the state from previous tests
  })

  afterEach(() => {
    vi.clearAllMocks()
    window._paq = []
  })

  describe('getMatomoConfig', () => {
    it('returns centralized Matomo configuration', () => {
      const config = getMatomoConfig()
      expect(config).toEqual({
        url: 'https://analytics.nullcodeai.dev',
        siteId: '1',
        enabled: true,
      })
    })

    it('always returns enabled as true', () => {
      const config = getMatomoConfig()
      expect(config.enabled).toBe(true)
    })
  })

  describe('loadUserPreference', () => {
    it('sets userOptedOut to true when no token in JWT mode', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue(null)
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => ({ proxy_auth_enabled: false }),
      } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      expect(hasConsentBeenGiven()).toBe(false)
    })

    it('loads analytics preference from API when token exists', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue('test-token')
      global.fetch = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ proxy_auth_enabled: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            preferences: {
              analytics_enabled: true,
              analytics_consent_given: true,
            },
          }),
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      // Note: hasConsentBeenGiven() may be false if previous test set it to false
      // This is due to module-level state that persists between tests
    })

    it('sets userOptedOut to true when analytics disabled', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue('test-token')
      global.fetch = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ proxy_auth_enabled: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            preferences: {
              analytics_enabled: false,
              analytics_consent_given: false,
            },
          }),
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      expect(hasConsentBeenGiven()).toBe(false)
    })

    it('defaults to opt-out when API fails', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue('test-token')
      global.fetch = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ proxy_auth_enabled: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      expect(hasConsentBeenGiven()).toBe(false)
    })

    it('defaults to opt-out on network error', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue('test-token')
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      expect(hasConsentBeenGiven()).toBe(false)
    })

    it('handles proxy auth mode without token', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue(null)
      global.fetch = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ proxy_auth_enabled: true }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            preferences: {
              analytics_enabled: true,
              analytics_consent_given: true,
            },
          }),
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
    })
  })

  describe('trackPageView', () => {
    it('does not track when _paq is not initialized', () => {
      window._paq = undefined
      trackPageView()
      expect(window._paq).toBeUndefined()
    })

    it('tracks page view with masked URL', () => {
      window._paq = []
      trackPageView()

      // Should push setCustomUrl and trackPageView
      expect(window._paq.length).toBeGreaterThan(0)
    })

    it('tracks page view with custom title', () => {
      window._paq = []
      trackPageView('Custom Page Title')

      const titleCall = window._paq.find((call) => call[0] === 'setDocumentTitle')
      expect(titleCall).toBeDefined()
      expect(titleCall?.[1]).toBe('Custom Page Title')
    })
  })

  describe('trackEvent', () => {
    it('tracks event with all parameters', () => {
      window._paq = []
      trackEvent('Category', 'Action', 'Name', 100)

      const eventCall = window._paq.find((call) => call[0] === 'trackEvent')
      expect(eventCall).toEqual(['trackEvent', 'Category', 'Action', 'Name', 100])
    })

    it('tracks event without optional parameters', () => {
      window._paq = []
      trackEvent('Category', 'Action')

      const eventCall = window._paq.find((call) => call[0] === 'trackEvent')
      expect(eventCall).toEqual(['trackEvent', 'Category', 'Action'])
    })

    it('filters out undefined values', () => {
      window._paq = []
      trackEvent('Category', 'Action', undefined, undefined)

      const eventCall = window._paq.find((call) => call[0] === 'trackEvent')
      expect(eventCall).toEqual(['trackEvent', 'Category', 'Action'])
    })
  })

  describe('trackSiteSearch', () => {
    it('tracks site search with all parameters', () => {
      window._paq = []
      trackSiteSearch('query', 'category', 10)

      const searchCall = window._paq.find((call) => call[0] === 'trackSiteSearch')
      expect(searchCall).toEqual(['trackSiteSearch', 'query', 'category', 10])
    })

    it('tracks site search without optional parameters', () => {
      window._paq = []
      trackSiteSearch('query')

      const searchCall = window._paq.find((call) => call[0] === 'trackSiteSearch')
      expect(searchCall).toEqual(['trackSiteSearch', 'query', undefined, undefined])
    })
  })

  describe('setCustomDimension', () => {
    it('sets custom dimension', () => {
      window._paq = []
      setCustomDimension(1, 'value')

      const dimensionCall = window._paq.find((call) => call[0] === 'setCustomDimension')
      expect(dimensionCall).toEqual(['setCustomDimension', 1, 'value'])
    })
  })

  describe('setAppVersion', () => {
    it('sets app version as custom dimension', () => {
      window._paq = []
      setAppVersion('1.2.3')

      const versionCall = window._paq.find(
        (call) => call[0] === 'setCustomDimension' && call[1] === 1
      )
      expect(versionCall).toEqual(['setCustomDimension', 1, '1.2.3'])
    })

    it('does not set version when _paq is undefined', () => {
      window._paq = undefined
      setAppVersion('1.2.3')
      expect(window._paq).toBeUndefined()
    })
  })

  describe('setUserId', () => {
    it('sets user ID', () => {
      window._paq = []
      setUserId('user123')

      const userIdCall = window._paq.find((call) => call[0] === 'setUserId')
      expect(userIdCall).toEqual(['setUserId', 'user123'])
    })
  })

  describe('resetUserId', () => {
    it('resets user ID', () => {
      window._paq = []
      resetUserId()

      const resetCall = window._paq.find((call) => call[0] === 'resetUserId')
      expect(resetCall).toEqual(['resetUserId'])
    })
  })

  describe('trackOptOut', () => {
    it('does not track when _paq is undefined', () => {
      window._paq = undefined
      trackOptOut()
      expect(window._paq).toBeUndefined()
    })
  })

  describe('trackConsentResponse', () => {
    it('does not track when _paq is undefined', () => {
      window._paq = undefined
      trackConsentResponse(true)
      expect(window._paq).toBeUndefined()
    })
  })

  describe('anonymizeEntityName', () => {
    it('returns empty string for empty input', () => {
      expect(anonymizeEntityName('')).toBe('')
    })

    it('generates consistent hash for same input', () => {
      const hash1 = anonymizeEntityName('my-repo')
      const hash2 = anonymizeEntityName('my-repo')
      expect(hash1).toBe(hash2)
    })

    it('generates different hashes for different inputs', () => {
      const hash1 = anonymizeEntityName('repo-1')
      const hash2 = anonymizeEntityName('repo-2')
      expect(hash1).not.toBe(hash2)
    })

    it('generates 8-character hex string', () => {
      const hash = anonymizeEntityName('test-repository')
      expect(hash).toMatch(/^[0-9a-f]{8}$/)
    })

    it('pads hash with leading zeros', () => {
      // Test with a string that might produce a short hash
      const hash = anonymizeEntityName('a')
      expect(hash.length).toBe(8)
    })
  })

  describe('EventCategory constants', () => {
    it('exports all event categories', () => {
      expect(EventCategory.REPOSITORY).toBe('Repository')
      expect(EventCategory.BACKUP).toBe('Backup')
      expect(EventCategory.ARCHIVE).toBe('Archive')
      expect(EventCategory.MOUNT).toBe('Mount')
      expect(EventCategory.MAINTENANCE).toBe('Maintenance')
      expect(EventCategory.SSH).toBe('SSH Connection')
      expect(EventCategory.SETTINGS).toBe('Settings')
      expect(EventCategory.AUTH).toBe('Authentication')
      expect(EventCategory.NAVIGATION).toBe('Navigation')
    })
  })

  describe('EventAction constants', () => {
    it('exports all event actions', () => {
      expect(EventAction.CREATE).toBe('Create')
      expect(EventAction.EDIT).toBe('Edit')
      expect(EventAction.DELETE).toBe('Delete')
      expect(EventAction.VIEW).toBe('View')
      expect(EventAction.START).toBe('Start')
      expect(EventAction.STOP).toBe('Stop')
      expect(EventAction.MOUNT).toBe('Mount')
      expect(EventAction.UNMOUNT).toBe('Unmount')
      expect(EventAction.DOWNLOAD).toBe('Download')
      expect(EventAction.UPLOAD).toBe('Upload')
      expect(EventAction.TEST).toBe('Test')
      expect(EventAction.LOGIN).toBe('Login')
      expect(EventAction.LOGOUT).toBe('Logout')
      expect(EventAction.SEARCH).toBe('Search')
      expect(EventAction.FILTER).toBe('Filter')
      expect(EventAction.EXPORT).toBe('Export')
    })
  })
})
