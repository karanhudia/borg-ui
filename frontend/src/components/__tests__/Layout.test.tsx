import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Layout from '../Layout'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import {
  createRemoteBackendClient,
  resetRemoteBackendStateForTests,
  setActiveBackendTarget,
} from '../../services/remoteBackends/storage'

const {
  logoutMock,
  refreshUserMock,
  hasConsentBeenGivenMock,
  loadUserPreferenceMock,
  announcementSurfaceMock,
  useAuthMock,
} = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  refreshUserMock: vi.fn(),
  hasConsentBeenGivenMock: vi.fn(),
  loadUserPreferenceMock: vi.fn(),
  announcementSurfaceMock: vi.fn(),
  useAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth.tsx', () => ({
  useAuth: () => useAuthMock(),
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

vi.mock('../../hooks/useAnnouncementSurface', () => ({
  useAnnouncementSurface: () => announcementSurfaceMock(),
}))

vi.mock('../AnalyticsConsentBanner', () => ({
  default: ({ onConsentGiven }: { onConsentGiven: () => void }) => (
    <div>
      Consent Banner
      <button onClick={onConsentGiven}>Dismiss Banner</button>
    </div>
  ),
}))

vi.mock('../AnnouncementModal', () => ({
  default: ({
    announcement,
    open,
    onAcknowledge,
  }: {
    announcement: { title: string } | null
    open: boolean
    onAcknowledge: () => void
  }) =>
    open && announcement ? (
      <div>
        Announcement Modal
        <div>{announcement.title}</div>
        <button onClick={onAcknowledge}>Dismiss Announcement</button>
      </div>
    ) : null,
}))

vi.mock('../PasskeyEnrollmentPrompt', () => ({
  default: ({
    open,
    onSnooze,
    onIgnore,
  }: {
    open: boolean
    onSnooze: () => void
    onIgnore: () => void
  }) =>
    open ? (
      <div>
        Passkey Prompt
        <button onClick={onSnooze}>Snooze Passkey Prompt</button>
        <button onClick={onIgnore}>Ignore Passkey Prompt</button>
      </div>
    ) : null,
}))

vi.mock('../AppSidebar', () => ({
  default: () => <div>Sidebar</div>,
}))

function RemoteBackendSwitchButton() {
  return (
    <button
      onClick={() => {
        const remote = createRemoteBackendClient({
          name: 'Remote',
          backendUrl: 'remote.example.com',
        })
        setActiveBackendTarget(remote.id)
      }}
    >
      Switch backend
    </button>
  )
}

function renderLayout(
  ui: Parameters<typeof renderWithProviders>[0],
  options?: Parameters<typeof renderWithProviders>[1]
) {
  return renderWithProviders(<RemoteBackendProvider>{ui}</RemoteBackendProvider>, options)
}

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    resetRemoteBackendStateForTests()
    sessionStorage.clear()
    loadUserPreferenceMock.mockResolvedValue(undefined)
    hasConsentBeenGivenMock.mockReturnValue(true)
    announcementSurfaceMock.mockReturnValue({
      announcement: null,
      acknowledgeAnnouncement: vi.fn(),
      snoozeAnnouncement: vi.fn(),
      trackAnnouncementCtaClick: vi.fn(),
    })
    useAuthMock.mockReturnValue({
      user: { username: 'admin', email: 'admin@example.com', role: 'admin', passkey_count: 0 },
      proxyAuthEnabled: false,
      hasGlobalPermission: () => true,
      canEnrollPasskeyFromRecentLogin: true,
      clearRecentPasskeyEnrollmentState: vi.fn(),
      refreshUser: refreshUserMock,
      logout: logoutMock,
    })
  })

  it('shows the analytics consent banner when consent has not been given', async () => {
    hasConsentBeenGivenMock.mockReturnValue(false)

    renderLayout(
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

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await user.click(
      await screen.findByRole('button', { name: 'Dismiss Banner' }, { timeout: 5000 })
    )

    await waitFor(() => {
      expect(screen.queryByText('Consent Banner')).not.toBeInTheDocument()
    })
  })

  it('renders the current user and logs out from the header action', async () => {
    const user = userEvent.setup()

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(screen.getByText('admin')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(await screen.findByRole('button', { name: /logout/i }))

    expect(logoutMock).toHaveBeenCalledTimes(1)
  })

  it('clears query data when the active backend target changes', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(['repositories'], [{ id: 1, name: 'Local Repo' }])
    const user = userEvent.setup()

    renderWithProviders(
      <RemoteBackendProvider>
        <Layout>
          <RemoteBackendSwitchButton />
        </Layout>
      </RemoteBackendProvider>,
      { queryClient }
    )

    expect(queryClient.getQueryData(['repositories'])).toEqual([{ id: 1, name: 'Local Repo' }])

    await user.click(screen.getByRole('button', { name: 'Switch backend' }))

    await waitFor(() => {
      expect(queryClient.getQueryData(['repositories'])).toBeUndefined()
    })
  })

  it('shows the passkey prompt before analytics even when password setup is still pending', async () => {
    hasConsentBeenGivenMock.mockReturnValue(false)
    sessionStorage.setItem('recent_password_login', '1')
    useAuthMock.mockReturnValue({
      user: {
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        must_change_password: true,
        passkey_count: 0,
      },
      proxyAuthEnabled: false,
      hasGlobalPermission: () => true,
      canEnrollPasskeyFromRecentLogin: true,
      clearRecentPasskeyEnrollmentState: vi.fn(),
      refreshUser: refreshUserMock,
      logout: logoutMock,
    })

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>,
      { initialRoute: '/dashboard' }
    )

    expect(await screen.findByText('Passkey Prompt')).toBeInTheDocument()
    expect(screen.queryByText('Consent Banner')).not.toBeInTheDocument()
  })

  it('shows the passkey prompt after a recent password login when no passkeys exist', async () => {
    sessionStorage.setItem('recent_password_login', '1')

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(await screen.findByText('Passkey Prompt')).toBeInTheDocument()
  })

  it('does not show the passkey prompt for users who already have passkeys', async () => {
    sessionStorage.setItem('recent_password_login', '1')
    useAuthMock.mockReturnValue({
      user: { username: 'admin', email: 'admin@example.com', role: 'admin', passkey_count: 1 },
      proxyAuthEnabled: false,
      hasGlobalPermission: () => true,
      canEnrollPasskeyFromRecentLogin: true,
      clearRecentPasskeyEnrollmentState: vi.fn(),
      refreshUser: refreshUserMock,
      logout: logoutMock,
    })

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await waitFor(() => {
      expect(screen.queryByText('Passkey Prompt')).not.toBeInTheDocument()
    })
  })

  it('snoozes the passkey prompt and shows it again after the snooze expires', async () => {
    sessionStorage.setItem('recent_password_login', '1')
    const user = userEvent.setup()

    const { unmount } = renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await user.click(await screen.findByRole('button', { name: 'Snooze Passkey Prompt' }))

    await waitFor(() => {
      expect(screen.queryByText('Passkey Prompt')).not.toBeInTheDocument()
      expect(Number(localStorage.getItem('passkey_prompt_snoozed_admin'))).toBeGreaterThan(
        Date.now()
      )
      expect(sessionStorage.getItem('recent_password_login')).toBeNull()
    })

    sessionStorage.setItem('recent_password_login', '1')
    unmount()
    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await waitFor(() => {
      expect(screen.queryByText('Passkey Prompt')).not.toBeInTheDocument()
    })

    localStorage.setItem('passkey_prompt_snoozed_admin', String(Date.now() - 1000))
    sessionStorage.setItem('recent_password_login', '1')
    unmount()
    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(await screen.findByText('Passkey Prompt')).toBeInTheDocument()
  })

  it('can ignore the passkey prompt on this device', async () => {
    sessionStorage.setItem('recent_password_login', '1')
    const user = userEvent.setup()

    const { unmount } = renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await user.click(await screen.findByRole('button', { name: 'Ignore Passkey Prompt' }))

    await waitFor(() => {
      expect(screen.queryByText('Passkey Prompt')).not.toBeInTheDocument()
      expect(localStorage.getItem('passkey_prompt_ignored_admin')).toBe('1')
      expect(sessionStorage.getItem('recent_password_login')).toBeNull()
    })

    sessionStorage.setItem('recent_password_login', '1')
    unmount()
    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    await waitFor(() => {
      expect(screen.queryByText('Passkey Prompt')).not.toBeInTheDocument()
    })
  })

  it('suppresses announcements while the passkey prompt is active', async () => {
    sessionStorage.setItem('recent_password_login', '1')
    announcementSurfaceMock.mockReturnValue({
      announcement: {
        id: 'update-1',
        type: 'update_available',
        title: 'Update Available',
        message: 'A new version is ready.',
      },
      acknowledgeAnnouncement: vi.fn(),
      snoozeAnnouncement: vi.fn(),
      trackAnnouncementCtaClick: vi.fn(),
    })

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(await screen.findByText('Passkey Prompt')).toBeInTheDocument()
    expect(screen.queryByText('Announcement Modal')).not.toBeInTheDocument()
  })

  it('shows the analytics consent banner before announcements', async () => {
    hasConsentBeenGivenMock.mockReturnValue(false)
    announcementSurfaceMock.mockReturnValue({
      announcement: {
        id: 'update-1',
        type: 'update_available',
        title: 'Update Available',
        message: 'A new version is ready.',
      },
      acknowledgeAnnouncement: vi.fn(),
      snoozeAnnouncement: vi.fn(),
      trackAnnouncementCtaClick: vi.fn(),
    })

    renderLayout(
      <Layout>
        <div>Page Content</div>
      </Layout>
    )

    expect(await screen.findByText('Consent Banner')).toBeInTheDocument()
    expect(screen.queryByText('Announcement Modal')).not.toBeInTheDocument()
  })
})
