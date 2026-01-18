/**
 * Matomo Analytics Integration
 *
 * Provides tracking functionality for user interactions and events in Borg UI.
 * Configure via environment variables:
 * - VITE_MATOMO_URL: Your Matomo instance URL (e.g., http://192.168.1.250:8085)
 * - VITE_MATOMO_SITE_ID: Your site ID in Matomo (usually 1)
 */

interface MatomoWindow extends Window {
  _paq?: any[]
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
let preferenceLoaded = false

/**
 * Load user's analytics preference from API
 * Should be called on app startup before any tracking
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    const token = localStorage.getItem('token')
    if (!token) {
      userOptedOut = false // Not logged in, allow tracking
      preferenceLoaded = true
      return
    }

    const response = await fetch('/api/settings/preferences', {
      headers: { Authorization: `Bearer ${token}` },
    })

    if (response.ok) {
      const data = await response.json()
      userOptedOut = !data.preferences?.analytics_enabled
    } else {
      userOptedOut = false // Default to enabled if API fails
    }
  } catch (error) {
    userOptedOut = false // Default to enabled on error
  }

  preferenceLoaded = true
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
