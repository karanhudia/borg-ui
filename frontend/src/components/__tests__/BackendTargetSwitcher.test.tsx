import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../test/test-utils'
import BackendTargetSwitcher from '../BackendTargetSwitcher'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import {
  createRemoteBackendClient,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
  updateRemoteBackendHealth,
} from '../../services/remoteBackends/storage'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

function renderSwitcher() {
  return renderWithProviders(
    <RemoteBackendProvider>
      <BackendTargetSwitcher />
    </RemoteBackendProvider>
  )
}

describe('BackendTargetSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    resetRemoteBackendStateForTests()
  })

  it('shows the local backend as the default target', () => {
    renderSwitcher()

    expect(
      screen.getByRole('button', { name: /backend target local backend/i })
    ).toBeInTheDocument()
    expect(screen.getByText('Local')).toBeInTheDocument()
  })

  it('switches to a compatible remote backend', async () => {
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

    await user.click(screen.getByRole('button', { name: /backend target local backend/i }))
    const menu = await screen.findByRole('menu', { name: /backend targets/i })
    await user.click(within(menu).getByRole('menuitem', { name: /studio nas/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /backend target studio nas/i })).toBeInTheDocument()
      expect(screen.getByText('Remote')).toBeInTheDocument()
    })
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

    await user.click(screen.getByRole('button', { name: /backend target local backend/i }))
    const menu = await screen.findByRole('menu', { name: /backend targets/i })

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

    await user.click(screen.getByRole('button', { name: /backend target studio nas/i }))
    await user.click(await screen.findByRole('menuitem', { name: /manage remote clients/i }))

    expect(navigateMock).toHaveBeenCalledWith('/remote-clients')
  })
})
