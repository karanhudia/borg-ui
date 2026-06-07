import {
  LOCAL_BACKEND_ID,
  type BackendTarget,
  type RemoteBackendClient,
  type RemoteBackendClientInput,
  type RemoteBackendHealth,
  type RemoteBackendState,
} from './types'
import { getLocalApiBaseUrl, getLocalWebBaseUrl, normalizeRemoteBackendUrl } from './url'

export { LOCAL_BACKEND_ID } from './types'

const REMOTE_BACKENDS_STORAGE_KEY = 'borg_ui_remote_backends'
const REMOTE_BACKEND_ACTIVE_KEY = 'borg_ui_active_backend_target'
const REMOTE_BACKEND_ACTIVE_SNAPSHOT_KEY = 'borg_ui_active_backend_snapshot'
const REMOTE_TOKEN_PREFIX = 'borg_ui_access_token'
const LEGACY_LOCAL_TOKEN_KEY = 'access_token'
const remoteBackendClientsByStorage = new WeakMap<Storage, RemoteBackendClient[]>()
let fallbackRemoteBackendClients: RemoteBackendClient[] = []
export type RemoteBackendStorageChangeReason = 'clients' | 'target' | 'token'

const defaultHealth = (): RemoteBackendHealth => ({
  status: 'unknown',
  checkedAt: null,
  appVersion: null,
  borgVersion: null,
  borg2Version: null,
  error: null,
  compatibility: 'unknown',
  compatibilityMessage: null,
})

const listeners = new Set<(reason: RemoteBackendStorageChangeReason) => void>()

function nowIso(): string {
  return new Date().toISOString()
}

function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `remote-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function emitChange(reason: RemoteBackendStorageChangeReason = 'clients'): void {
  for (const listener of listeners) {
    listener(reason)
  }
}

function getClientStorage(): Storage | null {
  return typeof localStorage === 'undefined' ? null : localStorage
}

function cloneRemoteBackendClient(client: RemoteBackendClient): RemoteBackendClient {
  return {
    ...client,
    health: {
      ...client.health,
    },
  }
}

function isRemoteBackendClient(value: unknown): value is RemoteBackendClient {
  return (
    value !== null &&
    typeof value === 'object' &&
    'id' in value &&
    'name' in value &&
    'apiBaseUrl' in value &&
    'webBaseUrl' in value &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.apiBaseUrl === 'string' &&
    typeof value.webBaseUrl === 'string'
  )
}

function readClients(): RemoteBackendClient[] {
  const storage = getClientStorage()
  const clients = storage
    ? (remoteBackendClientsByStorage.get(storage) ?? [])
    : fallbackRemoteBackendClients
  return clients.map(cloneRemoteBackendClient)
}

function writeClients(clients: RemoteBackendClient[]): void {
  const nextClients = clients.map(cloneRemoteBackendClient)
  const storage = getClientStorage()
  if (storage) {
    remoteBackendClientsByStorage.set(storage, nextClients)
    return
  }
  fallbackRemoteBackendClients = nextClients
}

export function replaceRemoteBackendClients(clients: RemoteBackendClient[]): void {
  writeClients(clients)
  const activeTargetId = getStoredActiveTargetId()
  const activeClient = clients.find((client) => client.id === activeTargetId)
  if (activeClient) {
    writeActiveTargetSnapshot(activeClient)
  }
  emitChange('clients')
}

export function readLegacyRemoteBackendClients(): RemoteBackendClient[] {
  const storage = getClientStorage()
  if (!storage) return []

  const raw = storage.getItem(REMOTE_BACKENDS_STORAGE_KEY)
  if (!raw) return []

  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isRemoteBackendClient)
  } catch {
    return []
  }
}

export function clearLegacyRemoteBackendClients(): void {
  getClientStorage()?.removeItem(REMOTE_BACKENDS_STORAGE_KEY)
}

function getStoredActiveTargetId(): string {
  return localStorage.getItem(REMOTE_BACKEND_ACTIVE_KEY) || LOCAL_BACKEND_ID
}

function writeActiveTargetId(targetId: string): void {
  if (targetId === LOCAL_BACKEND_ID) {
    localStorage.removeItem(REMOTE_BACKEND_ACTIVE_KEY)
  } else {
    localStorage.setItem(REMOTE_BACKEND_ACTIVE_KEY, targetId)
  }
}

function readActiveTargetSnapshot(): RemoteBackendClient | null {
  const storage = getClientStorage()
  if (!storage) return null

  const raw = storage.getItem(REMOTE_BACKEND_ACTIVE_SNAPSHOT_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw)
    if (!isRemoteBackendClient(parsed)) return null
    return cloneRemoteBackendClient(parsed)
  } catch {
    return null
  }
}

function writeActiveTargetSnapshot(client: RemoteBackendClient | null): void {
  const storage = getClientStorage()
  if (!storage) return

  if (!client) {
    storage.removeItem(REMOTE_BACKEND_ACTIVE_SNAPSHOT_KEY)
    return
  }

  storage.setItem(
    REMOTE_BACKEND_ACTIVE_SNAPSHOT_KEY,
    JSON.stringify(cloneRemoteBackendClient(client))
  )
}

export function readRemoteBackendState(): RemoteBackendState {
  const clients = readClients()
  const activeTargetId = getStoredActiveTargetId()
  const activeSnapshot = readActiveTargetSnapshot()
  const activeExists =
    activeTargetId === LOCAL_BACKEND_ID ||
    clients.some((client) => client.id === activeTargetId) ||
    activeSnapshot?.id === activeTargetId

  return {
    activeTargetId: activeExists ? activeTargetId : LOCAL_BACKEND_ID,
    clients,
  }
}

export function getLocalBackendTarget(): BackendTarget {
  return {
    id: LOCAL_BACKEND_ID,
    kind: 'local',
    name: 'This server',
    apiBaseUrl: getLocalApiBaseUrl(),
    webBaseUrl: getLocalWebBaseUrl(),
    health: {
      ...defaultHealth(),
      status: 'online',
      compatibility: 'compatible',
      compatibilityMessage: 'This browser is connected to this Borg UI server.',
    },
  }
}

export function listRemoteBackendClients(): RemoteBackendClient[] {
  return readClients()
}

export function getActiveBackendTarget(): BackendTarget {
  const state = readRemoteBackendState()
  if (state.activeTargetId === LOCAL_BACKEND_ID) {
    return getLocalBackendTarget()
  }

  const activeClient = state.clients.find((client) => client.id === state.activeTargetId)
  const activeSnapshot = readActiveTargetSnapshot()
  return (
    activeClient ??
    (activeSnapshot?.id === state.activeTargetId ? activeSnapshot : null) ??
    getLocalBackendTarget()
  )
}

export function createRemoteBackendClient(input: RemoteBackendClientInput): RemoteBackendClient {
  const normalized = normalizeRemoteBackendUrl(input.backendUrl)
  const name = input.name.trim()
  if (!name) {
    throw new Error('Enter a client name.')
  }

  const timestamp = nowIso()
  const client: RemoteBackendClient = {
    id: createId(),
    kind: 'remote',
    name,
    apiBaseUrl: normalized.apiBaseUrl,
    webBaseUrl: normalized.webBaseUrl,
    createdAt: timestamp,
    updatedAt: timestamp,
    health: defaultHealth(),
  }

  writeClients([...readClients(), client])
  emitChange('clients')
  return client
}

export function updateRemoteBackendClient(
  id: string,
  input: RemoteBackendClientInput
): RemoteBackendClient {
  const normalized = normalizeRemoteBackendUrl(input.backendUrl)
  const name = input.name.trim()
  if (!name) {
    throw new Error('Enter a client name.')
  }

  const clients = readClients()
  const index = clients.findIndex((client) => client.id === id)
  if (index === -1) {
    throw new Error('Remote client was not found.')
  }

  const updated: RemoteBackendClient = {
    ...clients[index],
    name,
    apiBaseUrl: normalized.apiBaseUrl,
    webBaseUrl: normalized.webBaseUrl,
    updatedAt: nowIso(),
  }
  const nextClients = [...clients]
  nextClients[index] = updated
  writeClients(nextClients)
  if (getStoredActiveTargetId() === id) {
    writeActiveTargetSnapshot(updated)
  }
  emitChange('clients')
  return updated
}

export function updateRemoteBackendHealth(
  id: string,
  health: Partial<RemoteBackendHealth>
): RemoteBackendClient {
  const clients = readClients()
  const index = clients.findIndex((client) => client.id === id)
  if (index === -1) {
    throw new Error('Remote client was not found.')
  }

  const updated: RemoteBackendClient = {
    ...clients[index],
    health: {
      ...clients[index].health,
      ...health,
    },
    updatedAt: nowIso(),
  }
  const nextClients = [...clients]
  nextClients[index] = updated
  writeClients(nextClients)
  if (getStoredActiveTargetId() === id) {
    writeActiveTargetSnapshot(updated)
  }
  emitChange('clients')
  return updated
}

export function deleteRemoteBackendClient(id: string): void {
  const clients = readClients().filter((client) => client.id !== id)
  writeClients(clients)
  if (getStoredActiveTargetId() === id) {
    writeActiveTargetId(LOCAL_BACKEND_ID)
    writeActiveTargetSnapshot(null)
  }
  localStorage.removeItem(getAccessTokenKey(id))
  emitChange('clients')
}

export function setActiveBackendTarget(targetId: string): void {
  if (targetId === LOCAL_BACKEND_ID) {
    writeActiveTargetId(LOCAL_BACKEND_ID)
    writeActiveTargetSnapshot(null)
    emitChange('target')
    return
  }

  const activeSnapshot = readActiveTargetSnapshot()
  const client =
    readClients().find((item) => item.id === targetId) ??
    (activeSnapshot?.id === targetId ? activeSnapshot : null)
  if (!client) {
    throw new Error('Remote client was not found.')
  }

  if (client.health.compatibility === 'incompatible') {
    throw new Error(client.health.compatibilityMessage || 'Remote client server is incompatible.')
  }

  writeActiveTargetId(targetId)
  writeActiveTargetSnapshot(client)
  emitChange('target')
}

export function getAccessTokenKey(targetId = getActiveBackendTarget().id): string {
  return targetId === LOCAL_BACKEND_ID
    ? LEGACY_LOCAL_TOKEN_KEY
    : `${REMOTE_TOKEN_PREFIX}:${targetId}`
}

export function getBackendAccessToken(targetId?: string): string | null {
  return localStorage.getItem(getAccessTokenKey(targetId))
}

export function setBackendAccessToken(token: string, targetId?: string): void {
  localStorage.setItem(getAccessTokenKey(targetId), token)
  emitChange('token')
}

export function clearBackendAccessToken(targetId?: string): void {
  localStorage.removeItem(getAccessTokenKey(targetId))
  emitChange('token')
}

export function subscribeRemoteBackendStorage(
  listener: (reason: RemoteBackendStorageChangeReason) => void
): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function resetRemoteBackendStateForTests(): void {
  writeClients([])
  localStorage.removeItem(REMOTE_BACKENDS_STORAGE_KEY)
  localStorage.removeItem(REMOTE_BACKEND_ACTIVE_KEY)
  localStorage.removeItem(REMOTE_BACKEND_ACTIVE_SNAPSHOT_KEY)
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith(`${REMOTE_TOKEN_PREFIX}:`)) {
      localStorage.removeItem(key)
    }
  }
  listeners.clear()
}
