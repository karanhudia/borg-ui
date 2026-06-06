export const LOCAL_BACKEND_ID = 'local'

export type BackendTargetKind = 'local' | 'remote'
export type RemoteBackendStatus = 'unknown' | 'checking' | 'online' | 'offline'
export type RemoteBackendCompatibility = 'compatible' | 'incompatible' | 'unknown'

export interface RemoteBackendHealth {
  status: RemoteBackendStatus
  checkedAt?: string | null
  appVersion?: string | null
  borgVersion?: string | null
  borg2Version?: string | null
  error?: string | null
  compatibility: RemoteBackendCompatibility
  compatibilityMessage?: string | null
}

export interface RemoteBackendClient {
  id: string
  kind: 'remote'
  name: string
  apiBaseUrl: string
  webBaseUrl: string
  createdAt: string
  updatedAt: string
  health: RemoteBackendHealth
}

export interface LocalBackendTarget {
  id: typeof LOCAL_BACKEND_ID
  kind: 'local'
  name: string
  apiBaseUrl: string
  webBaseUrl: string
  health: RemoteBackendHealth
}

export type BackendTarget = LocalBackendTarget | RemoteBackendClient

export interface RemoteBackendState {
  activeTargetId: string
  clients: RemoteBackendClient[]
}

export interface RemoteBackendClientInput {
  name: string
  backendUrl: string
}

export interface NormalizedRemoteBackendUrl {
  apiBaseUrl: string
  webBaseUrl: string
}
