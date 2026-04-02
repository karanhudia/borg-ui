import { BASE_PATH } from '@/utils/basePath'

type DownloadParamValue = string | number | boolean | null | undefined

export const API_BASE_URL = import.meta.env.VITE_API_URL || `${BASE_PATH}/api`

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

  const token = localStorage.getItem('access_token')
  if (token) {
    searchParams.set('token', token)
  }

  const query = searchParams.toString()
  return query ? `${API_BASE_URL}${path}?${query}` : `${API_BASE_URL}${path}`
}
