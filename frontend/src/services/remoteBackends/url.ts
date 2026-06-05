import { BASE_PATH } from '@/utils/basePath'
import type { NormalizedRemoteBackendUrl, RemoteBackendCompatibility } from './types'

export const getLocalApiBaseUrl = (): string => import.meta.env.VITE_API_URL || `${BASE_PATH}/api`

export const getLocalWebBaseUrl = (): string => {
  const localApiBaseUrl = getLocalApiBaseUrl().replace(/\/+$/, '')
  return localApiBaseUrl.endsWith('/api') ? localApiBaseUrl.slice(0, -4) : localApiBaseUrl
}

function isHttpPrivateHost(hostname: string): boolean {
  const normalized = hostname.toLowerCase()
  if (
    normalized === 'localhost' ||
    normalized === '::1' ||
    normalized.endsWith('.local') ||
    normalized.startsWith('127.')
  ) {
    return true
  }

  const octets = normalized.split('.').map((part) => Number(part))
  if (octets.length !== 4 || octets.some((part) => Number.isNaN(part))) {
    return false
  }

  const [first, second] = octets
  return (
    first === 10 ||
    (first === 192 && second === 168) ||
    (first === 172 && second >= 16 && second <= 31)
  )
}

function ensureUrlProtocol(rawInput: string): string {
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(rawInput)) {
    return rawInput
  }

  if (rawInput.startsWith('/')) {
    return rawInput
  }

  const hostPart = rawInput.split(/[/?#]/)[0] ?? ''
  const hostname = hostPart.startsWith('[')
    ? hostPart.slice(1, hostPart.indexOf(']'))
    : hostPart.split(':')[0]
  const protocol = isHttpPrivateHost(hostname) ? 'http' : 'https'
  return `${protocol}://${rawInput}`
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

export function normalizeRemoteBackendUrl(input: string): NormalizedRemoteBackendUrl {
  const trimmed = input.trim()
  if (!trimmed) {
    throw new Error('Enter a backend URL.')
  }

  let url: URL
  try {
    url = new URL(ensureUrlProtocol(trimmed), window.location.origin)
  } catch {
    throw new Error('Enter a valid backend URL.')
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Backend URL must use HTTP or HTTPS.')
  }

  url.hash = ''
  url.search = ''

  const origin = url.origin
  const cleanPath = stripTrailingSlash(url.pathname)
  const apiPath = cleanPath.endsWith('/api') ? cleanPath : `${cleanPath}/api`
  const normalizedApiPath = apiPath === '/api' ? '/api' : apiPath.replace(/\/+/g, '/')
  const webPath = normalizedApiPath.endsWith('/api')
    ? normalizedApiPath.slice(0, -4)
    : normalizedApiPath

  return {
    apiBaseUrl: `${origin}${normalizedApiPath}`,
    webBaseUrl: webPath ? `${origin}${webPath}` : origin,
  }
}

function parseMajorVersion(version: string | null | undefined): number | null {
  if (!version) return null
  const match = version.match(/^v?(\d+)(?:\.|$)/i)
  return match ? Number(match[1]) : null
}

export function compareBackendVersions(
  frontendVersion: string | null | undefined,
  backendVersion: string | null | undefined
): { status: RemoteBackendCompatibility; message: string } {
  if (!backendVersion) {
    return {
      status: 'unknown',
      message: 'Remote backend version is unavailable.',
    }
  }

  const frontendMajor = parseMajorVersion(frontendVersion)
  const backendMajor = parseMajorVersion(backendVersion)

  if (frontendMajor === null || backendMajor === null) {
    return {
      status: 'unknown',
      message: 'Remote backend version could not be compared.',
    }
  }

  if (frontendMajor !== backendMajor) {
    return {
      status: 'incompatible',
      message: `Borg UI ${backendVersion} uses a different major version than this frontend.`,
    }
  }

  return {
    status: 'compatible',
    message: `Borg UI ${backendVersion} is compatible with this frontend.`,
  }
}
