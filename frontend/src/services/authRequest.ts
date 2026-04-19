import { API_BASE_URL } from '@/utils/downloadUrl'
import { getAccessTokenHeader } from './authHeaders'

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
