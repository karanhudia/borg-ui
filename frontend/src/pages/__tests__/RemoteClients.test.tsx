import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import RemoteClients from '../RemoteClients'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import {
  createRemoteBackendClient,
  resetRemoteBackendStateForTests,
} from '../../services/remoteBackends/storage'

const { mockHasGlobalPermission, mockPlanCan } = vi.hoisted(() => ({
  mockHasGlobalPermission: vi.fn(() => true),
  mockPlanCan: vi.fn((_feature: string) => true),
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
    mockPlanCan.mockReturnValue(true)
  })

  it('redirects when the user lacks SSH management permission', async () => {
    mockHasGlobalPermission.mockReturnValue(false)

    renderPage()

    expect(
      await screen.findByText('You do not have permission to open this page')
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(window.location.pathname).toBe('/dashboard')
    })
  })

  it('adds and lists a remote client with normalized URL details', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(screen.getByRole('heading', { name: 'Remote Clients' })).toBeInTheDocument()
    expect(screen.getByText('No remote clients yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /use this server/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Studio NAS')
    await user.type(screen.getByLabelText('Server URL'), 'nas.local:9000')
    await user.click(screen.getByRole('button', { name: 'Save client' }))

    expect(screen.getByText('Studio NAS')).toBeInTheDocument()
    expect(screen.getByText('http://nas.local:9000/api')).toBeInTheDocument()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('shows the plan gate instead of management controls when remote clients are unavailable', async () => {
    mockPlanCan.mockImplementation((feature) => feature !== 'remote_clients')

    renderPage()

    expect(
      await screen.findByText(/remote client switching is available on pro and enterprise plans/i)
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add remote client/i })).not.toBeInTheDocument()
    expect(screen.queryByText('No remote clients yet')).not.toBeInTheDocument()
  })

  it('vertically centers the local server status and use action', () => {
    renderPage()

    const useLocalButton = screen.getByRole('button', { name: /use this server/i })
    const actionGroup = useLocalButton.parentElement

    expect(actionGroup).not.toBeNull()
    expect(getComputedStyle(actionGroup!).alignItems).toBe('center')
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

    fireEvent.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Studio NAS')
    await user.type(screen.getByLabelText('Server URL'), 'nas.local:9000')
    fireEvent.click(screen.getByRole('button', { name: 'Save client' }))
    await user.click(await screen.findByRole('button', { name: /check studio nas/i }))

    await waitFor(() => {
      expect(screen.getByText('Online')).toBeInTheDocument()
      expect(screen.getByText(/Borg UI 2\.2\.1/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /use studio nas/i }))

    expect(screen.getByText('Active target')).toBeInTheDocument()
  })

  it('shows validation errors for invalid server URLs', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: /add remote client/i }))
    await user.type(screen.getByLabelText('Client name'), 'Broken')
    await user.type(screen.getByLabelText('Server URL'), 'ftp://example.com')
    await user.click(screen.getByRole('button', { name: 'Save client' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Server URL must use HTTP or HTTPS.')
  })

  it('requires confirmation before deleting a remote client', async () => {
    createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /delete studio nas/i }))

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
    fireEvent.click(screen.getByRole('button', { name: 'Delete client' }))

    expect(screen.queryByText('Studio NAS')).not.toBeInTheDocument()
  })
})
