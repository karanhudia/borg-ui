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

// Track if Matomo has been initialized (script loaded)
let matomoInitialized = false

/**
 * Initialize Matomo tracking - ONLY if user has not opted out
 * Should be called after user preferences are loaded
 * @internal - Use initMatomoIfEnabled instead for proper preference checking
 */
const initMatomoScript = (): void => {
  const config = getMatomoConfig()

  if (!config.enabled || matomoInitialized) return

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

  // Note: IP anonymization must also be configured server-side in Matomo:
  // Settings → Privacy → Anonymize Visitor IP addresses → Mask 2 bytes

  // Load Matomo script
  const script = document.createElement('script')
  script.async = true
  script.src = `${config.url}/matomo.js`
  document.head.appendChild(script)

  matomoInitialized = true
}

/**
 * Initialize Matomo ONLY if user has enabled analytics
 * Call this after loadUserPreference() has completed
 *
 * PRIVACY: If user has opted out, this does NOTHING - no scripts loaded, no requests made
 */
export const initMatomoIfEnabled = (): void => {
  // Only initialize if user has NOT opted out and script not already loaded
  if (!userOptedOut && preferenceLoaded && !matomoInitialized) {
    initMatomoScript()
  }
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
    // Check if proxy auth is enabled
    const authConfigResponse = await fetch('/api/auth/config')
    const authConfig = await authConfigResponse.json()
    const proxyAuthEnabled = authConfig.proxy_auth_enabled

    const token = localStorage.getItem('access_token')

    // In proxy auth mode, we can fetch preferences without a token
    // In JWT mode, we need a token
    if (!token && !proxyAuthEnabled) {
      // PRIVACY FIRST: No tracking on login page (JWT mode without token)
      // User's opt-out preference is stored server-side (requires auth to fetch)
      // Default to NO tracking until user logs in and we can verify their preference
      userOptedOut = true
      consentGiven = false
      preferenceLoaded = true
      return
    }

    const headers: Record<string, string> = {}
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    // In proxy auth mode without token, the backend will use proxy headers

    const response = await fetch('/api/settings/preferences', {
      headers,
    })

    if (response.ok) {
      const data = await response.json()
      userOptedOut = !data.preferences?.analytics_enabled
      consentGiven = data.preferences?.analytics_consent_given ?? false
    } else {
      // PRIVACY FIRST: If API fails, default to NO tracking
      userOptedOut = true
      consentGiven = false
    }
  } catch {
    // PRIVACY FIRST: On error, default to NO tracking
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
 * If user re-enables analytics, this will initialize Matomo
 */
export const resetOptOutCache = async (): Promise<void> => {
  await loadUserPreference()
  // If user re-enabled analytics, initialize Matomo now
  initMatomoIfEnabled()
}

/**
 * Track analytics opt-out event
 * ONLY sends event if Matomo is already initialized (user was tracking before opting out)
 * Call this BEFORE saving the preference
 *
 * PRIVACY: Does NOT initialize Matomo if not already loaded
 * If user opts out before Matomo loads, no tracking occurs at all
 */
export const trackOptOut = (): void => {
  // Only track if Matomo is already initialized
  // Do NOT initialize Matomo just to send this event
  if (!matomoInitialized || !window._paq) return

  window._paq.push(['trackEvent', 'Settings', 'OptOut', 'analytics'])
}

/**
 * Track consent banner response
 * ONLY sends event if Matomo is already initialized
 * @param accepted - true if user accepted analytics, false if declined
 *
 * PRIVACY: Does NOT initialize Matomo if not already loaded
 */
export const trackConsentResponse = (accepted: boolean): void => {
  // Only track if Matomo is already initialized
  // Do NOT initialize Matomo just to send this event
  if (!matomoInitialized || !window._paq) return

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
