import { API_BASE_URL } from '@/utils/downloadUrl'
import { getAccessTokenHeader } from './authHeaders'
import type { AuthTransportMode } from './api'

let authTransportMode: AuthTransportMode = 'jwt'

export const setFetchAuthMode = (mode: AuthTransportMode) => {
  authTransportMode = mode
}

export const fetchWithAuth = (
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> => {
  const headers = new Headers(init.headers)
  const authHeader = getAccessTokenHeader()

  if (authHeader) {
    for (const [key, value] of Object.entries(authHeader)) {
      headers.set(key, value)
    }
  }

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  return fetch(input, {
    ...init,
    headers,
  })
}

export const fetchJsonWithAuth = (path: string, init: RequestInit = {}): Promise<Response> =>
  fetchWithAuth(`${API_BASE_URL}${path}`, init)

export const fetchJsonForAuthMode = (
  path: string,
  init: RequestInit = {},
  mode: AuthTransportMode = authTransportMode
): Promise<Response> => {
  if (mode === 'jwt') {
    return fetchJsonWithAuth(path, init)
  }

  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })
}
