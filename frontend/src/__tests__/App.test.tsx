import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../test/test-utils'
import App from '../App'

const { useAuthMock, loadUserPreferenceMock, initAnalyticsIfEnabledMock, protectedRouteMock } =
  vi.hoisted(() => ({
    useAuthMock: vi.fn(),
    loadUserPreferenceMock: vi.fn().mockResolvedValue(undefined),
    initAnalyticsIfEnabledMock: vi.fn(),
    protectedRouteMock: vi.fn(),
  }))

vi.mock('../hooks/useAuth.tsx', () => ({
  useAuth: () => useAuthMock(),
}))

vi.mock('../utils/analytics', () => ({
  loadUserPreference: loadUserPreferenceMock,
  initAnalyticsIfEnabled: initAnalyticsIfEnabledMock,
}))

vi.mock('../components/Layout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>Layout{children}</div>,
}))

vi.mock('../components/UmamiTracker', () => ({
  UmamiTracker: () => <div>Umami Tracker</div>,
}))

vi.mock('../components/AnnouncementManager', () => ({
  default: () => <div>Announcement Manager</div>,
}))

vi.mock('../components/ProtectedRoute', () => ({
  default: ({ children, requiredTab }: { children: React.ReactNode; requiredTab: string }) => {
    protectedRouteMock(requiredTab)
    return (
      <div>
        <span>Protected:{requiredTab}</span>
        {children}
      </div>
    )
  },
}))

vi.mock('../pages/Login', () => ({
  default: () => <div>Login Page</div>,
}))
vi.mock('../pages/DashboardV3', () => ({
  default: () => <div>Dashboard Page</div>,
}))
vi.mock('../pages/Backup', () => ({
  default: () => <div>Backup Page</div>,
}))
vi.mock('../pages/Archives', () => ({
  default: () => <div>Archives Page</div>,
}))
vi.mock('../pages/Restore', () => ({
  default: () => <div>Restore Page</div>,
}))
vi.mock('../pages/Schedule', () => ({
  default: () => <div>Schedule Page</div>,
}))
vi.mock('../pages/Repositories', () => ({
  default: () => <div>Repositories Page</div>,
}))
vi.mock('../pages/SSHConnectionsSingleKey', () => ({
  default: () => <div>SSH Connections Page</div>,
}))
vi.mock('../pages/Activity', () => ({
  default: () => <div>Activity Page</div>,
}))
vi.mock('../pages/Settings', () => ({
  default: () => <div>Settings Page</div>,
}))

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      proxyAuthEnabled: false,
    })
  })

  it('shows the loading spinner while auth is loading', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      proxyAuthEnabled: false,
    })

    renderWithProviders(<App />)

    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('shows the proxy-auth loading spinner instead of the login page', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      proxyAuthEnabled: true,
    })

    renderWithProviders(<App />, { initialRoute: '/login' })

    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('renders the login route when unauthenticated in JWT mode', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      proxyAuthEnabled: false,
    })

    renderWithProviders(<App />, { initialRoute: '/backup' })

    expect(await screen.findByText('Login Page')).toBeInTheDocument()
    expect(screen.getByText('Umami Tracker')).toBeInTheDocument()
    expect(screen.queryByText('Layout')).not.toBeInTheDocument()
    expect(screen.queryByText('Announcement Manager')).not.toBeInTheDocument()
  })

  it('renders the authenticated app shell and redirects root to dashboard', async () => {
    renderWithProviders(<App />, { initialRoute: '/' })

    expect(await screen.findByText('Dashboard Page')).toBeInTheDocument()
    expect(screen.getByText('Layout')).toBeInTheDocument()
    expect(screen.getByText('Umami Tracker')).toBeInTheDocument()
    expect(screen.getByText('Announcement Manager')).toBeInTheDocument()
  })

  it('wraps guarded routes with the expected required tab', async () => {
    renderWithProviders(<App />, { initialRoute: '/backup' })

    expect(await screen.findByText('Backup Page')).toBeInTheDocument()
    expect(screen.getByText('Protected:backups')).toBeInTheDocument()
    expect(protectedRouteMock).toHaveBeenCalledWith('backups')
  })

  it('redirects legacy scripts route to settings/scripts', async () => {
    renderWithProviders(<App />, { initialRoute: '/scripts' })

    expect(await screen.findByText('Settings Page')).toBeInTheDocument()
    await waitFor(() => {
      expect(window.location.pathname).toBe('/settings/scripts')
    })
  })

  it('loads analytics preferences and initializes analytics on mount', async () => {
    renderWithProviders(<App />, { initialRoute: '/dashboard' })

    await waitFor(() => {
      expect(loadUserPreferenceMock).toHaveBeenCalledTimes(1)
      expect(initAnalyticsIfEnabledMock).toHaveBeenCalledTimes(1)
    })
  })
})
