import { API_ERROR_ENDPOINTS } from './apiErrorEndpoints'

export type ApiFailureClass =
  'http' | 'timeout' | 'network' | 'configuration' | 'response' | 'unknown'
export interface ApiDiagnostics {
  endpoint: string
  error_class: ApiFailureClass
  request_id?: string
  error_code?: string
  duration_ms?: number
  timeout_ms?: number
}
interface RequestConfig {
  url?: string
  method?: string
  timeout?: number
  analyticsStartedAt?: number
}
interface ApiError {
  code?: string
  config?: RequestConfig
  request?: unknown
  response?: { status?: number; headers?: Record<string, unknown> }
}
const CODES = new Set([
  'ECONNABORTED',
  'ETIMEDOUT',
  'ERR_NETWORK',
  'ERR_BAD_OPTION',
  'ERR_BAD_OPTION_VALUE',
  'ERR_INVALID_URL',
  'ERR_NOT_SUPPORT',
  'ERR_DEPRECATED',
  'ERR_BAD_RESPONSE',
  'ERR_BAD_REQUEST',
  'ERR_FR_TOO_MANY_REDIRECTS',
  'ERR_FORM_DATA_DEPTH_EXCEEDED',
])
const CONFIG_CODES = new Set([
  'ERR_BAD_OPTION',
  'ERR_BAD_OPTION_VALUE',
  'ERR_INVALID_URL',
  'ERR_NOT_SUPPORT',
  'ERR_DEPRECATED',
  'ERR_FORM_DATA_DEPTH_EXCEEDED',
])
const AREAS = new Set(
  API_ERROR_ENDPOINTS.map((path) => path.split('/').filter(Boolean)).map((parts) =>
    parts[0] === 'v2' ? parts[1] : parts[0]
  )
)
const TEMPLATES = API_ERROR_ENDPOINTS.map((template) => ({ template, parts: template.split('/') }))

/** Monotonic time remains local request metadata; only elapsed milliseconds are sent. */
export function markApiRequest<T extends object>(config: T): T {
  Object.assign(config, { analyticsStartedAt: performance.now() })
  return config
}

function endpointTemplate(url?: string): string {
  try {
    const absolute = /^[a-z][a-z0-9+.-]*:/i.test(url ?? '')
    const parts = new URL(url ?? '', 'https://analytics.invalid').pathname
      .split('/')
      .filter(Boolean)
    const api = parts.indexOf('api')
    const route = api >= 0 ? parts.slice(api + 1) : absolute ? [] : parts
    const actual = ['', ...route]
    const match = TEMPLATES.find(({ parts }) => {
      return (
        parts.length === actual.length &&
        parts.every((part, index) => part === ':id' || part === actual[index])
      )
    })
    if (match) return match.template
    const version = route[0] === 'v2' ? '/v2' : ''
    const area = route[version ? 1 : 0]
    return `${version}/${AREAS.has(area) ? area : 'other'}/:unknown`
  } catch {
    return '/other/:unknown'
  }
}

export function apiErrorDiagnostics(error: ApiError): ApiDiagnostics {
  const code = error.code && CODES.has(error.code) ? error.code : undefined
  const status = error.response?.status
  const error_class: ApiFailureClass = CONFIG_CODES.has(code ?? '')
    ? 'configuration'
    : status !== undefined && status >= 400
      ? 'http'
      : code === 'ERR_BAD_RESPONSE' || code === 'ERR_FR_TOO_MANY_REDIRECTS'
        ? 'response'
        : status !== undefined
          ? 'http'
          : code === 'ECONNABORTED' || code === 'ETIMEDOUT'
            ? 'timeout'
            : code === 'ERR_NETWORK' || error.request != null
              ? 'network'
              : 'unknown'
  const started = error.config?.analyticsStartedAt
  const elapsed = typeof started === 'number' ? performance.now() - started : NaN
  const timeout = error.config?.timeout
  const requestId =
    error.response?.headers?.['x-request-id'] ?? error.response?.headers?.['x-correlation-id']
  const safeRequestId =
    typeof requestId === 'string' &&
    /^(?:[0-9a-f]{16,64}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.test(
      requestId
    )
      ? requestId
      : undefined
  return {
    endpoint: endpointTemplate(error.config?.url),
    error_class,
    ...(safeRequestId ? { request_id: safeRequestId } : {}),
    ...(code ? { error_code: code } : {}),
    ...(Number.isFinite(elapsed) && elapsed >= 0 ? { duration_ms: Math.round(elapsed) } : {}),
    ...(typeof timeout === 'number' && Number.isFinite(timeout) && timeout > 0
      ? { timeout_ms: Math.round(timeout) }
      : {}),
  }
}

export function apiFailureMessage(
  method: string,
  diagnostic: ApiDiagnostics,
  status?: number
): string {
  const cause =
    status !== undefined
      ? `HTTP ${status}`
      : {
          timeout: 'request timed out',
          network: 'no response received',
          configuration: 'invalid request configuration',
          response: 'unexpected response',
          unknown: 'request failed',
          http: 'HTTP failure',
        }[diagnostic.error_class]
  return `${method.toUpperCase()} ${diagnostic.endpoint} — ${cause}`
}
