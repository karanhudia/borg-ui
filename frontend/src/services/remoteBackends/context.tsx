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
  RemoteBackendState,
} from './types'
import {
  createRemoteBackendClient,
  deleteRemoteBackendClient,
  getActiveBackendTarget,
  getBackendAccessToken,
  listRemoteBackendClients,
  readRemoteBackendState,
  setActiveBackendTarget,
  subscribeRemoteBackendStorage,
  updateRemoteBackendClient,
  updateRemoteBackendHealth,
} from './storage'
import { compareBackendVersions } from './url'
import { AUTH_TOKEN_HEADER } from '../authHeaders'

const FRONTEND_APP_VERSION = __APP_VERSION__
const REMOTE_BACKEND_CHECK_TIMEOUT_MS = 10000

interface RemoteBackendContextValue {
  activeTarget: BackendTarget
  clients: RemoteBackendClient[]
  state: RemoteBackendState
  createClient: (input: RemoteBackendClientInput) => RemoteBackendClient
  updateClient: (id: string, input: RemoteBackendClientInput) => RemoteBackendClient
  deleteClient: (id: string) => void
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

export function RemoteBackendProvider({
  children,
  frontendVersion = FRONTEND_APP_VERSION,
  fetchImpl = fetch,
}: RemoteBackendProviderProps) {
  const [snapshot, setSnapshot] = useState(readSnapshot)
  const pendingChecksRef = useRef(new Map<string, AbortController>())

  const refresh = useCallback(() => {
    setSnapshot(readSnapshot())
  }, [])

  useEffect(() => {
    const unsubscribe = subscribeRemoteBackendStorage(refresh)
    const handleStorage = () => refresh()
    window.addEventListener('storage', handleStorage)
    return () => {
      unsubscribe()
      window.removeEventListener('storage', handleStorage)
    }
  }, [refresh])

  useEffect(() => {
    const pendingChecks = pendingChecksRef.current
    return () => {
      pendingChecks.forEach((controller) => controller.abort())
      pendingChecks.clear()
    }
  }, [])

  const createClient = useCallback(
    (input: RemoteBackendClientInput) => createRemoteBackendClient(input),
    []
  )

  const updateClient = useCallback(
    (id: string, input: RemoteBackendClientInput) => updateRemoteBackendClient(id, input),
    []
  )

  const deleteClient = useCallback((id: string) => deleteRemoteBackendClient(id), [])

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
        return updateRemoteBackendHealth(id, health)
      } catch (error) {
        if (!isLatestCheck()) return readCurrentClient() ?? client
        return updateRemoteBackendHealth(id, {
          status: 'offline',
          checkedAt: new Date().toISOString(),
          error: extractErrorMessage(error),
          compatibility: 'unknown',
          compatibilityMessage: 'Remote client server compatibility could not be checked.',
        })
      } finally {
        window.clearTimeout(timeoutId)
        if (isLatestCheck()) {
          pendingChecksRef.current.delete(id)
        }
      }
    },
    [fetchImpl, frontendVersion]
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
