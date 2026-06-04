import { API_BASE_URL } from '@/utils/downloadUrl'

const LOCAL_BACKEND_PORT = '8083'

function stripApiSuffix(url: URL): URL {
  const next = new URL(url.toString())
  const path = next.pathname.replace(/\/+$/, '')
  if (path.endsWith('/api')) {
    next.pathname = path.slice(0, -4) || '/'
  }
  next.search = ''
  next.hash = ''
  return next
}

function isRelativeUrl(value: string): boolean {
  return !/^[a-z][a-z\d+.-]*:/i.test(value)
}

function shouldUseDevBackendPort(url: URL, apiBaseUrl: string): boolean {
  return (
    isRelativeUrl(apiBaseUrl) &&
    ['localhost', '127.0.0.1'].includes(url.hostname) &&
    url.port === '7879'
  )
}

export function resolveAgentServerUrl(
  apiBaseUrl = API_BASE_URL,
  browserOrigin = window.location.origin
): string {
  const resolved = stripApiSuffix(new URL(apiBaseUrl, browserOrigin))
  if (shouldUseDevBackendPort(resolved, apiBaseUrl)) {
    resolved.port = LOCAL_BACKEND_PORT
  }
  return resolved.origin + (resolved.pathname === '/' ? '' : resolved.pathname)
}

export function isLocalAgentServerUrl(serverUrl: string): boolean {
  try {
    const url = new URL(serverUrl)
    return ['localhost', '127.0.0.1', '::1'].includes(url.hostname)
  } catch {
    return false
  }
}

export function normalizeAgentServerUrl(serverUrl: string): string {
  const parsed = stripApiSuffix(new URL(serverUrl))
  return parsed.origin + (parsed.pathname === '/' ? '' : parsed.pathname)
}
