/**
 * Borg UI usage analytics.
 *
 * Events go to the Borg UI ingest service described in docs/trust.md. Nothing is
 * sent before the user's preferences load or after analytics is turned off, except
 * the single consent answer and opt-out events that count those choices. Events
 * carry only paths, never hostnames, query strings or referrers. Error reports
 * (see errorReporting.ts) also go through this tracker and stop with it; they can
 * contain paths, hostnames and repository names, with secrets removed.
 */

import { authAPI } from '../services/api'
import { fetchJsonForAuthMode } from '../services/authRequest'
import { BASE_PATH } from './basePath'
import { randomUuid } from './uuid'
import { isCancelled, reportError } from './errorReporting'

export const ANALYTICS_ENDPOINT = 'https://t.borgui.com/e'

const FLUSH_MS = 5000
const MAX_BATCH = 50
// Under the ingest's 64 KiB body limit, and the browser's 64 KiB budget for all
// keepalive requests in flight at once.
const MAX_BYTES = 60_000
const bytes = (text: string): number => new TextEncoder().encode(text).length
// The ingest drops an event whose props serialize to more than this.
const PROPS_MAX = 2048

type Props = Record<string, unknown>

interface OutgoingEvent {
  event_id: string
  occurred_at: string
  source: 'app'
  name: string
  session_key: string
  // Only error reports may go without one (see enqueueErrorReport).
  instance_key?: string
  user_key?: string
  path: string
  app_version?: string
  plan?: string
  props?: Props
}

let userOptedOut: boolean | null = null
let consentGiven: boolean | null = null
let preferenceLoaded = false
// True only when the preference loaded and said no. A logged out user, a preference
// that is not loaded yet or one that failed to load is not a no (see enqueueErrorReport).
let analyticsDeclined = false
let instanceKey: string | null = null
let userKey: string | null = null
let currentAppVersion: string | null = import.meta.env.VITE_APP_VERSION?.trim() || null
let currentPlan: string | null = null
const queue: OutgoingEvent[] = []
const retryTimers = new Set<ReturnType<typeof setTimeout>>()
let deliveryGeneration = 0
const MAX_ATTEMPTS = 3
const REQUEST_TIMEOUT_MS = 10_000
const MAX_EVENT_AGE_MS = 60_000
const MAX_IN_FLIGHT_BATCHES = 4
const activeDeliveries = new Set<AbortController>()

const cancelRetries = (): void => {
  deliveryGeneration++
  for (const timer of retryTimers) clearTimeout(timer)
  retryTimers.clear()
  for (const controller of activeDeliveries) controller.abort()
  activeDeliveries.clear()
}

const validKey = (key: unknown): string | null =>
  typeof key === 'string' && /^[a-f0-9]{64}$/.test(key) ? key : null
// Bytes of keepalive sends not yet settled, across flushes: the browser's budget is shared.
let keepaliveBytes = 0
let flushTimer: ReturnType<typeof setTimeout> | null = null
let listening = false
// Page views that arrived before tracking was allowed, with where and when they
// happened; sent once preferences allow it.
let pendingPageviews: { path: string; at: string }[] = []
// Consent and opt-out answers given before an install key is known (the preference
// request failed); sent once a later load provides the key.
let pendingForced: { name: string; data?: Props; at: { path: string; at: string } }[] = []

// Error reports that arrived before the first preference load settled.
let heldErrorReports: Props[] = []
let errorHoldTimer: ReturnType<typeof setTimeout> | null = null
let errorHoldOver = false
const ERROR_HOLD_MAX = 20
const ERROR_HOLD_MS = 5000
// The ingest accepts this much for an error report's props (2 KB for other events).
const ERROR_PROPS_MAX = 16384

const sessionKey = randomUuid()

/**
 * The route a path belongs to: no deployment base path, and every segment that is
 * not a plain lowercase word (an id, an `aid:` selector) replaced with `:id`, so
 * paths group by page and carry nothing that identifies a repository or archive.
 */
// Routes with ids (App.tsx): how many segments after the root are ids, even when a
// value looks like a plain word, and the only words allowed after them.
const ID_ROUTES: Record<string, { ids: number; after: ReadonlySet<string> }> = {
  archives: { ids: 2, after: new Set() }, // /archives/:repositoryId/:archiveId
  repositories: { ids: 1, after: new Set(['prune-preview']) }, // /repositories/:id/prune-preview
}

// The app's top-level routes (App.tsx). Any other path is sent as `/:other`, so a
// typed or stale URL can never carry a word that is really a name. A test checks
// this list against App.tsx.
export const KNOWN_ROUTE_ROOTS: ReadonlySet<string> = new Set([
  'activity',
  'archives',
  'backup',
  'backup-plans',
  'cloud-storage',
  'connections',
  'dashboard',
  'integrity',
  'login',
  'managed-agents',
  'remote-clients',
  'repositories',
  'restore',
  'schedule',
  'scripts',
  'settings',
  'ssh-connections',
  'ssh-keys',
])

// The only words kept one level below a root: Settings tabs and Schedule views.
// A test checks these against Settings.tsx and Schedule.tsx.
export const ROUTE_WORDS: Record<string, ReadonlySet<string>> = {
  settings: new Set([
    'account',
    'activity',
    'appearance',
    'background-work',
    'beta',
    'cache',
    'export',
    'licensing',
    'logs',
    'monitoring',
    'mounts',
    'mqtt',
    'notifications',
    'packages',
    'preferences',
    'scripts',
    'system',
    'users',
  ]),
  schedule: new Set(['backups', 'by-plan', 'checks', 'restore-checks']),
}

export const normalizeRoute = (pathname: string): string => {
  const path =
    BASE_PATH && (pathname === BASE_PATH || pathname.startsWith(`${BASE_PATH}/`))
      ? pathname.slice(BASE_PATH.length) || '/'
      : pathname
  const segments = path.split('/')
  if (segments[1] && !KNOWN_ROUTE_ROOTS.has(segments[1])) return '/:other'
  const idRoute = ID_ROUTES[segments[1]]
  return segments
    .map((segment, index) => {
      if (!segment || index === 1) return segment
      if (idRoute) {
        if (index < 2 + idRoute.ids) return ':id'
        // Only the route's own word right after its ids; anything else is no route of ours.
        return index === 2 + idRoute.ids && idRoute.after.has(segment) ? segment : ':id'
      }
      // Other routes keep only a known Settings tab or Schedule view below the root.
      return index === 2 && ROUTE_WORDS[segments[1]]?.has(segment) ? segment : ':id'
    })
    .join('/')
}

const currentRoute = (): string => normalizeRoute(window.location.pathname)

interface ErrorLike {
  isAxiosError?: boolean
  code?: string
  config?: { method?: string; url?: string }
  response?: { status?: number; data?: { detail?: unknown } }
}

/**
 * A coarse class for a failure, from its HTTP status or transport code only. Error
 * messages are never sent: they carry paths, hostnames and repository names.
 */
export const errorClass = (error: unknown): string => {
  const err = error as ErrorLike | null
  if (!err?.isAxiosError) return 'unknown'
  const status = err.response?.status
  if (!status)
    return err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT' ? 'timeout' : 'network'
  if (status === 400 || status === 422) return 'validation'
  if (status === 401) return 'auth'
  if (status === 403) return 'permission'
  if (status === 404) return 'not_found'
  if (status === 409) return 'conflict'
  if (status === 429) return 'rate_limited'
  if (status >= 500) return 'server'
  return 'client'
}

/**
 * Props for the outcome of a connection test: a failure always carries a class,
 * `check_failed` when the request worked but the test itself reported failure.
 */
export const testResult = (success: boolean, error?: unknown): Record<string, unknown> =>
  success
    ? { success: true }
    : { success: false, error_class: error === undefined ? 'check_failed' : errorClass(error) }

// The API area a request belongs to: its first path segment after any version
// prefix, which is a fixed route name. Never the rest, which can hold names.
const apiArea = (url?: string): string => {
  const raw = url ?? ''
  const absolute = /^[a-z][a-z0-9+.-]*:/i.test(raw)
  let pathname = ''
  try {
    pathname = new URL(raw, 'http://x').pathname
  } catch {
    return 'other'
  }
  const segments = pathname.split('/').filter(Boolean)
  // A relative URL is already under the API base. An absolute one may carry a
  // deployment base path first, so its area is whatever follows `api`.
  const apiIndex = segments.indexOf('api')
  const rest = apiIndex >= 0 ? segments.slice(apiIndex + 1) : absolute ? [] : segments
  const first = rest[0] === 'v2' ? rest[1] : rest[0]
  return first && /^[a-z][a-z0-9_-]*$/.test(first) ? first : 'other'
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
  if (!Object.keys(out).length) return undefined
  // Rather than lose the whole event at the ingest, send it without its details.
  return JSON.stringify(out).length > PROPS_MAX ? { props_truncated: true } : out
}

/**
 * Send everything queued, in batches of at most MAX_BATCH events and MAX_BYTES.
 * `keepalive` lets a send outlive the page (tab hidden, reload right after opt-out);
 * it is only used then, and only while unsettled keepalive sends fit its 64 KiB budget.
 */
export const flushAnalytics = (keepalive = false): void => {
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  while (queue.length) {
    let count = 0
    // At least one event per batch; props are capped, so any single event fits.
    while (count < Math.min(MAX_BATCH, queue.length)) {
      const next = JSON.stringify({ events: queue.slice(0, count + 1) })
      if (count > 0 && bytes(next) > MAX_BYTES) break
      count++
    }
    sendBatch(queue.splice(0, count), keepalive)
  }
}

// Retry transient failures in memory only, with stable event ids for ingest deduplication.
// Withdrawing consent invalidates both scheduled retries and failures still in flight.
const sendBatch = (
  events: OutgoingEvent[],
  keepalive: boolean,
  attempt = 1,
  generation = deliveryGeneration
): void => {
  if (generation !== deliveryGeneration || activeDeliveries.size >= MAX_IN_FLIGHT_BATCHES) return
  events = events.filter((event) => Date.now() - Date.parse(event.occurred_at) <= MAX_EVENT_AGE_MS)
  if (!events.length) return
  const controller = new AbortController()
  activeDeliveries.add(controller)
  const body = JSON.stringify({ events })
  const size = bytes(body)
  const keep = keepalive && keepaliveBytes + size <= MAX_BYTES
  if (keep) keepaliveBytes += size
  const retry = (): void => {
    if (
      generation !== deliveryGeneration ||
      attempt >= MAX_ATTEMPTS ||
      retryTimers.size >= MAX_BATCH
    )
      return
    const timer = setTimeout(
      () => {
        retryTimers.delete(timer)
        if (generation === deliveryGeneration) sendBatch(events, false, attempt + 1, generation)
      },
      1000 * 2 ** (attempt - 1)
    )
    retryTimers.add(timer)
  }
  // text/plain avoids preflight; referrers and credentials must never accompany analytics.
  // Race the request deadline too: an abort-ignoring transport must not retain a slot forever.
  const deadline = new Promise<never>((_, reject) => {
    controller.signal.addEventListener('abort', () => reject(new Error('Analytics send ended')), {
      once: true,
    })
  })
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  void Promise.race([
    fetch(ANALYTICS_ENDPOINT, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'text/plain' },
      keepalive: keep,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      signal: controller.signal,
    }),
    deadline,
  ])
    .then((response) => {
      if (response.status === 408 || response.status === 429 || response.status >= 500) retry()
    })
    .catch(retry)
    .finally(() => {
      clearTimeout(timeout)
      activeDeliveries.delete(controller)
      if (keep) keepaliveBytes -= size
    })
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
  at = { path: currentRoute(), at: new Date().toISOString() }
): void => {
  if (!instanceKey) {
    if (force && pendingForced.length < MAX_BATCH) pendingForced.push({ name, data, at })
    return
  }
  if (!force && !canTrack()) return
  const props = scrubProps(data)
  queue.push({
    event_id: randomUuid(),
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

const sendErrorReport = (props: Props): void => {
  if (analyticsDeclined || JSON.stringify(props).length > ERROR_PROPS_MAX) return
  queue.push({
    event_id: randomUuid(),
    occurred_at: new Date().toISOString(),
    source: 'app',
    name: 'Error - Report',
    session_key: sessionKey,
    ...(instanceKey ? { instance_key: instanceKey } : {}),
    ...(userKey ? { user_key: userKey } : {}),
    path: currentRoute(),
    ...(currentAppVersion ? { app_version: currentAppVersion } : {}),
    ...(currentPlan ? { plan: currentPlan } : {}),
    props,
  })
  if (queue.length >= MAX_BATCH) flushAnalytics()
  else scheduleFlush()
}

// A no also withdraws reports already queued, not just the held ones.
const dropErrorReports = (): void => {
  heldErrorReports = []
  for (let i = queue.length - 1; i >= 0; i--)
    if (queue[i].name === 'Error - Report') queue.splice(i, 1)
}

// The first preference load settled, or the wait ran out: send what was held.
const releaseErrorReports = (): void => {
  errorHoldOver = true
  if (errorHoldTimer) clearTimeout(errorHoldTimer)
  errorHoldTimer = null
  const held = heldErrorReports
  heldErrorReports = []
  for (const props of held) sendErrorReport(props)
}

/**
 * Queue an error report. Unlike other events it is sent unless the user said no
 * (preferences loaded with analytics off): logged out or not yet loaded is not a no,
 * and without a known install key it goes without one. Reports from before the first
 * preference load wait for it, at most 5 seconds and 20 of them. No `scrubProps`:
 * the caller has already scrubbed secrets, and paths and hosts are wanted here.
 */
export const enqueueErrorReport = (props: Props): void => {
  if (errorHoldOver) return sendErrorReport(props)
  if (heldErrorReports.length < ERROR_HOLD_MAX) heldErrorReports.push(props)
  if (!errorHoldTimer) errorHoldTimer = setTimeout(releaseErrorReports, ERROR_HOLD_MS)
}

/**
 * Load the user's analytics preference and pseudonymous keys from the API.
 * Called on app startup and after login, before any tracking.
 */
export const loadUserPreference = async (): Promise<void> => {
  try {
    await readPreference()
  } finally {
    if (userOptedOut) {
      queue.length = 0
      cancelRetries()
    }
    if (analyticsDeclined) dropErrorReports()
    releaseErrorReports()
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
  const generation = deliveryGeneration
  try {
    const authConfig = (await authAPI.getAuthConfig()).data
    if (generation !== deliveryGeneration) return
    const proxyAuthEnabled = authConfig.proxy_auth_enabled
    const insecureNoAuthEnabled = authConfig.insecure_no_auth_enabled
    const token = localStorage.getItem('access_token')

    if (!token && !proxyAuthEnabled && !insecureNoAuthEnabled) {
      userOptedOut = true
      analyticsDeclined = false
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
    // A response begun before an explicit decline must not reopen the tracking gate.
    if (generation !== deliveryGeneration) return
    userOptedOut = !prefs.analytics_enabled
    analyticsDeclined = prefs.analytics_enabled === false
    consentGiven = prefs.analytics_consent_given ?? false
    instanceKey = validKey(prefs.analytics_instance_key)
    userKey = validKey(prefs.analytics_user_key)
  } catch {
    if (generation !== deliveryGeneration) return
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
      pendingPageviews.push({ path: currentRoute(), at: new Date().toISOString() })
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

type PlanDetail = { key?: string; feature?: string; required?: string; current?: string }

// The backend sends a detail as an object, a key string or a JSON string (see
// getBackendErrorKey in services/api.ts).
const planDetail = (detail: unknown): PlanDetail | undefined => {
  if (typeof detail !== 'string') return (detail as PlanDetail | null) ?? undefined
  if (!detail.startsWith('{')) return { key: detail }
  try {
    return JSON.parse(detail) as PlanDetail
  } catch {
    return undefined
  }
}

/**
 * Called by the API clients for every failed request. A plan gate the backend
 * refused is a blocked feature like any in the UI; any other failed change (not a
 * read, not an expired session) is `API - Fail` with its area, method and class.
 */
export const trackApiError = (error: unknown): void => {
  const err = error as ErrorLike
  const detail = planDetail(err?.response?.data?.detail)
  const area = apiArea(err?.config?.url)
  if (typeof detail?.key === 'string' && detail.key.startsWith('backend.errors.plan.')) {
    trackEvent(EventCategory.PLAN, EventAction.FEATURE_BLOCKED, {
      // Every refusal names its feature; 'unknown' keeps an old backend's countable.
      feature: detail.feature ?? 'unknown',
      required_plan: detail.required,
      current_plan: detail.current,
      allowed: false,
      surface: 'api',
      operation: area,
      gate_mode: 'api_error',
    })
    return
  }
  const method = err?.config?.method?.toLowerCase()
  const status = err?.response?.status
  // Backend translation keys identify a failure without copying private params.
  const key = detail?.key
  const errorKey =
    typeof key === 'string' &&
    key.length <= 160 &&
    /^backend\.errors\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$/.test(key)
      ? key.slice('backend.errors.'.length)
      : undefined
  // 5xx are reported by the backend itself.
  if (method && !isCancelled(error) && !(status !== undefined && status >= 500)) {
    reportError(error, {
      kind: 'api',
      area,
      method,
      ...(status !== undefined ? { status } : {}),
      ...(errorKey ? { error_key: errorKey } : {}),
    })
  }
  if (!method || method === 'get' || method === 'head' || err.response?.status === 401) return
  trackEvent(EventCategory.API, EventAction.FAIL, {
    area,
    method,
    ...(err.response?.status ? { status: err.response.status } : {}),
    error_class: errorClass(error),
    ...(errorKey ? { error_key: errorKey } : {}),
  })
}

export const setAppVersion = (version: string): void => {
  const knownVersion = version?.trim()
  if (!knownVersion) return
  currentAppVersion = knownVersion
  for (const event of queue) {
    if (!event.app_version) event.app_version = knownVersion
  }
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
  analyticsDeclined = true
  cancelRetries()
  heldErrorReports = []
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
  // A decline closes the gate now, so a failed preference reload cannot release held reports.
  if (!accepted) {
    userOptedOut = true
    analyticsDeclined = true
    pendingPageviews = []
    queue.length = 0
    cancelRetries()
    dropErrorReports()
  }
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
  QUICK_START: 'Quick Start',
  WIZARD: 'Wizard',
  API: 'API',
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
  CANCEL: 'Cancel',
} as const
