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

function getResponseDetail(error: unknown): unknown {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return undefined
  }

  const response = error.response
  if (typeof response !== 'object' || response === null || !('data' in response)) {
    return undefined
  }

  const data = response.data
  if (typeof data !== 'object' || data === null || !('detail' in data)) {
    return undefined
  }

  return data.detail
}

export function getApiErrorDetail(error: unknown): BackendDetail {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : getResponseDetail(error)
  return isBackendDetail(detail) ? detail : undefined
}
