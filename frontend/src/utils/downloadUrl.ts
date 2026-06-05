import { BASE_PATH } from '@/utils/basePath'
import { getActiveBackendTarget, getBackendAccessToken } from '@/services/remoteBackends/storage'

type DownloadParamValue = string | number | boolean | null | undefined

export const API_BASE_URL = import.meta.env.VITE_API_URL || `${BASE_PATH}/api`

export function getApiBaseUrl(): string {
  return getActiveBackendTarget().apiBaseUrl
}

export function buildDownloadUrl(
  path: string,
  params: Record<string, DownloadParamValue> = {}
): string {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      searchParams.set(key, String(value))
    }
  })

  const token = getBackendAccessToken()
  if (token) {
    searchParams.set('token', token)
  }

  const query = searchParams.toString()
  const apiBaseUrl = getApiBaseUrl()
  return query ? `${apiBaseUrl}${path}?${query}` : `${apiBaseUrl}${path}`
}
