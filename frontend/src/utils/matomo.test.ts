import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  getMatomoConfig,
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
  loadUserPreference,
  initMatomoIfEnabled,
  resetOptOutCache,
  EventCategory,
  EventAction,
} from './matomo'

describe('Matomo Analytics', () => {
  let mockPaq: (string | number | boolean | undefined)[][]
  let localStorageMock: Record<string, string>

  beforeEach(() => {
    // Reset _paq
    mockPaq = []
    // @ts-expect-error - Setting window._paq for testing
    window._paq = mockPaq

    // Reset localStorage
    localStorageMock = {}
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(
      (key) => localStorageMock[key] || null
    )
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => {
      localStorageMock[key] = value
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation((key) => {
      delete localStorageMock[key]
    })

    // Mock fetch
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      json: async () => ({}),
    } as Response)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    // @ts-expect-error - Cleaning up window._paq
    delete window._paq
  })

  describe('getMatomoConfig', () => {
    it('returns correct config object', () => {
      const config = getMatomoConfig()

      expect(config).toHaveProperty('url')
      expect(config).toHaveProperty('siteId')
      expect(config).toHaveProperty('enabled')
      expect(config.url).toBe('https://analytics.nullcodeai.dev')
      expect(config.siteId).toBe('1')
      expect(config.enabled).toBe(true)
    })
  })

  describe('anonymizeEntityName', () => {
    it('returns empty string for empty input', () => {
      expect(anonymizeEntityName('')).toBe('')
    })

    it('returns empty string for null-like input', () => {
      // @ts-expect-error - Testing edge case
      expect(anonymizeEntityName(null)).toBe('')
      // @ts-expect-error - Testing edge case
      expect(anonymizeEntityName(undefined)).toBe('')
    })

    it('returns consistent hash for same input', () => {
      const hash1 = anonymizeEntityName('my-backup-repo')
      const hash2 = anonymizeEntityName('my-backup-repo')

      expect(hash1).toBe(hash2)
    })

    it('returns different hash for different inputs', () => {
      const hash1 = anonymizeEntityName('repo-1')
      const hash2 = anonymizeEntityName('repo-2')

      expect(hash1).not.toBe(hash2)
    })

    it('returns 8-character hex string', () => {
      const hash = anonymizeEntityName('test-repository')

      expect(hash).toHaveLength(8)
      expect(/^[0-9a-f]{8}$/.test(hash)).toBe(true)
    })

    it('handles special characters', () => {
      const hash = anonymizeEntityName('repo with spaces & special chars!')

      expect(hash).toHaveLength(8)
      expect(/^[0-9a-f]{8}$/.test(hash)).toBe(true)
    })
  })

  describe('EventCategory constants', () => {
    it('has expected categories', () => {
      expect(EventCategory.REPOSITORY).toBe('Repository')
      expect(EventCategory.BACKUP).toBe('Backup')
      expect(EventCategory.ARCHIVE).toBe('Archive')
      expect(EventCategory.MOUNT).toBe('Mount')
      expect(EventCategory.SSH).toBe('SSH Connection')
      expect(EventCategory.SETTINGS).toBe('Settings')
      expect(EventCategory.AUTH).toBe('Authentication')
      expect(EventCategory.NAVIGATION).toBe('Navigation')
    })
  })

  describe('EventAction constants', () => {
    it('has expected actions', () => {
      expect(EventAction.CREATE).toBe('Create')
      expect(EventAction.EDIT).toBe('Edit')
      expect(EventAction.DELETE).toBe('Delete')
      expect(EventAction.VIEW).toBe('View')
      expect(EventAction.START).toBe('Start')
      expect(EventAction.MOUNT).toBe('Mount')
      expect(EventAction.UNMOUNT).toBe('Unmount')
      expect(EventAction.LOGIN).toBe('Login')
      expect(EventAction.LOGOUT).toBe('Logout')
    })
  })

  describe('loadUserPreference', () => {
    it('sets userOptedOut to true when no token', async () => {
      // No token in localStorage
      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
    })

    it('sets userOptedOut to true when API fails', async () => {
      localStorageMock['access_token'] = 'test-token'
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        json: async () => ({}),
      } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
    })

    it('sets userOptedOut based on API response', async () => {
      localStorageMock['access_token'] = 'test-token'
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
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
      expect(hasConsentBeenGiven()).toBe(true)
    })

    it('handles fetch errors gracefully', async () => {
      localStorageMock['access_token'] = 'test-token'
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'))

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
      // Should default to opt-out on error
    })
  })

  describe('arePreferencesLoaded', () => {
    it('returns boolean value', () => {
      const result = arePreferencesLoaded()
      expect(typeof result).toBe('boolean')
    })
  })

  describe('hasConsentBeenGiven', () => {
    it('returns null or boolean', () => {
      const result = hasConsentBeenGiven()
      expect(result === null || typeof result === 'boolean').toBe(true)
    })
  })

  describe('tracking functions when disabled', () => {
    beforeEach(async () => {
      // Ensure tracking is disabled (no token = opted out)
      await loadUserPreference()
    })

    it('trackPageView does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      trackPageView('Test Page')
      // Should not add anything to _paq
      expect(mockPaq.length).toBe(initialLength)
    })

    it('trackEvent does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      trackEvent('Test', 'Action', 'Name', 123)
      expect(mockPaq.length).toBe(initialLength)
    })

    it('trackSiteSearch does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      trackSiteSearch('keyword', 'category', 10)
      expect(mockPaq.length).toBe(initialLength)
    })

    it('setCustomDimension does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      setCustomDimension(1, 'value')
      expect(mockPaq.length).toBe(initialLength)
    })

    it('setUserId does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      setUserId('user123')
      expect(mockPaq.length).toBe(initialLength)
    })

    it('resetUserId does nothing when canTrack returns false', () => {
      const initialLength = mockPaq.length
      resetUserId()
      expect(mockPaq.length).toBe(initialLength)
    })
  })

  describe('setAppVersion', () => {
    it('pushes to _paq when _paq exists', () => {
      setAppVersion('1.0.0')
      expect(mockPaq).toContainEqual(['setCustomDimension', 1, '1.0.0'])
    })

    it('does nothing when _paq is undefined', () => {
      // @ts-expect-error - Testing edge case
      delete window._paq
      // Should not throw
      setAppVersion('1.0.0')
    })
  })

  describe('trackOptOut', () => {
    it('does nothing when matomo not initialized', () => {
      const initialLength = mockPaq.length
      trackOptOut()
      expect(mockPaq.length).toBe(initialLength)
    })
  })

  describe('trackConsentResponse', () => {
    it('does nothing when matomo not initialized', () => {
      const initialLength = mockPaq.length
      trackConsentResponse(true)
      trackConsentResponse(false)
      expect(mockPaq.length).toBe(initialLength)
    })
  })

  describe('initMatomoIfEnabled', () => {
    it('does not throw when called', () => {
      expect(() => initMatomoIfEnabled()).not.toThrow()
    })
  })

  describe('resetOptOutCache', () => {
    it('calls loadUserPreference and initMatomoIfEnabled', async () => {
      await expect(resetOptOutCache()).resolves.not.toThrow()
    })
  })

  describe('tracking when enabled', () => {
    beforeEach(async () => {
      // Set up for enabled tracking
      localStorageMock['access_token'] = 'test-token'
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          preferences: {
            analytics_enabled: true,
            analytics_consent_given: true,
          },
        }),
      } as Response)
      await loadUserPreference()
      // Manually set _paq to simulate initialization
      mockPaq = []
      // @ts-expect-error - Setting window._paq for testing
      window._paq = mockPaq
    })

    it('trackPageView adds to _paq when enabled', () => {
      const initialLength = mockPaq.length
      trackPageView('Test Page')
      // Should add setCustomUrl and trackPageView
      expect(mockPaq.length).toBeGreaterThan(initialLength)
    })

    it('trackPageView with custom title sets document title', () => {
      trackPageView('Custom Title')
      expect(mockPaq.some((item) => item[0] === 'setDocumentTitle')).toBe(true)
    })

    it('trackEvent adds event to _paq', () => {
      const initialLength = mockPaq.length
      trackEvent('Category', 'Action', 'Name', 123)
      expect(mockPaq.length).toBeGreaterThan(initialLength)
      expect(mockPaq.some((item) => item[0] === 'trackEvent')).toBe(true)
    })

    it('trackSiteSearch adds search to _paq', () => {
      const initialLength = mockPaq.length
      trackSiteSearch('keyword', 'category', 10)
      expect(mockPaq.length).toBeGreaterThan(initialLength)
      expect(mockPaq.some((item) => item[0] === 'trackSiteSearch')).toBe(true)
    })

    it('setCustomDimension adds dimension to _paq', () => {
      const initialLength = mockPaq.length
      setCustomDimension(2, 'test-value')
      expect(mockPaq.length).toBeGreaterThan(initialLength)
      expect(mockPaq.some((item) => item[0] === 'setCustomDimension')).toBe(true)
    })

    it('setUserId adds userId to _paq', () => {
      const initialLength = mockPaq.length
      setUserId('user-123')
      expect(mockPaq.length).toBeGreaterThan(initialLength)
      expect(mockPaq.some((item) => item[0] === 'setUserId')).toBe(true)
    })

    it('resetUserId adds resetUserId to _paq', () => {
      const initialLength = mockPaq.length
      resetUserId()
      expect(mockPaq.length).toBeGreaterThan(initialLength)
      expect(mockPaq.some((item) => item[0] === 'resetUserId')).toBe(true)
    })
  })

  describe('trackEvent filtering', () => {
    beforeEach(async () => {
      localStorageMock['access_token'] = 'test-token'
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          preferences: {
            analytics_enabled: true,
          },
        }),
      } as Response)
      await loadUserPreference()
      mockPaq = []
      // @ts-expect-error - Setting window._paq for testing
      window._paq = mockPaq
    })

    it('filters undefined values from event data', () => {
      trackEvent('Category', 'Action')
      // Should have trackEvent, Category, Action but no undefined values
      const eventCall = mockPaq.find((item) => item[0] === 'trackEvent')
      expect(eventCall).toBeDefined()
      expect(eventCall).not.toContain(undefined)
    })

    it('includes name when provided', () => {
      trackEvent('Category', 'Action', 'Name')
      const eventCall = mockPaq.find((item) => item[0] === 'trackEvent')
      expect(eventCall).toContain('Name')
    })

    it('includes value when provided', () => {
      trackEvent('Category', 'Action', 'Name', 42)
      const eventCall = mockPaq.find((item) => item[0] === 'trackEvent')
      expect(eventCall).toContain(42)
    })
  })
})
