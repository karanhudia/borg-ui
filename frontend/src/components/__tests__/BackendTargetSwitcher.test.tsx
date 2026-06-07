import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../test/test-utils'
import BackendTargetSwitcher from '../BackendTargetSwitcher'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import {
  createRemoteBackendClient,
  getActiveBackendTarget,
  listRemoteBackendClients,
  replaceRemoteBackendClients,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  updateRemoteBackendHealth,
} from '../../services/remoteBackends/storage'
import type { RemoteBackendClient } from '../../services/remoteBackends/types'

const navigateMock = vi.fn()
const { mockHasGlobalPermission, mockPlanCan, mockPlanIsLoading, mockTrackRemoteClient } =
  vi.hoisted(() => ({
    mockHasGlobalPermission: vi.fn((_permission: string) => true),
    mockPlanCan: vi.fn((_feature: string) => true),
    mockPlanIsLoading: vi.fn(() => false),
    mockTrackRemoteClient: vi.fn(),
  }))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    features: {},
    entitlement: undefined,
    isLoading: mockPlanIsLoading(),
    can: mockPlanCan,
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: mockHasGlobalPermission,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackRemoteClient: mockTrackRemoteClient,
    EventAction: {
      SWITCH: 'Switch',
    },
  }),
}))

function remoteClientResponse(client: RemoteBackendClient) {
  return {
    id: client.id,
    name: client.name,
    api_base_url: client.apiBaseUrl,
    web_base_url: client.webBaseUrl,
    created_at: client.createdAt,
    updated_at: client.updatedAt,
    health: {
      status: client.health.status,
      checked_at: client.health.checkedAt ?? null,
      app_version: client.health.appVersion ?? null,
      borg_version: client.health.borgVersion ?? null,
      borg2_version: client.health.borg2Version ?? null,
      error: client.health.error ?? null,
      compatibility: client.health.compatibility,
      compatibility_message: client.health.compatibilityMessage ?? null,
    },
  }
}

const switcherFetch: typeof fetch = async (input) => {
  const url = String(input)
  if (url.endsWith('/api/remote-clients')) {
    return new Response(JSON.stringify(listRemoteBackendClients().map(remoteClientResponse)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  throw new Error(`Unexpected fetch: ${url}`)
}

function renderSwitcher() {
  return renderWithProviders(
    <RemoteBackendProvider fetchImpl={switcherFetch}>
      <BackendTargetSwitcher />
    </RemoteBackendProvider>
  )
}

describe('BackendTargetSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    resetRemoteBackendStateForTests()
    mockHasGlobalPermission.mockReturnValue(true)
    mockPlanCan.mockReturnValue(true)
    mockPlanIsLoading.mockReturnValue(false)
    mockTrackRemoteClient.mockClear()
  })

  it('shows this server as the default target', () => {
    renderSwitcher()

    expect(screen.getByRole('button', { name: /server target this server/i })).toBeInTheDocument()
    expect(screen.getByText('Local')).toBeInTheDocument()
  })

  it('switches to a compatible remote client', async () => {
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '2.2.1',
      compatibility: 'compatible',
      compatibilityMessage: 'Compatible',
    })
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target this server/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })
    await user.click(within(menu).getByRole('menuitem', { name: /studio nas/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /server target studio nas/i })).toBeInTheDocument()
      expect(screen.getByText('Remote client')).toBeInTheDocument()
    })
    expect(mockTrackRemoteClient).toHaveBeenCalledWith(
      'Switch',
      expect.objectContaining({ name: 'Studio NAS' }),
      {
        surface: 'target_switcher',
        target_kind: 'remote',
      }
    )
  })

  it('keeps the selected remote client active while plan access is loading', () => {
    mockPlanCan.mockImplementation((feature) => feature !== 'remote_clients')
    mockPlanIsLoading.mockReturnValue(true)
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '2.2.1',
      compatibility: 'compatible',
      compatibilityMessage: 'Compatible',
    })
    setActiveBackendTarget(remote.id)

    renderSwitcher()

    expect(screen.getByRole('button', { name: /server target studio nas/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /server target this server/i })
    ).not.toBeInTheDocument()
    expect(getActiveBackendTarget().id).toBe(remote.id)
  })

  it('keeps the selected remote visible while saved clients hydrate', async () => {
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '2.2.1',
      compatibility: 'compatible',
      compatibilityMessage: 'Compatible',
    })
    setActiveBackendTarget(remote.id)
    replaceRemoteBackendClients([])
    const user = userEvent.setup()

    renderSwitcher()

    expect(screen.getByRole('button', { name: /server target studio nas/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /server target studio nas/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })
    expect(within(menu).getByRole('menuitem', { name: /studio nas/i })).toBeInTheDocument()
  })

  it('keeps the local server available but blocks remote switching when the plan lacks access', async () => {
    mockPlanCan.mockImplementation((feature) => feature !== 'remote_clients')
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '2.2.1',
      compatibility: 'compatible',
      compatibilityMessage: 'Compatible',
    })
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target this server/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })

    expect(within(menu).getByRole('menuitem', { name: /this server/i })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    )
    expect(within(menu).getByRole('menuitem', { name: /studio nas/i })).toHaveAttribute(
      'aria-disabled',
      'true'
    )

    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('disables incompatible remote targets', async () => {
    const remote = createRemoteBackendClient({
      name: 'Old Server',
      backendUrl: 'old.example.com',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '1.9.0',
      compatibility: 'incompatible',
      compatibilityMessage: 'Major version mismatch',
    })
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target this server/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })

    expect(within(menu).getByRole('menuitem', { name: /old server/i })).toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })

  it('navigates to remote client management', async () => {
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    setActiveBackendTarget(remote.id)
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target studio nas/i }))
    await user.click(await screen.findByRole('menuitem', { name: /manage remote clients/i }))

    expect(navigateMock).toHaveBeenCalledWith('/remote-clients')
  })

  it('does not navigate to remote client management when the plan lacks access', async () => {
    mockPlanCan.mockImplementation((feature) => feature !== 'remote_clients')
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target this server/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })
    const upgradeItem = within(menu).getByRole('menuitem', {
      name: /remote clients require pro/i,
    })

    expect(upgradeItem).toHaveAttribute('aria-disabled', 'true')
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('blocks stale remote targets when the user lacks remote client admin permission', async () => {
    mockHasGlobalPermission.mockReturnValue(false)
    const remote = createRemoteBackendClient({
      name: 'Studio NAS',
      backendUrl: 'nas.local:9000',
    })
    updateRemoteBackendHealth(remote.id, {
      status: 'online',
      checkedAt: '2026-06-05T00:00:00.000Z',
      appVersion: '2.2.1',
      compatibility: 'compatible',
      compatibilityMessage: 'Compatible',
    })
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /server target this server/i }))
    const menu = await screen.findByRole('menu', { name: /server targets/i })

    expect(within(menu).getByRole('menuitem', { name: /studio nas/i })).toHaveAttribute(
      'aria-disabled',
      'true'
    )

    expect(within(menu).getByRole('menuitem', { name: /this server/i })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })
})
