/**
 * Umami Analytics Integration
 *
 * Provides tracking functionality for user interactions and events in Borg UI.
 * Uses Umami Cloud (https://umami.is) — privacy-focused, no cookies, GDPR compliant.
 *
 * Website ID is hardcoded as this is a centralized analytics instance for all Borg UI installs.
 * Users can opt-out anytime in Settings → Preferences.
 */

import { BASE_PATH } from './basePath'

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

const identifyWithAppVersion = (): void => {
  if (!currentAppVersion || !window.umami?.identify) return
  window.umami.identify({ app_version: currentAppVersion })
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
  script.addEventListener('load', identifyWithAppVersion)
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
    const authConfigResponse = await fetch(`${BASE_PATH}/api/auth/config`)
    const authConfig = await authConfigResponse.json()
    const proxyAuthEnabled = authConfig.proxy_auth_enabled

    const token = localStorage.getItem('access_token')

    if (!token && !proxyAuthEnabled) {
      userOptedOut = true
      consentGiven = false
      preferenceLoaded = true
      return
    }

    const headers: Record<string, string> = {}
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }

    const response = await fetch(`${BASE_PATH}/api/settings/preferences`, { headers })

    if (response.ok) {
      const data = await response.json()
      userOptedOut = !data.preferences?.analytics_enabled
      consentGiven = data.preferences?.analytics_consent_given ?? false
    } else {
      userOptedOut = true
      consentGiven = false
    }
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
 * Track a page view
 * Umami can auto-track but we call manually to respect the opt-out preference.
 */
export const trackPageView = (customTitle?: string): void => {
  if (!canTrack()) return

  const pageUrl = customTitle || `${window.location.pathname}${window.location.search}`
  window.umami?.track((payload: Record<string, unknown>) => {
    const payloadData =
      payload.data && typeof payload.data === 'object'
        ? (payload.data as Record<string, unknown>)
        : undefined

    return {
      ...payload,
      url: pageUrl,
      data: withAppVersion(payloadData),
    }
  })
}

/**
 * Track a custom event
 * Maps the analytics (category, action, name, value) signature to Umami's track API.
 * Events appear in Umami as "Category - Action" with optional name/value properties.
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

  window.umami?.track(
    `${category} - ${action}`,
    withAppVersion(Object.keys(data).length ? data : undefined)
  )
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
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const setCustomDimension = (_dimensionId: number, _value: string): void => {}

export const setAppVersion = (version: string): void => {
  currentAppVersion = version || null
  identifyWithAppVersion()
}

/**
 * No-op — Umami tracks unique visitors without user IDs.
 * Kept for API compatibility.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const setUserId = (_userId: string): void => {}

/**
 * No-op — Umami tracks unique visitors without user IDs.
 * Kept for API compatibility.
 */
export const resetUserId = (): void => {}

const INSTALL_ID_KEY = 'borg_ui_install_id'

/**
 * Get (or lazily create) a random UUID that uniquely identifies this browser/installation.
 */
export const getOrCreateInstallId = (): string => {
  let id = localStorage.getItem(INSTALL_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(INSTALL_ID_KEY, id)
  }
  return id
}

const sendManualUmamiEvent = (eventName: string, data?: Record<string, unknown>): void => {
  const payload = {
    type: 'event',
    payload: {
      website: UMAMI_WEBSITE_ID,
      url: `${window.location.origin}${window.location.pathname}${window.location.search}`,
      hostname: window.location.hostname,
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
} as const

// Pre-defined event actions
export const EventAction = {
  CREATE: 'Create',
  EDIT: 'Edit',
  DELETE: 'Delete',
  VIEW: 'View',
  START: 'Start',
  STOP: 'Stop',
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
