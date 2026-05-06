import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'

export const AUTH_TOKEN_HEADER = 'X-Borg-Authorization'

export const getAccessToken = (): string | null => localStorage.getItem('access_token')

export const getAccessTokenHeader = (): Record<string, string> | undefined => {
  const token = getAccessToken()
  if (!token) return undefined
  return {
    [AUTH_TOKEN_HEADER]: `Bearer ${token}`,
  }
}

export const attachAccessTokenHeader = (
  config: InternalAxiosRequestConfig
): InternalAxiosRequestConfig => {
  const header = getAccessTokenHeader()
  if (!header) return config

  const headers = AxiosHeaders.from(config.headers)
  headers.set(AUTH_TOKEN_HEADER, header[AUTH_TOKEN_HEADER])
  config.headers = headers
  return config
}
