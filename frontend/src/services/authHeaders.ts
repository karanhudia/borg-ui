import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import {
  clearBackendAccessToken,
  getBackendAccessToken,
  setBackendAccessToken,
} from './remoteBackends/storage'

export const AUTH_TOKEN_HEADER = 'X-Borg-Authorization'
export const BACKEND_TARGET_ID_CONFIG_KEY = 'borgUiBackendTargetId'

export interface BackendTargetRequestConfig extends InternalAxiosRequestConfig {
  [BACKEND_TARGET_ID_CONFIG_KEY]?: string
}

export const getAccessToken = (targetId?: string): string | null => getBackendAccessToken(targetId)

export const setAccessToken = (token: string, targetId?: string): void => {
  setBackendAccessToken(token, targetId)
}

export const clearAccessToken = (targetId?: string): void => {
  clearBackendAccessToken(targetId)
}

export const getAccessTokenHeader = (targetId?: string): Record<string, string> | undefined => {
  const token = getAccessToken(targetId)
  if (!token) return undefined
  return {
    [AUTH_TOKEN_HEADER]: `Bearer ${token}`,
  }
}

export const attachAccessTokenHeader = (
  config: InternalAxiosRequestConfig,
  targetId?: string
): InternalAxiosRequestConfig => {
  const header = getAccessTokenHeader(targetId)
  if (!header) return config

  const headers = AxiosHeaders.from(config.headers)
  headers.set(AUTH_TOKEN_HEADER, header[AUTH_TOKEN_HEADER])
  config.headers = headers
  return config
}
