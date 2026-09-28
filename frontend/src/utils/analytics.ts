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
// Under the ingest's 64 KiB body limit, and the browser's 64 KiB budget for all
// keepalive requests in flight at once.
const MAX_BYTES = 60_000
const bytes = (text: string): number => new TextEncoder().encode(text).length

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
// Page views that arrived before tracking was allowed, with where and when they
// happened; sent once preferences allow it.
let pendingPageviews: { path: string; at: string }[] = []
// Consent and opt-out answers given before an install key is known (the preference
// request failed); sent once a later load provides the key.
let pendingForced: { name: string; data?: Props; at: { path: string; at: string } }[] = []

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

// One choke point: any *_name prop, and any value that looks like a path, URL or
// user@host (repository filters, remotes), is hashed here, at any depth, so no call
// site can leak one.
const sensitive = (key: string, value: string): boolean =>
  key.endsWith('_name') || /[/\\@]/.test(value)

const scrubValue = (key: string, value: unknown): unknown => {
  if (typeof value === 'string') return sensitive(key, value) ? anonymizeEntityName(value) : value
  if (Array.isArray(value)) return value.map((item) => scrubValue(key, item))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrubValue(k, v)]))
  }
  return value
}

const scrubProps = (data?: Props): Props | undefined => {
  if (!data) return undefined
  const out = scrubValue('', data) as Props
  return Object.keys(out).length ? out : undefined
}

/**
 * Send everything queued, in batches of at most MAX_BATCH events and MAX_BYTES.
 * `keepalive` lets a send outlive the page (tab hidden, reload right after opt-out);
 * it is only used then, and only while the batches sent so far fit its 64 KiB budget.
 */
export const flushAnalytics = (keepalive = false): void => {
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  let keptBytes = 0
  while (queue.length) {
    let count = 0
    let body = ''
    // At least one event per batch, so an oversized one is still attempted.
    while (count < Math.min(MAX_BATCH, queue.length)) {
      const next = JSON.stringify({ events: queue.slice(0, count + 1) })
      if (count > 0 && bytes(next) > MAX_BYTES) break
      body = next
      count++
    }
    queue.splice(0, count)
    const size = bytes(body)
    const keep = keepalive && keptBytes + size <= MAX_BYTES
    if (keep) keptBytes += size
    // text/plain keeps this a CORS simple request, so self-hosted origins need no preflight.
    // sendBeacon is not used because it cannot suppress the Referer header.
    void fetch(ANALYTICS_ENDPOINT, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'text/plain' },
      keepalive: keep,
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
      if (document.visibilityState === 'hidden') flushAnalytics(true)
    })
  }
  if (!flushTimer) flushTimer = setTimeout(() => flushAnalytics(), FLUSH_MS)
}

const canTrack = (): boolean => preferenceLoaded && userOptedOut === false && !!instanceKey

const enqueue = (
  name: string,
  data?: Props,
  force = false,
  at = { path: window.location.pathname, at: new Date().toISOString() }
): void => {
  if (!instanceKey) {
    if (force && pendingForced.length < MAX_BATCH) pendingForced.push({ name, data, at })
    return
  }
  if (!force && !canTrack()) return
  const props = scrubProps(data)
  queue.push({
    event_id: randomId(),
    occurred_at: at.at,
    source: 'app',
    name,
    session_key: sessionKey,
    instance_key: instanceKey,
    ...(userKey ? { user_key: userKey } : {}),
    path: at.path,
    ...(currentAppVersion ? { app_version: currentAppVersion } : {}),
    ...(currentPlan ? { plan: currentPlan } : {}),
    ...(props ? { props } : {}),
  })
  if (force) flushAnalytics(true)
  else if (queue.length >= MAX_BATCH) flushAnalytics()
  else scheduleFlush()
}

/**
 * Load the user's analytics preference and pseudonymous keys from the API.
 * Called on app startup and after login, before any tracking.
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    await readPreference()
  } finally {
    // Views held before the first load go out now if tracking is allowed, otherwise never.
    const held = pendingPageviews
    pendingPageviews = []
    if (canTrack()) for (const view of held) enqueue('pageview', undefined, false, view)
    if (instanceKey) {
      const forced = pendingForced
      pendingForced = []
      for (const event of forced) enqueue(event.name, event.data, true, event.at)
    }
  }
}

const readPreference = async (): Promise<void> => {
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
  // The first route renders before preferences first load; hold that view (where and when
  // it happened) instead of losing it. Once a preference is known, a view while analytics
  // is off is dropped, even during a reload that turns it on.
  if (!canTrack()) {
    if (!preferenceLoaded && pendingPageviews.length < MAX_BATCH) {
      pendingPageviews.push({ path: window.location.pathname, at: new Date().toISOString() })
    }
    return
  }
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
  // Close the gate now, not when the saved preference reloads: drop anything still
  // queued and send only the opt-out itself.
  userOptedOut = true
  pendingPageviews = []
  queue.length = 0
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
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
