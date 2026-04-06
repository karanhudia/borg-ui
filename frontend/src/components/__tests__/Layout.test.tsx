import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Layout from '../Layout'

const { logoutMock, hasConsentBeenGivenMock, loadUserPreferenceMock } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  hasConsentBeenGivenMock: vi.fn(),
  loadUserPreferenceMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth.tsx', () => ({
  useAuth: () => ({
    user: { username: 'admin', email: 'admin@example.com', role: 'admin' },
    logout: logoutMock,
  }),
}))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    roleHasGlobalPermission: (role: string, permission: string) =>
      role === 'admin' && permission === 'settings.users.manage',
  }),
}))

vi.mock('../../utils/analytics', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/analytics')>('../../utils/analytics')
  return {
    ...actual,
    hasConsentBeenGiven: () => hasConsentBeenGivenMock(),
    loadUserPreference: () => loadUserPreferenceMock(),
  }
})

vi.mock('../AnalyticsConsentBanner', () => ({
  default: ({ onConsentGiven }: { onConsentGiven: () => void }) => (
    <div>
      Consent Banner
      <button onClick={onConsentGiven}>Dismiss Banner</button>
    </div>
  ),
}))

vi.mock('../AppSidebar', () => ({
  default: () => <div>Sidebar</div>,
}))

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    loadUserPreferenceMock.mockResolvedValue(undefined)
    hasConsentBeenGivenMock.mockReturnValue(true)
  })

  it('shows the analytics consent banner when consent has not been given', async () => {
    hasConsentBeenGivenMock.mockReturnValue(false)

    renderWithProviders(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(await screen.findByText('Consent Banner')).toBeInTheDocument()
    expect(loadUserPreferenceMock).toHaveBeenCalledTimes(1)
  })

  it('hides the consent banner after consent is handled', async () => {
    hasConsentBeenGivenMock.mockReturnValue(false)
    const user = userEvent.setup()

    renderWithProviders(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await user.click(await screen.findByRole('button', { name: 'Dismiss Banner' }))

    await waitFor(() => {
      expect(screen.queryByText('Consent Banner')).not.toBeInTheDocument()
    })
  })

  it('renders the current user and logs out from the header action', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(screen.getByText('admin')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(await screen.findByRole('button', { name: /logout/i }))

    expect(logoutMock).toHaveBeenCalledTimes(1)
  })
})
