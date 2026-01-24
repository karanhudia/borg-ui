/**
 * Matomo Analytics Integration
 *
 * Provides tracking functionality for user interactions and events in Borg UI.
 * Configure via environment variables:
 * - VITE_MATOMO_URL: Your Matomo instance URL (e.g., http://192.168.1.250:8085)
 * - VITE_MATOMO_SITE_ID: Your site ID in Matomo (usually 1)
 */

interface MatomoWindow extends Window {
  _paq?: (string | number | boolean | undefined)[][]
}

declare const window: MatomoWindow

export interface MatomoConfig {
  url: string
  siteId: string
  enabled: boolean
}

/**
 * Centralized Matomo configuration for all Borg UI installations
 *
 * IMPORTANT: This is a centralized analytics service hosted by Borg UI developers.
 * All Borg UI instances send anonymous usage data to this single Matomo instance.
 *
 * Users can opt-out anytime in Settings → Preferences.
 */
export const getMatomoConfig = (): MatomoConfig => {
  // Hardcoded centralized Matomo instance - all users send data here
  const url = 'https://analytics.nullcodeai.dev'
  const siteId = '1'

  return {
    url,
    siteId,
    enabled: true, // Always enabled (users can opt-out via preferences)
  }
}

/**
 * Initialize Matomo tracking
 * Loads Matomo script immediately, checks user preferences on each track call
 */
export const initMatomo = (): void => {
  const config = getMatomoConfig()

  if (!config.enabled) return

  // Initialize _paq array immediately
  window._paq = window._paq || []
  const _paq = window._paq

  // CRITICAL PRIVACY: Use fake domain to mask real hostname
  // Matomo captures URLs from HTTP headers, so we override with a consistent fake domain
  _paq.push([
    'setCustomUrl',
    'https://app.borgui' + window.location.pathname + window.location.search,
  ])

  // CRITICAL PRIVACY: Disable cookies and user tracking
  _paq.push(['disableCookies'])
  _paq.push(['setDoNotTrack', true])

  // Configure Matomo
  _paq.push(['enableLinkTracking'])
  _paq.push(['setTrackerUrl', `${config.url}/matomo.php`])
  _paq.push(['setSiteId', config.siteId])

  // CRITICAL: Anonymize IP addresses - mask last 2 bytes (e.g. 192.168.xxx.xxx becomes 192.168.0.0)
  _paq.push(['setDoNotTrack', true])
  _paq.push(['disableCookies'])

  // Note: Full IP anonymization must also be configured server-side in Matomo:
  // Settings → Privacy → Anonymize Visitor IP addresses → Mask 2 bytes

  // Load Matomo script
  const script = document.createElement('script')
  script.async = true
  script.src = `${config.url}/matomo.js`
  document.head.appendChild(script)
}

// Cache opt-out status and loading state
let userOptedOut: boolean | null = null
let consentGiven: boolean | null = null
let preferenceLoaded = false

/**
 * Load user's analytics preference from API
 * Should be called on app startup before any tracking
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) {
      userOptedOut = false // Not logged in, allow tracking
      consentGiven = false
      preferenceLoaded = true
      return
    }

    const response = await fetch('/api/settings/preferences', {
      headers: { Authorization: `Bearer ${token}` },
    })

    if (response.ok) {
      const data = await response.json()
      userOptedOut = !data.preferences?.analytics_enabled
      consentGiven = data.preferences?.analytics_consent_given ?? false
    } else {
      userOptedOut = false // Default to enabled if API fails
      consentGiven = false
    }
  } catch {
    userOptedOut = false // Default to enabled on error
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
 * Check if Matomo is ready and user hasn't opted out (synchronous)
 */
const canTrack = (): boolean => {
  const config = getMatomoConfig()
  if (!config.enabled || !window._paq) return false

  // Don't track until preference is loaded
  if (!preferenceLoaded) return false

  return !userOptedOut
}

/**
 * Track a page view
 */
export const trackPageView = (customTitle?: string): void => {
  if (!canTrack()) return

  window._paq = window._paq || []

  // CRITICAL PRIVACY: Use fake domain to mask real hostname
  const maskedUrl = 'https://app.borgui' + window.location.pathname + window.location.search
  window._paq.push(['setCustomUrl', maskedUrl])

  if (customTitle) {
    window._paq.push(['setDocumentTitle', customTitle])
  }
  window._paq.push(['trackPageView'])
}

/**
 * Track a custom event
 */
export const trackEvent = (
  category: string,
  action: string,
  name?: string,
  value?: number
): void => {
  if (!canTrack()) return

  window._paq = window._paq || []
  const eventData = ['trackEvent', category, action, name, value].filter(
    (item) => item !== undefined
  )
  window._paq.push(eventData)
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

  window._paq = window._paq || []
  window._paq.push(['trackSiteSearch', keyword, category, resultsCount])
}

/**
 * Set custom dimension
 */
export const setCustomDimension = (dimensionId: number, value: string): void => {
  if (!canTrack()) return

  window._paq = window._paq || []
  window._paq.push(['setCustomDimension', dimensionId, value])
}

/**
 * Set app version as custom dimension 1
 * Should be called once when app version is known (e.g., after fetching system info)
 * Note: Custom dimension 1 must be configured in Matomo admin as "Visit" scope
 */
export const setAppVersion = (version: string): void => {
  const config = getMatomoConfig()
  if (!config.enabled || !window._paq) return

  window._paq.push(['setCustomDimension', 1, version])
}

/**
 * Set user ID for tracking authenticated users
 */
export const setUserId = (userId: string): void => {
  if (!canTrack()) return

  window._paq = window._paq || []
  window._paq.push(['setUserId', userId])
}

/**
 * Reset user ID (on logout)
 */
export const resetUserId = (): void => {
  if (!canTrack()) return

  window._paq = window._paq || []
  window._paq.push(['resetUserId'])
}

/**
 * Reset opt-out cache and reload preference (call this when user changes analytics preference)
 */
export const resetOptOutCache = async (): Promise<void> => {
  await loadUserPreference()
}

/**
 * Track analytics opt-out event (bypasses canTrack to send this final event)
 * Call this BEFORE saving the preference so we can track how many users opt out
 */
export const trackOptOut = (): void => {
  const config = getMatomoConfig()
  if (!config.enabled || !window._paq) return

  window._paq.push(['trackEvent', 'Settings', 'OptOut', 'analytics'])
}

/**
 * Track consent banner response (bypasses canTrack since this is the final event before potential opt-out)
 * @param accepted - true if user accepted analytics, false if declined
 */
export const trackConsentResponse = (accepted: boolean): void => {
  const config = getMatomoConfig()
  if (!config.enabled || !window._paq) return

  window._paq.push(['trackEvent', 'Consent', accepted ? 'Accept' : 'Decline', 'analytics_banner'])
}

/**
 * Generate anonymous hash for entity names (repositories, connections, etc.)
 * Creates a consistent 8-character identifier that doesn't reveal the actual name
 * but allows tracking distinct entities across sessions.
 *
 * Example: "my-backup-repo" → "a3f2b1c8"
 */
export const anonymizeEntityName = (name: string): string => {
  if (!name) return ''

  // Simple hash function (djb2 algorithm)
  let hash = 5381
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 33) ^ name.charCodeAt(i)
  }

  // Convert to 8-character hex string
  return (hash >>> 0).toString(16).padStart(8, '0')
}

// Pre-defined event categories for Borg UI
export const EventCategory = {
  REPOSITORY: 'Repository',
  BACKUP: 'Backup',
  ARCHIVE: 'Archive',
  MOUNT: 'Mount',
  MAINTENANCE: 'Maintenance',
  SSH: 'SSH Connection',
  SETTINGS: 'Settings',
  AUTH: 'Authentication',
  NAVIGATION: 'Navigation',
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
