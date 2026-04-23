import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../test/test-utils'
import App from '../App'

const {
  useAuthMock,
  loadUserPreferenceMock,
  initAnalyticsIfEnabledMock,
  identifyUserMock,
  protectedRouteMock,
} = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  loadUserPreferenceMock: vi.fn().mockResolvedValue(undefined),
  initAnalyticsIfEnabledMock: vi.fn(),
  identifyUserMock: vi.fn(),
  protectedRouteMock: vi.fn(),
}))

vi.mock('../hooks/useAuth.tsx', () => ({
  useAuth: () => useAuthMock(),
}))

vi.mock('../utils/analytics', () => ({
  loadUserPreference: loadUserPreferenceMock,
  initAnalyticsIfEnabled: initAnalyticsIfEnabledMock,
  identifyUser: identifyUserMock,
}))

vi.mock('../components/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>Layout{children}</div>,
}))

vi.mock('../components/UmamiTracker', () => ({
  UmamiTracker: () => <div>Umami Tracker</div>,
}))

vi.mock('../components/ProtectedRoute', () => ({
  default: ({ children, requiredTab }: { children: ReactNode; requiredTab: string }) => {
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
      mustChangePassword: false,
      proxyAuthEnabled: false,
      insecureNoAuthEnabled: false,
      proxyAuthWarnings: [],
      user: { username: 'admin', must_change_password: false },
    })
  })

  it('shows the loading spinner while auth is loading', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      mustChangePassword: false,
      proxyAuthEnabled: false,
      insecureNoAuthEnabled: false,
      proxyAuthWarnings: [],
      user: null,
    })

    renderWithProviders(<App />)

    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('shows the proxy-auth loading spinner instead of the login page', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      mustChangePassword: false,
      proxyAuthEnabled: true,
      insecureNoAuthEnabled: false,
      proxyAuthHeader: 'X-Forwarded-User',
      proxyAuthWarnings: [],
      authError: null,
      user: null,
    })

    renderWithProviders(<App />, { initialRoute: '/login' })

    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('shows a proxy-auth guidance screen when proxy auth is enabled but identity is missing', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      mustChangePassword: false,
      proxyAuthEnabled: true,
      insecureNoAuthEnabled: false,
      proxyAuthHeader: 'X-Forwarded-User',
      proxyAuthWarnings: [{ code: 'broad_bind', message: 'Bound broadly' }],
      authError: 'Reverse proxy authentication header "X-Forwarded-User" is required',
      user: null,
    })

    renderWithProviders(<App />, { initialRoute: '/login' })

    expect(screen.getByText('Proxy authentication required')).toBeInTheDocument()
    expect(
      screen.getByText('Reverse proxy authentication header "X-Forwarded-User" is required')
    ).toBeInTheDocument()
    expect(screen.getByText('Proxy auth configuration warnings')).toBeInTheDocument()
    expect(screen.getByText('Bound broadly')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('renders the login route when unauthenticated in JWT mode', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      mustChangePassword: false,
      proxyAuthEnabled: false,
      insecureNoAuthEnabled: false,
      proxyAuthWarnings: [],
      user: null,
    })

    renderWithProviders(<App />, { initialRoute: '/backup' })

    expect(await screen.findByText('Login Page')).toBeInTheDocument()
    expect(screen.getByText('Umami Tracker')).toBeInTheDocument()
    expect(screen.queryByText('Layout')).not.toBeInTheDocument()
  })

  it('renders the authenticated app shell and redirects root to dashboard', async () => {
    renderWithProviders(<App />, { initialRoute: '/' })

    expect(await screen.findByText('Dashboard Page')).toBeInTheDocument()
    expect(screen.getByText('Layout')).toBeInTheDocument()
    expect(screen.getByText('Umami Tracker')).toBeInTheDocument()
  })

  it('keeps authenticated first-login users on the auth screen until password setup is handled', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      mustChangePassword: true,
      proxyAuthEnabled: false,
      insecureNoAuthEnabled: false,
      proxyAuthWarnings: [],
      user: { username: 'admin', must_change_password: true },
    })

    renderWithProviders(<App />, { initialRoute: '/backup' })

    expect(await screen.findByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Layout')).not.toBeInTheDocument()
    await waitFor(() => {
      expect(window.location.pathname).toBe('/login')
    })
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

  it('skips the local login shell in insecure no-auth mode', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      mustChangePassword: true,
      proxyAuthEnabled: false,
      insecureNoAuthEnabled: true,
      proxyAuthWarnings: [],
      authError: null,
      user: { username: 'admin', must_change_password: true },
    })

    renderWithProviders(<App />, { initialRoute: '/dashboard' })

    expect(await screen.findByText('Dashboard Page')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
    expect(screen.queryByText('Proxy authentication required')).not.toBeInTheDocument()
  })
})
