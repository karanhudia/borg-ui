/**
 * Umami Analytics Integration
 *
 * Provides tracking functionality for user interactions and events in Borg UI.
 * Uses Umami Cloud (https://umami.is) — privacy-focused, no cookies, GDPR compliant.
 *
 * Website ID is hardcoded as this is a centralized analytics instance for all Borg UI installs.
 * Users can opt-out anytime in Settings → Preferences.
 */

import { authAPI } from '../services/api'
import { fetchJsonWithAuth } from '../services/authRequest'

const UMAMI_WEBSITE_ID = '870dcd0c-2fa3-4f78-8180-d0d7895c5d8c'
const UMAMI_SCRIPT_URL = 'https://cloud.umami.is/script.js'
const UMAMI_EVENT_URL = 'https://cloud.umami.is/api/send'
export const PUBLIC_ANALYTICS_DASHBOARD_URL = 'https://analytics.nullcodeai.dev/'

interface UmamiWindow extends Window {
  umami?: {
    track: (...args: unknown[]) => void
    identify?: (data: Record<string, unknown>) => void
  }
}

declare const window: UmamiWindow

// Track if Umami has been initialized (script loaded)
let analyticsInitialized = false

// Cache opt-out status and loading state
let userOptedOut: boolean | null = null
let consentGiven: boolean | null = null
let preferenceLoaded = false
let currentAppVersion: string | null = null

const withAppVersion = (data?: Record<string, unknown>): Record<string, unknown> | undefined => {
  if (!currentAppVersion) return data
  return {
    ...(data ?? {}),
    app_version: currentAppVersion,
  }
}

let currentUserId: string | null = null

const identifySession = (): void => {
  if (!window.umami?.identify) return
  const data: Record<string, unknown> = {}
  if (currentUserId) data.user_id = currentUserId
  if (currentAppVersion) data.app_version = currentAppVersion
  if (Object.keys(data).length) window.umami.identify(data)
}

/**
 * Check if tracking is allowed
 */
const canTrack = (): boolean => {
  if (!preferenceLoaded) return false
  return !userOptedOut && !!window.umami
}

/**
 * Initialize Umami script — ONLY if user has not opted out
 */
const initUmamiScript = (): void => {
  if (analyticsInitialized) return

  const script = document.createElement('script')
  script.defer = true
  script.src = UMAMI_SCRIPT_URL
  script.setAttribute('data-website-id', UMAMI_WEBSITE_ID)
  // Disable auto page tracking — we handle it via trackPageView so it respects opt-out
  script.setAttribute('data-auto-track', 'false')
  script.addEventListener('load', identifySession)
  document.head.appendChild(script)

  analyticsInitialized = true
}

/**
 * Initialize analytics ONLY if user has enabled analytics
 * Call this after loadUserPreference() has completed
 */
export const initAnalyticsIfEnabled = (): void => {
  if (!userOptedOut && preferenceLoaded && !analyticsInitialized) {
    initUmamiScript()
  }
}

/**
 * Load user's analytics preference from API
 * Should be called on app startup before any tracking
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    const authConfigResponse = await authAPI.getAuthConfig()
    const authConfig = authConfigResponse.data
    const proxyAuthEnabled = authConfig.proxy_auth_enabled

    const token = localStorage.getItem('access_token')

    if (!token && !proxyAuthEnabled) {
      userOptedOut = true
      consentGiven = false
      preferenceLoaded = true
      return
    }

    const response = await fetchJsonWithAuth('/settings/preferences')
    const data = await response.json()
    userOptedOut = !data.preferences?.analytics_enabled
    consentGiven = data.preferences?.analytics_consent_given ?? false
  } catch {
    userOptedOut = true
    consentGiven = false
  }

  preferenceLoaded = true
}

/**
 * Check if user has given consent (for showing banner)
 */
export const hasConsentBeenGiven = (): boolean | null => {
  return consentGiven
}

/**
 * Check if preferences have been loaded
 */
export const arePreferencesLoaded = (): boolean => {
  return preferenceLoaded
}

/**
 * Builds a masked base payload — replaces the real hostname/URL with app.borgui
 * so self-hosted users' private DNS names or IPs are never sent to Umami.
 */
const maskedPayload = (overrides: Record<string, unknown> = {}): Record<string, unknown> => ({
  hostname: 'app.borgui',
  url: `https://app.borgui${window.location.pathname}${window.location.search}`,
  ...overrides,
})

/**
 * Track a page view.
 * Umami auto-track is disabled — we fire manually to respect opt-out
 * and to mask the real hostname.
 */
export const trackPageView = (path?: string): void => {
  if (!canTrack()) return

  const url = `https://app.borgui${path ?? window.location.pathname + window.location.search}`
  window.umami?.track((payload: Record<string, unknown>) => ({
    ...payload,
    ...maskedPayload({ url }),
    data: withAppVersion(
      payload.data && typeof payload.data === 'object'
        ? (payload.data as Record<string, unknown>)
        : undefined
    ),
  }))
}

/**
 * Track a custom event.
 * Uses the callback form so hostname is masked before the payload leaves the browser.
 */
export const trackEvent = (
  category: string,
  action: string,
  nameOrData?: string | Record<string, unknown>,
  value?: number
): void => {
  if (!canTrack()) return

  const data: Record<string, unknown> = {}
  if (typeof nameOrData === 'string') {
    data.name = nameOrData
  } else if (nameOrData) {
    Object.assign(data, nameOrData)
  }
  if (value !== undefined) data.value = value

  window.umami?.track((payload: Record<string, unknown>) => ({
    ...payload,
    ...maskedPayload(),
    name: `${category} - ${action}`,
    data: withAppVersion(Object.keys(data).length ? data : undefined),
  }))
}

/**
 * Track a site search
 */
export const trackSiteSearch = (
  keyword: string,
  category?: string,
  resultsCount?: number
): void => {
  if (!canTrack()) return

  const data: Record<string, unknown> = { keyword }
  if (category !== undefined) data.category = category
  if (resultsCount !== undefined) data.resultsCount = resultsCount

  window.umami?.track('Site Search', withAppVersion(data))
}

/**
 * No-op — Umami does not use custom dimensions.
 * Kept for API compatibility.
 */
export const setCustomDimension = (_dimensionId: number, _value: string): void => {}

export const setAppVersion = (version: string): void => {
  currentAppVersion = version || null
  identifySession()
}

/**
 * Set a stable anonymous user ID so Umami counts the same user across sessions.
 * Pass the username — it's combined with a per-install UUID and hashed before sending.
 * This mirrors the old Matomo setUserId behaviour.
 */
export const identifyUser = (username: string): void => {
  const installId = getOrCreateInstallId()
  currentUserId = anonymizeEntityName(installId + username)
  identifySession()
}

/**
 * No-op — Umami tracks unique visitors without user IDs.
 * Kept for API compatibility.
 */
export const setUserId = (_userId: string): void => {}

/**
 * No-op — Umami tracks unique visitors without user IDs.
 * Kept for API compatibility.
 */
export const resetUserId = (): void => {}

const INSTALL_ID_KEY = 'borg_ui_install_id'

const getCryptoApi = (): Crypto | undefined => {
  if (typeof globalThis === 'undefined' || !('crypto' in globalThis)) {
    return undefined
  }

  return globalThis.crypto
}

const createUuidFromRandomValues = (randomValues: Uint8Array): string => {
  randomValues[6] = (randomValues[6] & 0x0f) | 0x40
  randomValues[8] = (randomValues[8] & 0x3f) | 0x80

  const hex = Array.from(randomValues, (value) => value.toString(16).padStart(2, '0'))
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-')
}

const generateInstallId = (): string => {
  const cryptoApi = getCryptoApi()

  if (cryptoApi?.randomUUID) {
    return cryptoApi.randomUUID()
  }

  if (cryptoApi?.getRandomValues) {
    return createUuidFromRandomValues(cryptoApi.getRandomValues(new Uint8Array(16)))
  }

  const timestamp = Date.now().toString(16).padStart(12, '0')
  const random = Math.random().toString(16).slice(2).padEnd(20, '0').slice(0, 20)
  return `${random.slice(0, 8)}-${random.slice(8, 12)}-4${random.slice(13, 16)}-a${random.slice(17, 20)}-${timestamp}`
}

/**
 * Get (or lazily create) a random UUID that uniquely identifies this browser/installation.
 */
export const getOrCreateInstallId = (): string => {
  let id = localStorage.getItem(INSTALL_ID_KEY)
  if (!id) {
    id = generateInstallId()
    localStorage.setItem(INSTALL_ID_KEY, id)
  }
  return id
}

const sendManualUmamiEvent = (eventName: string, data?: Record<string, unknown>): void => {
  const payload = {
    type: 'event',
    payload: {
      website: UMAMI_WEBSITE_ID,
      url: `https://app.borgui${window.location.pathname}${window.location.search}`,
      hostname: 'app.borgui',
      language: navigator.language,
      title: document.title,
      name: eventName,
      data: withAppVersion(data),
    },
  }

  const body = JSON.stringify(payload)

  if (navigator.sendBeacon) {
    navigator.sendBeacon(UMAMI_EVENT_URL, body)
    return
  }

  void fetch(UMAMI_EVENT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body,
    keepalive: true,
  }).catch(() => {
    // Best-effort analytics transport should never affect the UI.
  })
}

/**
 * Reset opt-out cache and reload preference
 */
export const resetOptOutCache = async (): Promise<void> => {
  await loadUserPreference()
  initAnalyticsIfEnabled()
}

/**
 * Track analytics opt-out event
 */
export const trackOptOut = (): void => {
  const data = withAppVersion({ name: 'analytics' })

  if (window.umami) {
    window.umami.track('Settings - OptOut', data)
    return
  }

  sendManualUmamiEvent('Settings - OptOut', data)
}

/**
 * Track language change event
 */
export const trackLanguageChange = (languageCode: string): void => {
  if (!canTrack()) return
  window.umami?.track('Settings - ChangeLanguage', withAppVersion({ name: languageCode }))
}

/**
 * Track consent banner response
 */
export const trackConsentResponse = (accepted: boolean): void => {
  const eventName = 'Consent - ' + (accepted ? 'Accept' : 'Decline')
  const data = withAppVersion({ name: 'analytics_banner' })

  if (window.umami) {
    window.umami.track(eventName, data)
    return
  }

  sendManualUmamiEvent(eventName, data)
}

/**
 * Generate anonymous hash for entity names
 */
export const anonymizeEntityName = (name: string): string => {
  if (!name) return ''

  let hash = 5381
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 33) ^ name.charCodeAt(i)
  }

  return (hash >>> 0).toString(16).padStart(8, '0')
}

export const getAnalyticsConfig = () => ({
  url: UMAMI_SCRIPT_URL,
  siteId: UMAMI_WEBSITE_ID,
  dashboardUrl: PUBLIC_ANALYTICS_DASHBOARD_URL,
  enabled: true,
})

// Pre-defined event categories
export const EventCategory = {
  REPOSITORY: 'Repository',
  BACKUP: 'Backup',
  ARCHIVE: 'Archive',
  MOUNT: 'Mount',
  MAINTENANCE: 'Maintenance',
  SSH: 'SSH Connection',
  SCRIPT: 'Script',
  NOTIFICATION: 'Notification',
  SYSTEM: 'System',
  PACKAGE: 'Package',
  SETTINGS: 'Settings',
  AUTH: 'Authentication',
  NAVIGATION: 'Navigation',
  PLAN: 'Plan',
  ANNOUNCEMENT: 'Announcement',
} as const

// Pre-defined event actions
export const EventAction = {
  CREATE: 'Create',
  EDIT: 'Edit',
  DELETE: 'Delete',
  VIEW: 'View',
  START: 'Start',
  STOP: 'Stop',
  COMPLETE: 'Complete',
  FAIL: 'Fail',
  MOUNT: 'Mount',
  UNMOUNT: 'Unmount',
  DOWNLOAD: 'Download',
  UPLOAD: 'Upload',
  TEST: 'Test',
  LOGIN: 'Login',
  LOGOUT: 'Logout',
  SEARCH: 'Search',
  FILTER: 'Filter',
  EXPORT: 'Export',
} as const
