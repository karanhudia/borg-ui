import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
} from '../../test/test-utils'
import { LOCAL_BACKEND_ID, resetRemoteBackendStateForTests, setBackendAccessToken } from './storage'
import { RemoteBackendProvider, useRemoteBackends } from './context'
import type { RemoteBackendCompatibility, RemoteBackendStatus } from './types'

interface DbClientHealthResponse {
  status: RemoteBackendStatus
  checked_at: string | null
  app_version: string | null
  borg_version: string | null
  borg2_version: string | null
  error: string | null
  compatibility: RemoteBackendCompatibility
  compatibility_message: string | null
}

interface DbClientResponse {
  id: string
  name: string
  api_base_url: string
  web_base_url: string
  created_at: string
  updated_at: string
  health: DbClientHealthResponse
}

const dbClientResponse: DbClientResponse = {
  id: 'db-client-1',
  name: 'Studio NAS',
  api_base_url: 'https://nas.example.com/api',
  web_base_url: 'https://nas.example.com',
  created_at: '2026-06-05T00:00:00+00:00',
  updated_at: '2026-06-05T00:00:00+00:00',
  health: {
    status: 'unknown',
    checked_at: null,
    app_version: null,
    borg_version: null,
    borg2_version: null,
    error: null,
    compatibility: 'unknown',
    compatibility_message: null,
  },
}

let nextDbClientId = 1

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deriveClientUrls(backendUrl: string): { apiBaseUrl: string; webBaseUrl: string } {
  const withProtocol = /^https?:\/\//i.test(backendUrl) ? backendUrl : `http://${backendUrl}`
  const trimmed = withProtocol.replace(/\/+$/, '')
  if (trimmed.endsWith('/api')) {
    return {
      apiBaseUrl: trimmed,
      webBaseUrl: trimmed.slice(0, -4),
    }
  }
  return {
    apiBaseUrl: `${trimmed}/api`,
    webBaseUrl: trimmed,
  }
}

function makeDbClient(
  overrides: {
    id?: string
    name?: string
    apiBaseUrl?: string
    webBaseUrl?: string
    health?: Partial<typeof dbClientResponse.health>
  } = {}
) {
  return {
    ...dbClientResponse,
    id: overrides.id ?? `db-client-${nextDbClientId++}`,
    name: overrides.name ?? dbClientResponse.name,
    api_base_url: overrides.apiBaseUrl ?? dbClientResponse.api_base_url,
    web_base_url: overrides.webBaseUrl ?? dbClientResponse.web_base_url,
    health: {
      ...dbClientResponse.health,
      ...overrides.health,
    },
  }
}

function createRemoteClientsApiFetch(
  options: {
    clients?: ReturnType<typeof makeDbClient>[]
    handleRemote?: (url: string, init?: RequestInit) => Promise<Response>
  } = {}
) {
  const clients = [...(options.clients ?? [])]
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'

    if (url.endsWith('/api/remote-clients') && method === 'GET') {
      return jsonResponse(clients)
    }

    if (url.endsWith('/api/remote-clients') && method === 'POST') {
      const body = JSON.parse(String(init?.body ?? '{}')) as {
        id?: string
        name?: string
        backend_url?: string
      }
      const urls = deriveClientUrls(body.backend_url ?? '')
      const client = makeDbClient({
        id: body.id,
        name: body.name ?? 'Studio NAS',
        apiBaseUrl: urls.apiBaseUrl,
        webBaseUrl: urls.webBaseUrl,
      })
      clients.push(client)
      return jsonResponse(client, 201)
    }

    if (url.includes('/api/remote-clients/') && method === 'PATCH') {
      const markerIndex = url.lastIndexOf('/api/remote-clients/')
      const id = decodeURIComponent(
        url.slice(markerIndex + '/api/remote-clients/'.length).replace(/\/health$/, '')
      )
      const index = clients.findIndex((client) => client.id === id)
      if (index === -1) return jsonResponse({ detail: 'Not found' }, 404)
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>
      clients[index] = {
        ...clients[index],
        health: {
          status: body.status as RemoteBackendStatus,
          checked_at: body.checked_at as string | null,
          app_version: body.app_version as string | null,
          borg_version: body.borg_version as string | null,
          borg2_version: body.borg2_version as string | null,
          error: body.error as string | null,
          compatibility: body.compatibility as RemoteBackendCompatibility,
          compatibility_message: body.compatibility_message as string | null,
        },
      }
      return jsonResponse(clients[index])
    }

    if (url.includes('/api/remote-clients/') && method === 'DELETE') {
      const markerIndex = url.lastIndexOf('/api/remote-clients/')
      const id = decodeURIComponent(url.slice(markerIndex + '/api/remote-clients/'.length))
      const index = clients.findIndex((client) => client.id === id)
      if (index !== -1) clients.splice(index, 1)
      return new Response(null, { status: 204 })
    }

    if (options.handleRemote) {
      return options.handleRemote(url, init)
    }

    throw new Error(`Unexpected fetch: ${method} ${url}`)
  })
}

function RemoteBackendProbe() {
  const { activeTarget, clients, createClient, switchTarget, checkClient, deleteClient } =
    useRemoteBackends()
  const firstClient = clients[0]

  return (
    <div>
      <div>active:{activeTarget.name}</div>
      <div>active-id:{activeTarget.id}</div>
      <div>clients:{clients.length}</div>
      <div>first:{firstClient?.name ?? 'none'}</div>
      <div>status:{firstClient?.health.status ?? 'none'}</div>
      <div>version:{firstClient?.health.appVersion ?? 'none'}</div>
      <div>compatibility:{firstClient?.health.compatibility ?? 'none'}</div>
      <button
        onClick={() => {
          void createClient({
            name: 'Studio NAS',
            backendUrl: 'nas.local:9000',
          })
        }}
      >
        Add
      </button>
      <button onClick={() => firstClient && switchTarget(firstClient.id)}>SwitchRemote</button>
      <button onClick={() => switchTarget(LOCAL_BACKEND_ID)}>SwitchLocal</button>
      <button onClick={() => firstClient && void checkClient(firstClient.id)}>Check</button>
      <button onClick={() => firstClient && void deleteClient(firstClient.id)}>Delete</button>
    </div>
  )
}

describe('RemoteBackendProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
    nextDbClientId = 1
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('creates clients and switches between local and remote targets', async () => {
    const fetchMock = createRemoteClientsApiFetch()
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    expect(screen.getByText('active:This server')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('clients:1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'SwitchRemote' }))
    expect(screen.getByText('active:Studio NAS')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'SwitchLocal' }))
    expect(screen.getByText('active:This server')).toBeInTheDocument()
  })

  it('hydrates saved remote clients from the active backend API', async () => {
    setBackendAccessToken('admin-token')
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/remote-clients') {
        expect(new Headers(init?.headers).get('X-Borg-Authorization')).toBe('Bearer admin-token')
        return Promise.resolve(
          new Response(JSON.stringify([dbClientResponse]), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      }
      return Promise.reject(new Error(`Unexpected fetch: ${String(input)}`))
    })

    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    expect(await screen.findByText('clients:1')).toBeInTheDocument()
    expect(screen.getByText('active:This server')).toBeInTheDocument()
  })

  it('imports legacy localStorage clients into the active backend API once', async () => {
    setBackendAccessToken('admin-token')
    localStorage.setItem(
      'borg_ui_remote_backends',
      JSON.stringify([
        {
          id: 'legacy-client-1',
          kind: 'remote',
          name: 'Legacy NAS',
          apiBaseUrl: 'https://legacy.example.com/api',
          webBaseUrl: 'https://legacy.example.com',
          createdAt: '2026-06-05T00:00:00.000Z',
          updatedAt: '2026-06-05T00:00:00.000Z',
          health: {
            status: 'unknown',
            compatibility: 'unknown',
          },
        },
      ])
    )
    let getCount = 0
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url === '/api/remote-clients' && method === 'GET') {
        getCount += 1
        return Promise.resolve(
          new Response(JSON.stringify(getCount === 1 ? [] : [dbClientResponse]), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      }
      if (url === '/api/remote-clients' && method === 'POST') {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          id: 'legacy-client-1',
          name: 'Legacy NAS',
          backend_url: 'https://legacy.example.com/api',
        })
        return Promise.resolve(
          new Response(JSON.stringify(dbClientResponse), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      }
      return Promise.reject(new Error(`Unexpected fetch: ${method} ${url}`))
    })

    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/remote-clients',
        expect.objectContaining({ method: 'POST' })
      )
      const importCalls = fetchMock.mock.calls.filter(([input, init]) => {
        return String(input) === '/api/remote-clients' && (init?.method ?? 'GET') === 'POST'
      })
      expect(importCalls).toHaveLength(1)
      expect(localStorage.getItem('borg_ui_remote_backends')).toBeNull()
    })
  })

  it('keeps the newest refresh when an older client load resolves late', async () => {
    const staleClient = makeDbClient({ id: 'stale-client', name: 'Stale NAS' })
    const freshClient = makeDbClient({ id: 'fresh-client', name: 'Fresh NAS' })
    let getCount = 0
    let resolveFirstLoad: (response: Response) => void = () => {}
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url === '/api/remote-clients' && method === 'GET') {
        getCount += 1
        if (getCount === 1) {
          return new Promise<Response>((resolve) => {
            resolveFirstLoad = resolve
          })
        }
        return Promise.resolve(jsonResponse([freshClient]))
      }
      return Promise.reject(new Error(`Unexpected fetch: ${method} ${url}`))
    })

    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await waitFor(() => {
      expect(getCount).toBe(1)
    })

    window.dispatchEvent(new StorageEvent('storage'))

    expect(await screen.findByText('first:Fresh NAS')).toBeInTheDocument()

    await act(async () => {
      resolveFirstLoad(jsonResponse([staleClient]))
    })

    await waitFor(() => {
      expect(screen.getByText('first:Fresh NAS')).toBeInTheDocument()
    })
    expect(screen.queryByText('first:Stale NAS')).not.toBeInTheDocument()
  })

  it('checks reachability and version compatibility for a remote client', async () => {
    const fetchMock = createRemoteClientsApiFetch({
      handleRemote: async (url) => {
        if (url === 'http://nas.local:9000/health') {
          return jsonResponse({ status: 'healthy' })
        }
        if (url === 'http://nas.local:9000/api/system/info') {
          return jsonResponse({
            app_version: '2.1.0',
            borg_version: 'borg 1.4.0',
            borg2_version: 'borg2 2.0.0',
          })
        }
        throw new Error(`Unexpected fetch: ${url}`)
      },
    })
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider frontendVersion="2.2.2" fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(await screen.findByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:online')).toBeInTheDocument()
      expect(screen.getByText('version:2.1.0')).toBeInTheDocument()
      expect(screen.getByText('compatibility:compatible')).toBeInTheDocument()
    })
  })

  it('keeps reachable health state when persisting health fails', async () => {
    const client = makeDbClient({
      id: 'db-client-1',
      apiBaseUrl: 'http://nas.local:9000/api',
      webBaseUrl: 'http://nas.local:9000',
    })
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url === '/api/remote-clients' && method === 'GET') {
        return Promise.resolve(jsonResponse([client]))
      }
      if (url === 'http://nas.local:9000/health') {
        return Promise.resolve(jsonResponse({ status: 'healthy' }))
      }
      if (url === 'http://nas.local:9000/api/system/info') {
        return Promise.resolve(
          jsonResponse({
            app_version: '2.1.0',
            borg_version: 'borg 1.4.0',
          })
        )
      }
      if (url.includes('/api/remote-clients/') && method === 'PATCH') {
        return Promise.reject(new Error('database unavailable'))
      }
      return Promise.reject(new Error(`Unexpected fetch: ${method} ${url}`))
    })
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider frontendVersion="2.2.2" fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await screen.findByText('clients:1')
    await user.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:online')).toBeInTheDocument()
      expect(screen.getByText('compatibility:compatible')).toBeInTheDocument()
    })
    expect(screen.queryByText('status:offline')).not.toBeInTheDocument()
  })

  it('keeps an unreachable remote client inactive and records the error', async () => {
    const fetchMock = createRemoteClientsApiFetch({
      handleRemote: async () => {
        throw new Error('network unavailable')
      },
    })
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(await screen.findByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:offline')).toBeInTheDocument()
      expect(screen.getByText('compatibility:unknown')).toBeInTheDocument()
      expect(screen.getByText('active:This server')).toBeInTheDocument()
    })
  })

  it('times out stalled health checks and records the abort error', async () => {
    const fetchMock = createRemoteClientsApiFetch({
      clients: [
        makeDbClient({
          apiBaseUrl: 'http://nas.local:9000/api',
          webBaseUrl: 'http://nas.local:9000',
        }),
      ],
      handleRemote: async (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const error = new Error('Aborted')
            error.name = 'AbortError'
            reject(error)
          })
        }),
    })
    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await screen.findByText('clients:1')
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Check' }))

    expect(fetchMock).toHaveBeenCalledWith(
      'http://nas.local:9000/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000)
    })

    expect(screen.getByText('status:offline')).toBeInTheDocument()
    expect(screen.getByText('compatibility:unknown')).toBeInTheDocument()
  })

  it('keeps the latest health check result when an older check resolves late', async () => {
    let firstSystemInfoResolve: (value: Record<string, unknown>) => void = () => {}
    let healthCallCount = 0
    const fetchMock = createRemoteClientsApiFetch({
      handleRemote: async (url) => {
        if (url === 'http://nas.local:9000/health') {
          healthCallCount += 1
          if (healthCallCount === 1) {
            return jsonResponse({ status: 'healthy' })
          }
          return jsonResponse({ status: 'down' }, 503)
        }
        if (url === 'http://nas.local:9000/api/system/info') {
          return {
            ok: true,
            status: 200,
            json: () =>
              new Promise<Record<string, unknown>>((resolve) => {
                firstSystemInfoResolve = resolve
              }),
          } as Response
        }
        throw new Error(`Unexpected fetch: ${url}`)
      },
    })
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider frontendVersion="2.2.2" fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(await screen.findByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://nas.local:9000/api/system/info',
        expect.anything()
      )
    })

    await user.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:offline')).toBeInTheDocument()
    })

    await act(async () => {
      firstSystemInfoResolve({
        app_version: '2.1.0',
        borg_version: 'borg 1.4.0',
      })
    })

    expect(screen.getByText('status:offline')).toBeInTheDocument()
    expect(screen.getByText('compatibility:unknown')).toBeInTheDocument()
  })
})
