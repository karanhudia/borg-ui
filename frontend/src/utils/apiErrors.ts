import axios from 'axios'
import type { BackendDetail } from './translateBackendKey'

function isBackendDetail(value: unknown): value is Exclude<BackendDetail, null | undefined> {
  if (typeof value === 'string') {
    return true
  }

  return (
    typeof value === 'object' &&
    value !== null &&
    'key' in value &&
    typeof value.key === 'string' &&
    (!('params' in value) ||
      value.params === undefined ||
      (typeof value.params === 'object' && value.params !== null))
  )
}

export function getApiErrorDetail(error: unknown): BackendDetail {
  if (!axios.isAxiosError(error)) {
    return undefined
  }

  const detail = error.response?.data?.detail
  return isBackendDetail(detail) ? detail : undefined
}
