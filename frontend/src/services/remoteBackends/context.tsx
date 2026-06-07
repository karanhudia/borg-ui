import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type {
  BackendTarget,
  RemoteBackendClient,
  RemoteBackendClientInput,
  RemoteBackendHealth,
  RemoteBackendStatus,
  RemoteBackendCompatibility,
  RemoteBackendState,
} from './types'
import {
  clearLegacyRemoteBackendClients,
  deleteRemoteBackendClient,
  getActiveBackendTarget,
  getBackendAccessToken,
  listRemoteBackendClients,
  readRemoteBackendState,
  readLegacyRemoteBackendClients,
  replaceRemoteBackendClients,
  setActiveBackendTarget,
  subscribeRemoteBackendStorage,
  updateRemoteBackendHealth,
} from './storage'
import { compareBackendVersions, normalizeRemoteBackendUrl } from './url'
import { AUTH_TOKEN_HEADER } from '../authHeaders'

const FRONTEND_APP_VERSION = __APP_VERSION__
const REMOTE_BACKEND_CHECK_TIMEOUT_MS = 10000

interface RemoteBackendContextValue {
  activeTarget: BackendTarget
  clients: RemoteBackendClient[]
  state: RemoteBackendState
  createClient: (input: RemoteBackendClientInput) => Promise<RemoteBackendClient>
  updateClient: (id: string, input: RemoteBackendClientInput) => Promise<RemoteBackendClient>
  deleteClient: (id: string) => Promise<void>
  switchTarget: (id: string) => void
  checkClient: (id: string) => Promise<RemoteBackendClient>
  refresh: () => void
}

const RemoteBackendContext = createContext<RemoteBackendContextValue | null>(null)

interface RemoteBackendProviderProps {
  children: ReactNode
  frontendVersion?: string
  fetchImpl?: typeof fetch
}

function readSnapshot(): {
  state: RemoteBackendState
  clients: RemoteBackendClient[]
  activeTarget: BackendTarget
} {
  return {
    state: readRemoteBackendState(),
    clients: listRemoteBackendClients(),
    activeTarget: getActiveBackendTarget(),
  }
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.name === 'AbortError') {
    return 'Remote client health check timed out.'
  }
  return error instanceof Error ? error.message : 'Remote client server could not be reached.'
}

async function readJsonResponse(response: Response): Promise<Record<string, unknown>> {
  return (await response.json().catch(() => ({}))) as Record<string, unknown>
}

interface RemoteClientApiHealth {
  status: RemoteBackendStatus
  checked_at?: string | null
  app_version?: string | null
  borg_version?: string | null
  borg2_version?: string | null
  error?: string | null
  compatibility: RemoteBackendCompatibility
  compatibility_message?: string | null
}

interface RemoteClientApiResponse {
  id: string
  name: string
  api_base_url: string
  web_base_url: string
  created_at: string
  updated_at: string
  health: RemoteClientApiHealth
}

type PersistableRemoteBackendHealth = Partial<RemoteBackendHealth> & {
  status: RemoteBackendStatus
  compatibility: RemoteBackendCompatibility
}

function mapApiClient(client: RemoteClientApiResponse): RemoteBackendClient {
  return {
    id: client.id,
    kind: 'remote',
    name: client.name,
    apiBaseUrl: client.api_base_url,
    webBaseUrl: client.web_base_url,
    createdAt: client.created_at,
    updatedAt: client.updated_at,
    health: {
      status: client.health.status,
      checkedAt: client.health.checked_at ?? null,
      appVersion: client.health.app_version ?? null,
      borgVersion: client.health.borg_version ?? null,
      borg2Version: client.health.borg2_version ?? null,
      error: client.health.error ?? null,
      compatibility: client.health.compatibility,
      compatibilityMessage: client.health.compatibility_message ?? null,
    },
  }
}

function buildRemoteClientsUrl(target: BackendTarget, path = ''): string {
  return `${target.apiBaseUrl}/remote-clients${path}`
}

function buildRemoteClientsHeaders(target: BackendTarget, includeJson = false): Headers {
  const headers = new Headers({ Accept: 'application/json' })
  if (includeJson) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getBackendAccessToken(target.id)
  if (token) {
    headers.set(AUTH_TOKEN_HEADER, `Bearer ${token}`)
  }
  return headers
}

async function fetchRemoteClientsFromApi(
  fetchImpl: typeof fetch
): Promise<{ clients: RemoteBackendClient[]; authorized: boolean }> {
  const target = getActiveBackendTarget()
  const response = await fetchImpl(buildRemoteClientsUrl(target), {
    headers: buildRemoteClientsHeaders(target),
  })

  if (response.status === 401 || response.status === 403) {
    return { clients: [], authorized: false }
  }
  if (!response.ok) {
    throw new Error(`Remote clients failed to load with HTTP ${response.status}.`)
  }

  const body = (await response.json().catch(() => [])) as RemoteClientApiResponse[]
  return {
    clients: Array.isArray(body) ? body.map(mapApiClient) : [],
    authorized: true,
  }
}

async function sendRemoteClientApiRequest(
  fetchImpl: typeof fetch,
  path: string,
  init: RequestInit
): Promise<Response> {
  const target = getActiveBackendTarget()
  return fetchImpl(buildRemoteClientsUrl(target, path), {
    ...init,
    headers: buildRemoteClientsHeaders(target, Boolean(init.body)),
  })
}

async function readRemoteClientApiResponse(response: Response): Promise<RemoteBackendClient> {
  if (!response.ok) {
    throw new Error(`Remote client request failed with HTTP ${response.status}.`)
  }
  return mapApiClient((await response.json()) as RemoteClientApiResponse)
}

async function persistRemoteBackendHealth(
  fetchImpl: typeof fetch,
  id: string,
  health: PersistableRemoteBackendHealth
): Promise<RemoteBackendClient | null> {
  try {
    const response = await sendRemoteClientApiRequest(fetchImpl, `/${id}/health`, {
      method: 'PATCH',
      body: JSON.stringify({
        status: health.status,
        checked_at: health.checkedAt ?? null,
        app_version: health.appVersion ?? null,
        borg_version: health.borgVersion ?? null,
        borg2_version: health.borg2Version ?? null,
        error: health.error ?? null,
        compatibility: health.compatibility,
        compatibility_message: health.compatibilityMessage ?? null,
      }),
    })
    if (!response.ok) {
      return null
    }
    return readRemoteClientApiResponse(response)
  } catch {
    return null
  }
}

function upsertRemoteBackendClient(client: RemoteBackendClient): void {
  replaceRemoteBackendClients([
    ...listRemoteBackendClients().filter((item) => item.id !== client.id),
    client,
  ])
}

export function RemoteBackendProvider({
  children,
  frontendVersion = FRONTEND_APP_VERSION,
  fetchImpl = fetch,
}: RemoteBackendProviderProps) {
  const [snapshot, setSnapshot] = useState(readSnapshot)
  const pendingChecksRef = useRef(new Map<string, AbortController>())
  const refreshSeqRef = useRef(0)

  const refresh = useCallback(() => {
    setSnapshot(readSnapshot())
  }, [])

  const refreshRemoteClients = useCallback(
    async (options: { importLegacy?: boolean; isCurrent?: () => boolean } = {}) => {
      const isCurrent = options.isCurrent ?? (() => true)
      const refreshSeq = ++refreshSeqRef.current
      const isLatestRefresh = () => isCurrent() && refreshSeq === refreshSeqRef.current
      try {
        const result = await fetchRemoteClientsFromApi(fetchImpl)
        if (!isLatestRefresh()) {
          return
        }
        replaceRemoteBackendClients(result.clients)
        setSnapshot(readSnapshot())

        const legacyClients = options.importLegacy ? readLegacyRemoteBackendClients() : []
        if (!result.authorized || legacyClients.length === 0) {
          return
        }

        const existingIds = new Set(result.clients.map((client) => client.id))
        let importSucceeded = true
        for (const legacyClient of legacyClients) {
          if (!isLatestRefresh()) {
            return
          }
          if (existingIds.has(legacyClient.id)) {
            continue
          }
          const response = await sendRemoteClientApiRequest(fetchImpl, '', {
            method: 'POST',
            body: JSON.stringify({
              id: legacyClient.id,
              name: legacyClient.name,
              backend_url: legacyClient.apiBaseUrl,
            }),
          })
          if (!isLatestRefresh()) {
            return
          }
          if (response.status === 409) {
            continue
          }
          if (!response.ok) {
            importSucceeded = false
            break
          }
        }

        if (importSucceeded) {
          if (!isLatestRefresh()) {
            return
          }
          clearLegacyRemoteBackendClients()
          const refreshed = await fetchRemoteClientsFromApi(fetchImpl)
          if (!isLatestRefresh()) {
            return
          }
          replaceRemoteBackendClients(refreshed.clients)
          setSnapshot(readSnapshot())
        }
      } catch (error) {
        console.error('Failed to refresh remote clients:', error)
      }
    },
    [fetchImpl]
  )

  useEffect(() => {
    let current = true
    const isCurrent = () => current
    const refreshFromApi = () => {
      if (!current) {
        return
      }
      refresh()
      void refreshRemoteClients({ importLegacy: true, isCurrent })
    }
    const unsubscribe = subscribeRemoteBackendStorage((reason) => {
      if (!current) {
        return
      }
      refresh()
      if (reason !== 'clients') {
        void refreshRemoteClients({ importLegacy: true, isCurrent })
      }
    })
    const handleStorage = () => refreshFromApi()
    window.addEventListener('storage', handleStorage)
    void refreshRemoteClients({ importLegacy: true, isCurrent })
    return () => {
      current = false
      unsubscribe()
      window.removeEventListener('storage', handleStorage)
    }
  }, [refresh, refreshRemoteClients])

  useEffect(() => {
    const pendingChecks = pendingChecksRef.current
    return () => {
      pendingChecks.forEach((controller) => controller.abort())
      pendingChecks.clear()
    }
  }, [])

  const createClient = useCallback(
    async (input: RemoteBackendClientInput): Promise<RemoteBackendClient> => {
      const normalized = normalizeRemoteBackendUrl(input.backendUrl)
      const name = input.name.trim()
      if (!name) {
        throw new Error('Enter a client name.')
      }

      const response = await sendRemoteClientApiRequest(fetchImpl, '', {
        method: 'POST',
        body: JSON.stringify({ name, backend_url: normalized.apiBaseUrl }),
      })
      const created = await readRemoteClientApiResponse(response)
      upsertRemoteBackendClient(created)
      refresh()
      return created
    },
    [fetchImpl, refresh]
  )

  const updateClient = useCallback(
    async (id: string, input: RemoteBackendClientInput): Promise<RemoteBackendClient> => {
      const normalized = normalizeRemoteBackendUrl(input.backendUrl)
      const name = input.name.trim()
      if (!name) {
        throw new Error('Enter a client name.')
      }

      const response = await sendRemoteClientApiRequest(fetchImpl, `/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ name, backend_url: normalized.apiBaseUrl }),
      })
      const updated = await readRemoteClientApiResponse(response)
      upsertRemoteBackendClient(updated)
      refresh()
      return updated
    },
    [fetchImpl, refresh]
  )

  const deleteClient = useCallback(
    async (id: string): Promise<void> => {
      const response = await sendRemoteClientApiRequest(fetchImpl, `/${id}`, { method: 'DELETE' })
      if (!response.ok) {
        throw new Error(`Remote client delete failed with HTTP ${response.status}.`)
      }
      deleteRemoteBackendClient(id)
      refresh()
    },
    [fetchImpl, refresh]
  )

  const switchTarget = useCallback((id: string) => setActiveBackendTarget(id), [])

  const checkClient = useCallback(
    async (id: string): Promise<RemoteBackendClient> => {
      const client = listRemoteBackendClients().find((item) => item.id === id)
      if (!client) {
        throw new Error('Remote client was not found.')
      }

      updateRemoteBackendHealth(id, {
        status: 'checking',
        checkedAt: new Date().toISOString(),
        error: null,
      })

      pendingChecksRef.current.get(id)?.abort()
      const controller = new AbortController()
      pendingChecksRef.current.set(id, controller)
      const timeoutId = window.setTimeout(() => controller.abort(), REMOTE_BACKEND_CHECK_TIMEOUT_MS)
      const isLatestCheck = () => pendingChecksRef.current.get(id) === controller
      const readCurrentClient = () => listRemoteBackendClients().find((item) => item.id === id)

      try {
        const healthResponse = await fetchImpl(`${client.webBaseUrl}/health`, {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        })
        if (!isLatestCheck()) return readCurrentClient() ?? client
        if (!healthResponse.ok) {
          throw new Error(`Health check failed with HTTP ${healthResponse.status}.`)
        }

        const headers = new Headers({ Accept: 'application/json' })
        const token = getBackendAccessToken(client.id)
        if (token) {
          headers.set(AUTH_TOKEN_HEADER, `Bearer ${token}`)
        }

        const systemInfoResponse = await fetchImpl(`${client.apiBaseUrl}/system/info`, {
          headers,
          signal: controller.signal,
        })
        if (!isLatestCheck()) return readCurrentClient() ?? client
        if (!systemInfoResponse.ok) {
          throw new Error(`Version check failed with HTTP ${systemInfoResponse.status}.`)
        }

        const systemInfo = await readJsonResponse(systemInfoResponse)
        const appVersion =
          typeof systemInfo.app_version === 'string' ? systemInfo.app_version : null
        const compatibility = compareBackendVersions(frontendVersion, appVersion)
        const health: RemoteBackendHealth = {
          status: 'online',
          checkedAt: new Date().toISOString(),
          appVersion,
          borgVersion: typeof systemInfo.borg_version === 'string' ? systemInfo.borg_version : null,
          borg2Version:
            typeof systemInfo.borg2_version === 'string' ? systemInfo.borg2_version : null,
          error: null,
          compatibility: compatibility.status,
          compatibilityMessage: compatibility.message,
        }

        if (!isLatestCheck()) return readCurrentClient() ?? client
        updateRemoteBackendHealth(id, health)
        refresh()
        const persisted = await persistRemoteBackendHealth(fetchImpl, id, health)
        if (persisted) {
          upsertRemoteBackendClient(persisted)
          refresh()
          return persisted
        }
        return readCurrentClient() ?? client
      } catch (error) {
        if (!isLatestCheck()) return readCurrentClient() ?? client
        const offlineHealth: PersistableRemoteBackendHealth = {
          status: 'offline',
          checkedAt: new Date().toISOString(),
          error: extractErrorMessage(error),
          compatibility: 'unknown',
          compatibilityMessage: 'Remote client server compatibility could not be checked.',
        }
        updateRemoteBackendHealth(id, offlineHealth)
        refresh()
        const persisted = await persistRemoteBackendHealth(fetchImpl, id, offlineHealth)
        if (persisted) {
          upsertRemoteBackendClient(persisted)
          refresh()
          return persisted
        }
        return readCurrentClient() ?? client
      } finally {
        window.clearTimeout(timeoutId)
        if (isLatestCheck()) {
          pendingChecksRef.current.delete(id)
        }
      }
    },
    [fetchImpl, frontendVersion, refresh]
  )

  const value = useMemo<RemoteBackendContextValue>(
    () => ({
      ...snapshot,
      createClient,
      updateClient,
      deleteClient,
      switchTarget,
      checkClient,
      refresh,
    }),
    [checkClient, createClient, deleteClient, refresh, snapshot, switchTarget, updateClient]
  )

  return <RemoteBackendContext.Provider value={value}>{children}</RemoteBackendContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRemoteBackends(): RemoteBackendContextValue {
  const context = useContext(RemoteBackendContext)
  if (!context) {
    throw new Error('useRemoteBackends must be used inside RemoteBackendProvider.')
  }
  return context
}

// eslint-disable-next-line react-refresh/only-export-components
export function useActiveBackendTarget(): BackendTarget {
  return useContext(RemoteBackendContext)?.activeTarget ?? getActiveBackendTarget()
}
