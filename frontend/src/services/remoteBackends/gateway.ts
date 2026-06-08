import { BASE_PATH } from '@/utils/basePath'
import { getBackendTargetTokenParams } from '../authHeaders'
import { getActiveBackendTarget } from './storage'
import type { BackendTarget } from './types'

type ApiParamValue = string | number | boolean | null | undefined

export const API_BASE_URL = import.meta.env.VITE_API_URL || `${BASE_PATH}/api`

export function getApiBaseUrl(target: BackendTarget = getActiveBackendTarget()): string {
  if (target.kind === 'remote') {
    return `${API_BASE_URL}/remote-clients/${encodeURIComponent(target.id)}/proxy/api`
  }
  return target.apiBaseUrl
}

export function buildApiUrl(path: string, params: Record<string, ApiParamValue> = {}): string {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      searchParams.set(key, String(value))
    }
  })

  const query = searchParams.toString()
  const apiBaseUrl = getApiBaseUrl()
  return query ? `${apiBaseUrl}${path}?${query}` : `${apiBaseUrl}${path}`
}

export function buildDownloadUrl(path: string, params: Record<string, ApiParamValue> = {}): string {
  const target = getActiveBackendTarget()
  return buildApiUrl(path, { ...params, ...getBackendTargetTokenParams(target.id) })
}
