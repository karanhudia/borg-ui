import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import {
  LOCAL_BACKEND_ID,
  clearBackendAccessToken,
  getBackendAccessToken,
  setBackendAccessToken,
} from './remoteBackends/storage'

export const AUTH_TOKEN_HEADER = 'X-Borg-Authorization'
export const REMOTE_TARGET_AUTH_HEADER = 'X-Borg-Remote-Authorization'
export const REMOTE_TARGET_AUTH_QUERY_PARAM = 'target_token'
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

export const attachBackendTargetAccessHeaders = (
  config: InternalAxiosRequestConfig,
  targetId?: string
): InternalAxiosRequestConfig => {
  const headerValues = getBackendTargetAccessHeaderValues(targetId)
  if (!headerValues) {
    return config
  }

  const headers = AxiosHeaders.from(config.headers)
  for (const [key, value] of Object.entries(headerValues)) {
    headers.set(key, value)
  }
  config.headers = headers
  return config
}

export const getBackendTargetAccessHeaderValues = (
  targetId?: string
): Record<string, string> | undefined => {
  if (!targetId || targetId === LOCAL_BACKEND_ID) {
    return getAccessTokenHeader(targetId)
  }

  const headerValues: Record<string, string> = {}
  const localToken = getAccessToken(LOCAL_BACKEND_ID)
  if (localToken) {
    headerValues[AUTH_TOKEN_HEADER] = `Bearer ${localToken}`
  }

  const remoteToken = getAccessToken(targetId)
  if (remoteToken) {
    headerValues[REMOTE_TARGET_AUTH_HEADER] = `Bearer ${remoteToken}`
  }

  return Object.keys(headerValues).length > 0 ? headerValues : undefined
}

export const getBackendTargetTokenParams = (
  targetId?: string
): { token?: string; target_token?: string } => {
  if (!targetId || targetId === LOCAL_BACKEND_ID) {
    const token = getAccessToken(targetId)
    return token ? { token } : {}
  }

  const params: { token?: string; target_token?: string } = {}
  const localToken = getAccessToken(LOCAL_BACKEND_ID)
  const remoteToken = getAccessToken(targetId)
  if (localToken) params.token = localToken
  if (remoteToken) params.target_token = remoteToken
  return params
}
