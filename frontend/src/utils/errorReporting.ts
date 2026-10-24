/**
 * Error reports for Borg UI's own usage analytics (see docs/trust.md). Builds the
 * `Error - Report` props: scrubbed message and stack, a fingerprint, and flood
 * control. Sending and the opt-out rule live in analytics.ts. Reporting never
 * throws: an error while reporting an error is dropped.
 */

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
  [/\b[0-9a-f]{8,}\b/gi, '<hex>'],
  [/'[^']*'|"[^"]*"|`[^`]*`/g, '<str>'],
  [/[A-Za-z]:\\\S*|(?<![\w<])\/\S+/g, '<path>'],
  [/\b\d+\b/g, '<n>'],
]

/** The message with its volatile parts (ids, names, paths, numbers) replaced, for fingerprinting. */
export const normalizeMessage = (message: string): string =>
  NORMALIZERS.reduce((text, [pattern, token]) => text.replace(pattern, token), message)

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
  [new RegExp(`(?<!\\w)((?:${KEYED})\\s*=\\s*)(?:"[^"]*"|'[^']*'|\\S+)`, 'gi'), '$1[redacted]'],
]

/** Replace secrets with `[redacted]`. Paths, hostnames and repository names stay. */
export const scrubSecrets = (text: string): string =>
  SCRUBBERS.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text)

// The function name and file basename of the first stack frame served from this
// origin, without line and column (Chrome `at fn (url:1:2)`, Firefox `fn@url:1:2`).
const topFrame = (stack: string): string => {
  for (const line of stack.split('\n')) {
    const url = /(https?:\/\/[^\s()]+?):\d+(?::\d+)?\)?\s*$/.exec(line)?.[1]
    if (!url || !url.startsWith(window.location.origin)) continue
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
const seen = new Map<string, Seen>()
let sentAt: number[] = []

/** Tests only: clear the flood-control state. */
export const resetErrorReporting = (): void => {
  seen.clear()
  sentAt = []
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

/** Report an error to Borg UI's analytics. Never throws. */
export const reportError = (error: unknown, ctx: ErrorContext): void => {
  try {
    const obj =
      typeof error === 'object' && error !== null ? (error as Record<string, unknown>) : null
    const type = typeof obj?.name === 'string' && obj.name ? obj.name : typeof error
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
