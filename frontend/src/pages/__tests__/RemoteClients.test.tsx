import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import RemoteClients from '../RemoteClients'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import { resetRemoteBackendStateForTests } from '../../services/remoteBackends/storage'

const { mockHasGlobalPermission } = vi.hoisted(() => ({
  mockHasGlobalPermission: vi.fn(() => true),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: mockHasGlobalPermission,
  }),
}))

function renderPage() {
  return renderWithProviders(
    <RemoteBackendProvider frontendVersion="2.2.2-alpha.1">
      <RemoteClients />
    </RemoteBackendProvider>,
    { initialRoute: '/remote-clients' }
  )
}

describe('RemoteClients', () => {
  beforeEach(() => {
    localStorage.clear()
    resetRemoteBackendStateForTests()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    mockHasGlobalPermission.mockReturnValue(true)
  })

  it('redirects when the user lacks SSH management permission', async () => {
    mockHasGlobalPermission.mockReturnValue(false)

    renderPage()

    await waitFor(() => {
      expect(window.location.pathname).toBe('/dashboard')
    })
  })

  it('adds and lists a remote client with normalized URL details', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(screen.getByRole('heading', { name: 'Remote Clients' })).toBeInTheDocument()
    expect(screen.getByText('No remote clients yet')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Studio NAS')
    await user.type(screen.getByLabelText('Backend URL'), 'nas.local:9000')
    await user.click(screen.getByRole('button', { name: 'Save client' }))

    expect(screen.getByText('Studio NAS')).toBeInTheDocument()
    expect(screen.getByText('http://nas.local:9000/api')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('checks health and switches to an online compatible remote client', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === 'http://nas.local:9000/health') {
        return Promise.resolve(new Response(JSON.stringify({ status: 'healthy' }), { status: 200 }))
      }
      if (url === 'http://nas.local:9000/api/system/info') {
        return Promise.resolve(
          new Response(JSON.stringify({ app_version: '2.2.1', borg_version: 'borg 1.4.0' }), {
            status: 200,
          })
        )
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Studio NAS')
    await user.type(screen.getByLabelText('Backend URL'), 'nas.local:9000')
    await user.click(screen.getByRole('button', { name: 'Save client' }))
    await user.click(await screen.findByRole('button', { name: /check studio nas/i }))

    await waitFor(() => {
      expect(screen.getByText('Online')).toBeInTheDocument()
      expect(screen.getByText(/Borg UI 2\.2\.1/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /use studio nas/i }))

    expect(screen.getByText('Active target')).toBeInTheDocument()
  })

  it('shows validation errors for invalid backend URLs', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Broken')
    await user.type(screen.getByLabelText('Backend URL'), 'ftp://example.com')
    await user.click(screen.getByRole('button', { name: 'Save client' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Backend URL must use HTTP or HTTPS.'
    )
  })
})
