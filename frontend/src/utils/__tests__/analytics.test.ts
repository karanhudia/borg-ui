import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  getAnalyticsConfig,
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
  trackLanguageChange,
  getOrCreateInstallId,
  resetOptOutCache,
  anonymizeEntityName,
  EventCategory,
  EventAction,
} from '../analytics'

interface UmamiWindow extends Window {
  umami?: {
    track: ReturnType<typeof vi.fn>
    identify?: ReturnType<typeof vi.fn>
  }
}

declare const window: UmamiWindow

describe('analytics (umami)', () => {
  beforeEach(() => {
    localStorage.clear()
    window.umami = { track: vi.fn(), identify: vi.fn() }
    vi.spyOn(Storage.prototype, 'getItem')
    vi.spyOn(Storage.prototype, 'setItem')
    global.fetch = vi.fn()
    Object.defineProperty(navigator, 'sendBeacon', {
      value: vi.fn().mockReturnValue(true),
      configurable: true,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    delete window.umami
  })

  describe('getAnalyticsConfig', () => {
    it('returns analytics configuration', () => {
      const config = getAnalyticsConfig()
      expect(config.enabled).toBe(true)
      expect(config.siteId).toBe('870dcd0c-2fa3-4f78-8180-d0d7895c5d8c')
      expect(config.dashboardUrl).toBe('https://analytics.nullcodeai.dev/')
    })
  })

  describe('loadUserPreference', () => {
    it('sets opted-out when no token in JWT mode', async () => {
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
            preferences: { analytics_enabled: true, analytics_consent_given: true },
          }),
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
    })

    it('defaults to opt-out when API fails', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue('test-token')
      global.fetch = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ proxy_auth_enabled: false }),
        } as Response)
        .mockResolvedValueOnce({ ok: false } as Response)

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
            preferences: { analytics_enabled: true, analytics_consent_given: true },
          }),
        } as Response)

      await loadUserPreference()

      expect(arePreferencesLoaded()).toBe(true)
    })
  })

  describe('trackPageView', () => {
    it('does not track when umami is not initialized', () => {
      delete window.umami
      expect(() => trackPageView()).not.toThrow()
    })

    it('does not throw when called', () => {
      expect(() => trackPageView('/dashboard')).not.toThrow()
    })
  })

  describe('trackEvent', () => {
    it('does not throw when called', () => {
      expect(() => trackEvent('Category', 'Action', 'Name', 100)).not.toThrow()
    })

    it('does not throw without optional parameters', () => {
      expect(() => trackEvent('Category', 'Action')).not.toThrow()
    })

    it('does not throw when umami is undefined', () => {
      delete window.umami
      expect(() => trackEvent('Category', 'Action')).not.toThrow()
    })
  })

  describe('trackSiteSearch', () => {
    it('does not throw when called', () => {
      expect(() => trackSiteSearch('query', 'category', 10)).not.toThrow()
    })

    it('does not throw without optional parameters', () => {
      expect(() => trackSiteSearch('query')).not.toThrow()
    })
  })

  describe('no-op functions', () => {
    it('setCustomDimension does not throw', () => {
      expect(() => setCustomDimension(1, 'value')).not.toThrow()
    })

    it('setAppVersion identifies the current app version when umami is available', () => {
      expect(() => setAppVersion('1.2.3')).not.toThrow()
      expect(window.umami?.identify).toHaveBeenCalledWith({ app_version: '1.2.3' })
    })

    it('setUserId does not throw', () => {
      expect(() => setUserId('user123')).not.toThrow()
    })

    it('resetUserId does not throw', () => {
      expect(() => resetUserId()).not.toThrow()
    })
  })

  describe('trackOptOut', () => {
    it('sends a manual event with app version when umami is undefined', () => {
      delete window.umami
      setAppVersion('1.2.3')
      trackOptOut()
      expect(navigator.sendBeacon).toHaveBeenCalled()
      expect(navigator.sendBeacon).toHaveBeenCalledWith(
        'https://cloud.umami.is/api/send',
        expect.stringContaining('"app_version":"1.2.3"')
      )
    })
  })

  describe('trackConsentResponse', () => {
    it('adds app version to tracked consent events', () => {
      setAppVersion('1.2.3')
      trackConsentResponse(true)

      expect(window.umami?.track).toHaveBeenCalledWith('Consent - Accept', {
        name: 'analytics_banner',
        app_version: '1.2.3',
      })
    })

    it('sends a manual event when umami is undefined', () => {
      delete window.umami
      trackConsentResponse(true)
      expect(navigator.sendBeacon).toHaveBeenCalled()
    })
  })

  describe('trackLanguageChange', () => {
    it('does not throw when called', () => {
      expect(() => trackLanguageChange('de')).not.toThrow()
    })
  })

  describe('anonymizeEntityName', () => {
    it('returns empty string for empty input', () => {
      expect(anonymizeEntityName('')).toBe('')
    })

    it('generates consistent hash for same input', () => {
      expect(anonymizeEntityName('my-repo')).toBe(anonymizeEntityName('my-repo'))
    })

    it('generates different hashes for different inputs', () => {
      expect(anonymizeEntityName('repo-1')).not.toBe(anonymizeEntityName('repo-2'))
    })

    it('generates 8-character hex string', () => {
      expect(anonymizeEntityName('test-repository')).toMatch(/^[0-9a-f]{8}$/)
    })

    it('pads hash with leading zeros', () => {
      expect(anonymizeEntityName('a').length).toBe(8)
    })
  })

  describe('getOrCreateInstallId', () => {
    it('creates and stores a new UUID when none exists', () => {
      localStorage.clear()
      vi.spyOn(window.crypto, 'randomUUID').mockReturnValue(
        'test-uuid-1234-5678-abcd-ef0123456789' as `${string}-${string}-${string}-${string}-${string}`
      )

      const id = getOrCreateInstallId()

      expect(id).toBe('test-uuid-1234-5678-abcd-ef0123456789')
      expect(localStorage.getItem('borg_ui_install_id')).toBe(
        'test-uuid-1234-5678-abcd-ef0123456789'
      )
    })

    it('returns existing UUID from localStorage', () => {
      localStorage.clear()
      localStorage.setItem('borg_ui_install_id', 'existing-uuid')
      expect(getOrCreateInstallId()).toBe('existing-uuid')
    })
  })

  describe('resetOptOutCache', () => {
    it('completes without error', async () => {
      Storage.prototype.getItem = vi.fn().mockReturnValue(null)
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ proxy_auth_enabled: false }),
      } as Response)

      await expect(resetOptOutCache()).resolves.toBeUndefined()
    })
  })

  describe('manual transport fallback', () => {
    it('falls back to fetch when sendBeacon is unavailable', async () => {
      vi.resetModules()
      delete window.umami
      Object.defineProperty(navigator, 'sendBeacon', {
        value: undefined,
        configurable: true,
      })
      const fetchMock = vi.fn().mockResolvedValue({ ok: true } as Response)
      global.fetch = fetchMock
      window.fetch = fetchMock as typeof window.fetch

      const analytics = await import('../analytics')
      analytics.trackConsentResponse(false)

      expect(fetchMock).toHaveBeenCalledWith(
        'https://cloud.umami.is/api/send',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          keepalive: true,
        })
      )
    })
  })

  describe('direct Umami events', () => {
    it('tracks opt-out immediately through Umami when available', () => {
      setAppVersion('9.9.9')
      trackOptOut()

      expect(window.umami?.track).toHaveBeenCalledWith('Settings - OptOut', {
        name: 'analytics',
        app_version: '9.9.9',
      })
    })

    it('tracks consent decline through Umami when available', () => {
      setAppVersion('4.5.6')
      trackConsentResponse(false)

      expect(window.umami?.track).toHaveBeenCalledWith('Consent - Decline', {
        name: 'analytics_banner',
        app_version: '4.5.6',
      })
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
      expect(EventCategory.SCRIPT).toBe('Script')
      expect(EventCategory.NOTIFICATION).toBe('Notification')
      expect(EventCategory.SYSTEM).toBe('System')
      expect(EventCategory.PACKAGE).toBe('Package')
      expect(EventCategory.SETTINGS).toBe('Settings')
      expect(EventCategory.AUTH).toBe('Authentication')
      expect(EventCategory.NAVIGATION).toBe('Navigation')
      expect(EventCategory.PLAN).toBe('Plan')
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
