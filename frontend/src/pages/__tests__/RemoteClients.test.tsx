import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import { toast } from 'react-hot-toast'
import RemoteClients from '../RemoteClients'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import { resetRemoteBackendStateForTests } from '../../services/remoteBackends/storage'
import type {
  RemoteBackendCompatibility,
  RemoteBackendStatus,
} from '../../services/remoteBackends/types'

const { mockHasGlobalPermission, mockPlanCan, mockTrackRemoteClient } = vi.hoisted(() => ({
  mockHasGlobalPermission: vi.fn(() => true),
  mockPlanCan: vi.fn((_feature: string) => true),
  mockTrackRemoteClient: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: mockHasGlobalPermission,
  }),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    features: {},
    entitlement: undefined,
    isLoading: false,
    can: mockPlanCan,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackRemoteClient: mockTrackRemoteClient,
    EventAction: {
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
      SWITCH: 'Switch',
      TEST: 'Test',
    },
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

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

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

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

function makeDbClient(
  overrides: {
    id?: string
    name?: string
    apiBaseUrl?: string
    webBaseUrl?: string
    health?: Partial<DbClientHealthResponse>
  } = {}
): DbClientResponse {
  return {
    id: overrides.id ?? `db-client-${nextDbClientId++}`,
    name: overrides.name ?? 'Studio NAS',
    api_base_url: overrides.apiBaseUrl ?? 'http://nas.local:9000/api',
    web_base_url: overrides.webBaseUrl ?? 'http://nas.local:9000',
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
      ...overrides.health,
    },
  }
}

function createRemoteClientsPageFetch(
  options: {
    clients?: ReturnType<typeof makeDbClient>[]
    deleteStatus?: number
    handleCheck?: (id: string, init?: RequestInit) => Promise<Response>
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
        name?: string
        backend_url?: string
      }
      const urls = deriveClientUrls(body.backend_url ?? '')
      const client = makeDbClient({
        name: body.name,
        apiBaseUrl: urls.apiBaseUrl,
        webBaseUrl: urls.webBaseUrl,
      })
      clients.push(client)
      return jsonResponse(client, 201)
    }

    if (url.includes('/api/remote-clients/') && method === 'PUT') {
      const markerIndex = url.lastIndexOf('/api/remote-clients/')
      const id = decodeURIComponent(url.slice(markerIndex + '/api/remote-clients/'.length))
      const index = clients.findIndex((client) => client.id === id)
      if (index === -1) return jsonResponse({ detail: 'Not found' }, 404)
      const body = JSON.parse(String(init?.body ?? '{}')) as {
        name?: string
        backend_url?: string
      }
      const urls = deriveClientUrls(body.backend_url ?? clients[index].api_base_url)
      clients[index] = {
        ...clients[index],
        name: body.name ?? clients[index].name,
        api_base_url: urls.apiBaseUrl,
        web_base_url: urls.webBaseUrl,
      }
      return jsonResponse(clients[index])
    }

    if (url.includes('/api/remote-clients/') && method === 'POST' && url.endsWith('/check')) {
      const markerIndex = url.lastIndexOf('/api/remote-clients/')
      const id = decodeURIComponent(
        url.slice(markerIndex + '/api/remote-clients/'.length).replace(/\/check$/, '')
      )
      if (options.handleCheck) {
        return options.handleCheck(id, init)
      }
      const index = clients.findIndex((client) => client.id === id)
      if (index === -1) return jsonResponse({ detail: 'Not found' }, 404)
      clients[index] = {
        ...clients[index],
        health: {
          ...clients[index].health,
          status: 'online',
          checked_at: '2026-06-05T12:00:00+00:00',
          app_version: '2.2.1',
          borg_version: 'borg 1.4.0',
          error: null,
          compatibility: 'compatible',
          compatibility_message: 'Borg UI 2.2.1 is compatible with this frontend.',
        },
      }
      return jsonResponse(clients[index])
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
          checked_at: stringOrNull(body.checked_at),
          app_version: stringOrNull(body.app_version),
          borg_version: stringOrNull(body.borg_version),
          borg2_version: stringOrNull(body.borg2_version),
          error: stringOrNull(body.error),
          compatibility: body.compatibility as RemoteBackendCompatibility,
          compatibility_message: stringOrNull(body.compatibility_message),
        },
      }
      return jsonResponse(clients[index])
    }

    if (url.includes('/api/remote-clients/') && method === 'DELETE') {
      const markerIndex = url.lastIndexOf('/api/remote-clients/')
      const id = decodeURIComponent(url.slice(markerIndex + '/api/remote-clients/'.length))
      const index = clients.findIndex((client) => client.id === id)
      if (options.deleteStatus && options.deleteStatus !== 204) {
        return jsonResponse({ detail: 'Delete failed' }, options.deleteStatus)
      }
      if (index !== -1) clients.splice(index, 1)
      return new Response(null, { status: 204 })
    }

    if (options.handleRemote) {
      return options.handleRemote(url, init)
    }

    throw new Error(`Unexpected fetch: ${method} ${url}`)
  })
}

function renderPage(fetchImpl: typeof fetch = createRemoteClientsPageFetch()) {
  return renderWithProviders(
    <RemoteBackendProvider frontendVersion="2.2.2" fetchImpl={fetchImpl}>
      <RemoteClients />
    </RemoteBackendProvider>,
    { initialRoute: '/remote-clients' }
  )
}

describe('RemoteClients', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
    nextDbClientId = 1
    vi.restoreAllMocks()
    vi.mocked(toast.success).mockClear()
    vi.mocked(toast.error).mockClear()
    mockHasGlobalPermission.mockReturnValue(true)
    mockPlanCan.mockReturnValue(true)
    mockTrackRemoteClient.mockClear()
  })

  it('redirects when the user lacks SSH management permission', async () => {
    mockHasGlobalPermission.mockReturnValue(false)

    renderPage()

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('You do not have permission to open this page', {
        duration: 4000,
      })
      expect(window.location.pathname).toBe('/dashboard')
    })
  })

  it('adds and lists a remote client with normalized URL details', async () => {
    renderPage()

    expect(screen.getByText('Remote Clients')).toBeInTheDocument()
    expect(screen.getByText('No remote clients yet')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Studio NAS' } })
    fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: 'nas.local:9000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))

    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()
    expect(screen.getByText('http://nas.local:9000/api')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Create',
      expect.objectContaining({ name: 'Studio NAS' }),
      { surface: 'remote_clients' }
    )
  })

  it('tracks successful remote client edits', async () => {
    const user = userEvent.setup()
    renderPage(
      createRemoteClientsPageFetch({
        clients: [makeDbClient({ id: 'db-client-1', name: 'Studio NAS' })],
      })
    )

    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /edit studio nas/i }))
    await user.clear(screen.getByLabelText('Client name'))
    await user.type(screen.getByLabelText('Client name'), 'Studio NAS 2')
    await user.click(screen.getByRole('button', { name: 'Save client' }))

    expect(await screen.findByText('Studio NAS 2')).toBeInTheDocument()
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Edit',
      expect.objectContaining({ name: 'Studio NAS 2' }),
      { surface: 'remote_clients' }
    )
  })

  it('prevents duplicate create requests while save is in flight', async () => {
    const fetchMock = createRemoteClientsPageFetch()
    renderPage(fetchMock)

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Studio NAS' } })
    fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: 'nas.local:9000' } })

    const saveButton = screen.getByRole('button', { name: 'Save client' })
    fireEvent.click(saveButton)
    fireEvent.click(saveButton)

    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()

    const createCalls = fetchMock.mock.calls.filter(([input, init]) => {
      return String(input).endsWith('/api/remote-clients') && (init?.method ?? 'GET') === 'POST'
    })
    expect(createCalls).toHaveLength(1)
  })

  it('shows the plan gate over a read-only page preview when remote clients are unavailable', async () => {
    mockPlanCan.mockImplementation((feature) => feature !== 'remote_clients')

    renderPage(
      createRemoteClientsPageFetch({
        clients: [makeDbClient({ id: 'db-client-1', name: 'Studio NAS' })],
      })
    )

    expect(
      await screen.findByText(/remote client switching is available on pro and enterprise plans/i)
    ).toBeInTheDocument()
    expect(screen.getByText('Remote Clients')).toBeInTheDocument()
    expect(screen.getByText('This server')).toBeInTheDocument()
    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()
    expect(screen.queryByText('No remote clients yet')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add remote client/i })).not.toBeInTheDocument()
  })

  it('renders the local server card with the active status indicator', () => {
    renderPage()

    expect(screen.getByText('This server')).toBeInTheDocument()
    expect(screen.getByText('Active target')).toBeInTheDocument()
    // When local is the active target the Use button is hidden;
    // the active badge alone conveys the state.
    expect(screen.queryByRole('button', { name: /use this server/i })).not.toBeInTheDocument()
  })

  it('checks health and switches to an online compatible remote client', async () => {
    const fetchMock = createRemoteClientsPageFetch()
    const user = userEvent.setup()
    renderPage(fetchMock)

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Studio NAS' } })
    fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: 'nas.local:9000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))
    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /check studio nas/i }))

    await waitFor(() => {
      expect(screen.getByText('Online')).toBeInTheDocument()
      expect(screen.getByText(/Borg UI 2\.2\.1/)).toBeInTheDocument()
    })
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Test',
      expect.objectContaining({ name: 'Studio NAS' }),
      {
        surface: 'remote_clients',
        status: 'online',
        compatibility: 'compatible',
      }
    )

    await user.click(screen.getByRole('button', { name: /use studio nas/i }))

    expect(screen.getByText('Active target')).toBeInTheDocument()
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Switch',
      expect.objectContaining({ name: 'Studio NAS' }),
      {
        surface: 'remote_clients',
        target_kind: 'remote',
      }
    )
  })

  it('shows validation errors for invalid server URLs', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Broken' } })
    fireEvent.change(screen.getByLabelText('Server URL'), {
      target: { value: 'ftp://example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Server URL must use HTTP or HTTPS.')
  })

  it('requires confirmation before deleting a remote client', async () => {
    const fetchMock = createRemoteClientsPageFetch()
    renderPage(fetchMock)

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Studio NAS' } })
    fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: 'nas.local:9000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))
    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /delete studio nas/i }))

    expect(screen.getByText('Studio NAS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Delete remote client?' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: 'Delete remote client?' })
      ).not.toBeInTheDocument()
    })
    expect(screen.getByText('Studio NAS')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /delete studio nas/i }))
    const deleteButton = screen.getByRole('button', { name: 'Delete client' })
    fireEvent.click(deleteButton)
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(screen.queryByText('Studio NAS')).not.toBeInTheDocument()
    })
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Delete',
      expect.objectContaining({ name: 'Studio NAS' }),
      { surface: 'remote_clients' }
    )

    const deleteCalls = fetchMock.mock.calls.filter(([input, init]) => {
      return String(input).includes('/api/remote-clients/') && (init?.method ?? 'GET') === 'DELETE'
    })
    expect(deleteCalls).toHaveLength(1)
  }, 30000)

  it('keeps the delete dialog open and shows an error when delete fails', async () => {
    const fetchMock = createRemoteClientsPageFetch({ deleteStatus: 500 })
    renderPage(fetchMock)

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Studio NAS' } })
    fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: 'nas.local:9000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))
    expect(await screen.findByText('Studio NAS')).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /delete studio nas/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete client' }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Remote client delete failed with HTTP 500.')
    })
    expect(screen.getByRole('heading', { name: 'Delete remote client?' })).toBeInTheDocument()
    expect(screen.getByText('Studio NAS')).toBeInTheDocument()
  }, 30000)
})
