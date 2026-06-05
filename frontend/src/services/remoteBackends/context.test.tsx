import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
} from '../../test/test-utils'
import { LOCAL_BACKEND_ID, resetRemoteBackendStateForTests } from './storage'
import { RemoteBackendProvider, useRemoteBackends } from './context'

function RemoteBackendProbe() {
  const { activeTarget, clients, createClient, switchTarget, checkClient, deleteClient } =
    useRemoteBackends()
  const firstClient = clients[0]

  return (
    <div>
      <div>active:{activeTarget.name}</div>
      <div>active-id:{activeTarget.id}</div>
      <div>clients:{clients.length}</div>
      <div>status:{firstClient?.health.status ?? 'none'}</div>
      <div>version:{firstClient?.health.appVersion ?? 'none'}</div>
      <div>compatibility:{firstClient?.health.compatibility ?? 'none'}</div>
      <button
        onClick={() =>
          createClient({
            name: 'Studio NAS',
            backendUrl: 'nas.local:9000',
          })
        }
      >
        Add
      </button>
      <button onClick={() => firstClient && switchTarget(firstClient.id)}>SwitchRemote</button>
      <button onClick={() => switchTarget(LOCAL_BACKEND_ID)}>SwitchLocal</button>
      <button onClick={() => firstClient && void checkClient(firstClient.id)}>Check</button>
      <button onClick={() => firstClient && deleteClient(firstClient.id)}>Delete</button>
    </div>
  )
}

describe('RemoteBackendProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('creates clients and switches between local and remote targets', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    expect(screen.getByText('active:Local backend')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByText('clients:1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'SwitchRemote' }))
    expect(screen.getByText('active:Studio NAS')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'SwitchLocal' }))
    expect(screen.getByText('active:Local backend')).toBeInTheDocument()
  })

  it('checks reachability and version compatibility for a remote client', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === 'http://nas.local:9000/health') {
        return Promise.resolve(new Response(JSON.stringify({ status: 'healthy' }), { status: 200 }))
      }
      if (url === 'http://nas.local:9000/api/system/info') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_version: '2.1.0',
              borg_version: 'borg 1.4.0',
              borg2_version: 'borg2 2.0.0',
            }),
            { status: 200 }
          )
        )
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider frontendVersion="2.2.2-alpha.1">
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:online')).toBeInTheDocument()
      expect(screen.getByText('version:2.1.0')).toBeInTheDocument()
      expect(screen.getByText('compatibility:compatible')).toBeInTheDocument()
    })
  })

  it('keeps an unreachable remote client inactive and records the error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network unavailable')))
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText('status:offline')).toBeInTheDocument()
      expect(screen.getByText('compatibility:unknown')).toBeInTheDocument()
      expect(screen.getByText('active:Local backend')).toBeInTheDocument()
    })
  })

  it('times out stalled health checks and records the abort error', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const error = new Error('Aborted')
            error.name = 'AbortError'
            reject(error)
          })
        })
    )
    renderWithProviders(
      <RemoteBackendProvider fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
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
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === 'http://nas.local:9000/health') {
        healthCallCount += 1
        if (healthCallCount === 1) {
          return Promise.resolve(
            new Response(JSON.stringify({ status: 'healthy' }), { status: 200 })
          )
        }
        return Promise.resolve(new Response(JSON.stringify({ status: 'down' }), { status: 503 }))
      }
      if (url === 'http://nas.local:9000/api/system/info') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            new Promise<Record<string, unknown>>((resolve) => {
              firstSystemInfoResolve = resolve
            }),
        } as Response)
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })
    const user = userEvent.setup()
    renderWithProviders(
      <RemoteBackendProvider frontendVersion="2.2.2-alpha.1" fetchImpl={fetchMock}>
        <RemoteBackendProbe />
      </RemoteBackendProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Add' }))
    await user.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
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
