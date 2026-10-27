/**
 * Error reports for Borg UI's own usage analytics (see docs/trust.md). Builds the
 * `Error - Report` props: scrubbed message and stack, a fingerprint, and flood
 * control. Sending and the opt-out rule live in analytics.ts. Reporting never
 * throws: an error while reporting an error is dropped.
 */

import axios from 'axios'
import { enqueueErrorReport, normalizeRoute } from './analytics'

export type FrontendErrorKind = 'render' | 'uncaught' | 'rejection' | 'api'

export interface ErrorContext {
  kind: FrontendErrorKind
  component?: string
  area?: string
  method?: string
  status?: number
  error_key?: string
}

const MESSAGE_MAX = 500
const TYPE_MAX = 100
const STACK_MAX = 8192
const PROPS_MAX = 16384
const REPEAT_MS = 10 * 60 * 1000
const HOUR_MS = 60 * 60 * 1000
const MAX_PER_HOUR = 30
// ponytail: fingerprints beyond this are reported without folding; raise if it matters
const MAX_TRACKED = 500

const MASK = (1n << 64n) - 1n
const FNV_PRIME = 0x100000001b3n

/** FNV-1a 64-bit over the UTF-8 bytes, as 16 lowercase hex characters. The backend uses the same. */
export const fnv1a64 = (text: string): string => {
  let hash = 0xcbf29ce484222325n
  for (const byte of new TextEncoder().encode(text)) {
    hash = ((hash ^ BigInt(byte)) * FNV_PRIME) & MASK
  }
  return hash.toString(16).padStart(16, '0')
}

// Applied in this order. The backend uses the same patterns.
const NORMALIZERS: [RegExp, string][] = [
  [/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '<uuid>'],
  [/\b0x[0-9a-f]+\b/gi, '<hex>'],
  [/\b[0-9a-f]{8,}\b/gi, '<hex>'],
  [/'[^']*'|"[^"]*"|`[^`]*`/g, '<str>'],
  [/[A-Za-z]:\\\S*|(?<![\w<])\/\S+/g, '<path>'],
  [/\b\d+\b/g, '<n>'],
]

// Keep translation keys in JSON and Python dict reprs before normalizing quoted params.
const STRUCTURED_ERROR_KEY =
  /(['"])key\1\s*:\s*(['"])(backend\.errors\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\2/g
const ERROR_KEY_VALUE = /^backend\.errors\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$/

/** The message with its volatile parts (ids, names, paths, numbers) replaced, for fingerprinting. */
export const normalizeMessage = (message: string): string => {
  const keyed = message.replace(
    STRUCTURED_ERROR_KEY,
    (_match, _quote, _valueQuote, key) => `key: ${key}`
  )
  return NORMALIZERS.reduce((text, [pattern, token]) => text.replace(pattern, token), keyed)
}

const KEYED = [
  'BORG_PASSPHRASE',
  'BORG_NEW_PASSPHRASE',
  'password',
  'passphrase',
  'token',
  'secret_access_key',
  'client_secret',
  'secret',
  'pass',
  'key',
].join('|')

const SCRUBBERS: [RegExp, string][] = [
  [
    /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)/g,
    '[redacted]',
  ],
  [/(Authorization\s*:\s*)[^\r\n]+/gi, '$1[redacted]'],
  [/(Bearer\s+)[\w.~+/=-]+/gi, '$1[redacted]'],
  [
    new RegExp(`(?<![A-Za-z0-9])((?:${KEYED})\\s*=\\s*)(?:"[^"]*"|'[^']*'|\\S+)`, 'gi'),
    '$1[redacted]',
  ],
  // Bare HTTP Basic credentials (base64).
  [/\bBasic\s+[A-Za-z0-9+/_-]{6,}={0,2}/g, 'Basic [redacted]'],
  // camelCase keys (apiKey=, authToken=, clientSecret=); `monkey=1` stays.
  [
    /(?<=[a-z0-9])((?:Key|Token|Secret|Password|Passphrase|Pass)\s*=\s*)(?:"[^"]*"|'[^']*'|\S+)/g,
    '$1[redacted]',
  ],
  [
    /("[\w.-]*(?:Key|Token|Secret|Password|Passphrase)"\s*:\s*)"(?:[^"\\]|\\.)*"/g,
    '$1"[redacted]"',
  ],
]

/** Replace secrets with `[redacted]`. Paths, hostnames and repository names stay. */
export const scrubSecrets = (text: string): string =>
  SCRUBBERS.reduce(
    (out, [pattern, replacement]) => out.replace(pattern, replacement),
    text
  ).replace(
    // A translation code in "key" is public error identity, not a secret key.
    /("(?:[\w.-]*[_.-])?(?:password|passphrase|token|secret|key|pass)"\s*:\s*)"((?:[^"\\]|\\.)*)"/gi,
    (match, prefix: string, value: string) =>
      /^"key"\s*:\s*$/.test(prefix) && ERROR_KEY_VALUE.test(value) ? match : `${prefix}"[redacted]"`
  )

// The function name and file basename of the first stack frame served from this
// origin, without line and column (Chrome `at fn (url:1:2)`, Firefox `fn@url:1:2`).
const topFrame = (stack: string): string => {
  for (const line of stack.split('\n')) {
    const url = /(https?:\/\/[^\s()]+?):\d+(?::\d+)?\)?\s*$/.exec(line)?.[1]
    if (!url || !sameOrigin(url)) continue
    const name = /^\s*at\s+(.+?)\s+\(/.exec(line)?.[1] ?? /^([^@\s]*)@/.exec(line)?.[1] ?? ''
    const file = url.split(/[?#]/)[0].split('/').pop() ?? ''
    return `${name}@${file}`
  }
  return ''
}

const stringify = (value: unknown): string => {
  try {
    return String(value)
  } catch {
    return '[unprintable]'
  }
}

interface Seen {
  lastSent: number
  pending: number
}
// Set once the page is going away: requests aborted by a reload or navigation are not errors.
let unloading = false
const seen = new Map<string, Seen>()
let sentAt: number[] = []

/** Tests only: clear the flood-control state. */
export const resetErrorReporting = (): void => {
  seen.clear()
  sentAt = []
  unloading = false
}

/** The count to send for this fingerprint now, or null when flood control holds it back. */
const admit = (fingerprint: string): number | null => {
  const now = Date.now()
  sentAt = sentAt.filter((at) => now - at < HOUR_MS)
  const entry = seen.get(fingerprint)
  if (entry) entry.pending++
  if (entry && now - entry.lastSent < REPEAT_MS) return null
  if (sentAt.length >= MAX_PER_HOUR) return null
  if (!entry && seen.size >= MAX_TRACKED) seen.clear()
  const count = entry ? entry.pending : 1
  seen.set(fingerprint, { lastSent: now, pending: 0 })
  sentAt.push(now)
  return count
}

// The dev server and browser automation (Playwright in CI) report the released
// version they were built from, so neither sends.
const devOrAutomated = (): boolean =>
  import.meta.env.MODE === 'development' ||
  (typeof navigator !== 'undefined' && navigator.webdriver === true)

/** Report an error to Borg UI's analytics. Never throws. */
export const reportError = (error: unknown, ctx: ErrorContext): void => {
  try {
    if (unloading || devOrAutomated()) return
    const obj =
      typeof error === 'object' && error !== null ? (error as Record<string, unknown>) : null
    const type = (typeof obj?.name === 'string' && obj.name ? obj.name : typeof error).slice(
      0,
      TYPE_MAX
    )
    const message = scrubSecrets(typeof obj?.message === 'string' ? obj.message : stringify(error))
    const rawStack = typeof obj?.stack === 'string' ? obj.stack : ''
    const parts =
      ctx.kind === 'api'
        ? ['api', ctx.method, ctx.area, String(ctx.status ?? 'network'), ctx.error_key ?? '']
        : ['frontend', ctx.kind, type, topFrame(rawStack), normalizeMessage(message)]
    const fingerprint = fnv1a64(parts.join('|'))
    const count = admit(fingerprint)
    if (count === null) return

    const props: Record<string, unknown> = {
      origin: 'frontend',
      kind: ctx.kind,
      type,
      message: message.slice(0, MESSAGE_MAX),
      ...(rawStack ? { stack: scrubSecrets(rawStack).slice(0, STACK_MAX) } : {}),
      fingerprint,
      ...(ctx.component ? { component: ctx.component } : {}),
      ...(ctx.area ? { area: ctx.area } : {}),
      ...(ctx.method ? { method: ctx.method } : {}),
      ...(ctx.status !== undefined ? { status: ctx.status } : {}),
      ...(ctx.error_key ? { error_key: ctx.error_key } : {}),
      route: normalizeRoute(window.location.pathname),
      count,
    }
    if (JSON.stringify(props).length > PROPS_MAX) delete props.stack
    enqueueErrorReport(props)
  } catch {
    // Reporting an error must never cause one.
  }
}

/** A cancelled or aborted request (axios cancel, ERR_CANCELED, fetch AbortError) is not an error. */
export const isCancelled = (reason: unknown): boolean => {
  try {
    const r = reason as { code?: unknown; name?: unknown } | null
    return axios.isCancel(reason) || r?.code === 'ERR_CANCELED' || r?.name === 'AbortError'
  } catch {
    return false
  }
}

// Exact origin match; a look-alike host or an unparsable URL counts as foreign.
const sameOrigin = (url: string): boolean => {
  try {
    return new URL(url, window.location.href).origin === window.location.origin
  } catch {
    return false
  }
}

let installed = false

/** Report uncaught errors and unhandled rejections. Idempotent. */
export const installGlobalErrorHandlers = (): void => {
  if (installed) return
  installed = true
  // pagehide, not beforeunload: a cancelled prompt never hides the page. A bfcache
  // restore fires pageshow, which turns reporting back on.
  window.addEventListener('pagehide', () => {
    unloading = true
  })
  window.addEventListener('pageshow', () => {
    unloading = false
  })
  window.addEventListener('error', (event) => {
    // Cross-origin scripts and browser extensions are not ours.
    if (event.message === 'Script error.') return
    // Browser layout notifications have no exception object. Keep real errors reportable.
    if (
      event.error == null &&
      /^ResizeObserver loop (?:limit exceeded|completed with undelivered notifications)\.?$/.test(
        event.message
      )
    )
      return
    if (event.filename && !sameOrigin(event.filename)) return
    reportError(event.error ?? event.message, { kind: 'uncaught' })
  })
  window.addEventListener('unhandledrejection', (event) => {
    // Axios failures were already reported by trackApiError.
    if (isCancelled(event.reason) || axios.isAxiosError(event.reason)) return
    reportError(event.reason, { kind: 'rejection' })
  })
}
