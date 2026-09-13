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
    // URL.hostname keeps the brackets on an IPv6 literal, so http://[::1]:8083
    // reports "[::1]" and never matched the bare "::1" this compared against.
    const hostname = new URL(serverUrl).hostname.replace(/^\[|\]$/g, '')
    return ['localhost', '127.0.0.1', '::1'].includes(hostname)
  } catch {
    return false
  }
}

export function normalizeAgentServerUrl(serverUrl: string): string {
  const parsed = stripApiSuffix(new URL(serverUrl))
  return parsed.origin + (parsed.pathname === '/' ? '' : parsed.pathname)
}

/**
 * True when a command that pipes this server's script into a root shell would
 * travel unencrypted across a network someone else can sit on.
 *
 * Loopback is exempt: there is no network path to attack, and a plain HTTP
 * localhost server is the ordinary development and single-host setup.
 */
export function isInsecureCommandUrl(serverUrl: string): boolean {
  try {
    return new URL(serverUrl).protocol === 'http:' && !isLocalAgentServerUrl(serverUrl)
  } catch {
    return false
  }
}
