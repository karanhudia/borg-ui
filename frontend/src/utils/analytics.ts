/**
 * Borg UI usage analytics.
 *
 * Events go to the Borg UI ingest service described in docs/trust.md. Nothing is
 * sent before the user's preferences load or after analytics is turned off, except
 * the single consent answer and opt-out events that count those choices. Only
 * paths are sent, never hostnames, query strings or referrers.
 */

import { authAPI } from '../services/api'
import { fetchJsonForAuthMode } from '../services/authRequest'

export const ANALYTICS_ENDPOINT = 'https://t.borgui.com/e'

const FLUSH_MS = 5000
const MAX_BATCH = 50

type Props = Record<string, unknown>

interface OutgoingEvent {
  event_id: string
  occurred_at: string
  source: 'app'
  name: string
  session_key: string
  instance_key: string
  user_key?: string
  path: string
  app_version?: string
  plan?: string
  props?: Props
}

let userOptedOut: boolean | null = null
let consentGiven: boolean | null = null
let preferenceLoaded = false
let instanceKey: string | null = null
let userKey: string | null = null
let currentAppVersion: string | null = null
let currentPlan: string | null = null
const queue: OutgoingEvent[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null
let listening = false

// crypto.randomUUID only exists in secure contexts; plain-HTTP LAN installs still have getRandomValues.
const randomId = (): string => {
  const bytes = new Uint8Array(16)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes)
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const sessionKey = randomId()

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

// One choke point: any *_name prop is hashed here, so no call site can leak a raw name.
const scrubProps = (data?: Props): Props | undefined => {
  if (!data) return undefined
  const out: Props = {}
  for (const [key, value] of Object.entries(data)) {
    out[key] =
      key.endsWith('_name') && typeof value === 'string' ? anonymizeEntityName(value) : value
  }
  return Object.keys(out).length ? out : undefined
}

export const flushAnalytics = (): void => {
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  while (queue.length) {
    const body = JSON.stringify({ events: queue.splice(0, MAX_BATCH) })
    // text/plain keeps this a CORS simple request, so self-hosted origins need no preflight.
    // sendBeacon is not used because it cannot suppress the Referer header.
    void fetch(ANALYTICS_ENDPOINT, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'text/plain' },
      keepalive: true,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
    }).catch(() => {
      // Best-effort analytics transport should never affect the UI.
    })
  }
}

const scheduleFlush = (): void => {
  if (!listening) {
    listening = true
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flushAnalytics()
    })
  }
  if (!flushTimer) flushTimer = setTimeout(flushAnalytics, FLUSH_MS)
}

const canTrack = (): boolean => preferenceLoaded && userOptedOut === false && !!instanceKey

const enqueue = (name: string, data?: Props, force = false): void => {
  if (!instanceKey || (!force && !canTrack())) return
  const props = scrubProps(data)
  queue.push({
    event_id: randomId(),
    occurred_at: new Date().toISOString(),
    source: 'app',
    name,
    session_key: sessionKey,
    instance_key: instanceKey,
    ...(userKey ? { user_key: userKey } : {}),
    path: window.location.pathname,
    ...(currentAppVersion ? { app_version: currentAppVersion } : {}),
    ...(currentPlan ? { plan: currentPlan } : {}),
    ...(props ? { props } : {}),
  })
  if (force || queue.length >= MAX_BATCH) flushAnalytics()
  else scheduleFlush()
}

/**
 * Load the user's analytics preference and pseudonymous keys from the API.
 * Called on app startup and after login, before any tracking.
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    const authConfig = (await authAPI.getAuthConfig()).data
    const proxyAuthEnabled = authConfig.proxy_auth_enabled
    const insecureNoAuthEnabled = authConfig.insecure_no_auth_enabled
    const token = localStorage.getItem('access_token')

    if (!token && !proxyAuthEnabled && !insecureNoAuthEnabled) {
      userOptedOut = true
      consentGiven = false
      preferenceLoaded = true
      return
    }

    const response = await fetchJsonForAuthMode(
      '/settings/preferences',
      {},
      insecureNoAuthEnabled ? 'insecure-no-auth' : proxyAuthEnabled ? 'proxy' : 'jwt'
    )
    const prefs = (await response.json()).preferences ?? {}
    userOptedOut = !prefs.analytics_enabled
    consentGiven = prefs.analytics_consent_given ?? false
    instanceKey = prefs.analytics_instance_key ?? null
    userKey = prefs.analytics_user_key ?? null
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
 * Reload the preference after the user changes it
 */
export const resetOptOutCache = async (): Promise<void> => {
  await loadUserPreference()
}

/**
 * The instance key for buy links, or null when analytics is off
 */
export const getAnalyticsInstanceKey = (): string | null => (canTrack() ? instanceKey : null)

/**
 * Track a page view. Only the path is sent; any query string is dropped.
 */
export const trackPageView = (_path?: string): void => {
  enqueue('pageview')
}

/**
 * Track a custom event as `Category - Action`
 */
export const trackEvent = (
  category: string,
  action: string,
  nameOrData?: string | Record<string, unknown>,
  value?: number
): void => {
  const data: Props = {}
  if (typeof nameOrData === 'string') {
    data.name = nameOrData
  } else if (nameOrData) {
    Object.assign(data, nameOrData)
  }
  if (value !== undefined) data.value = value
  enqueue(`${category} - ${action}`, data)
}

export const setAppVersion = (version: string): void => {
  currentAppVersion = version || null
}

/**
 * Set the effective subscription plan so usage can be compared across plans.
 * Only the plan name is sent, never licence keys or customer details.
 */
export const setAnalyticsPlan = (plan: string | null): void => {
  currentPlan = plan || null
}

/**
 * Track analytics opt-out. Sent once even when analytics is off, so opt-out rates can be counted.
 */
export const trackOptOut = (): void => {
  enqueue('Settings - OptOut', { name: 'analytics' }, true)
}

/**
 * Track language change event
 */
export const trackLanguageChange = (languageCode: string): void => {
  enqueue('Settings - ChangeLanguage', { name: languageCode })
}

/**
 * Track consent banner response. Sent once whatever the answer, so accept and
 * decline rates can be counted.
 */
export const trackConsentResponse = (accepted: boolean): void => {
  enqueue(`Consent - ${accepted ? 'Accept' : 'Decline'}`, { name: 'analytics_banner' }, true)
}

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
  REMOTE_CLIENT: 'Remote Client',
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
  SWITCH: 'Switch',
  FEATURE_USED: 'FeatureUsed',
  FEATURE_BLOCKED: 'FeatureBlocked',
} as const
