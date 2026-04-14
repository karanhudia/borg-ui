import axios from 'axios'

export function getApiErrorDetail(error: unknown): unknown {
  if (!axios.isAxiosError(error)) {
    return undefined
  }

  return error.response?.data?.detail
}
