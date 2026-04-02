import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import { AuthProvider, useAuth } from '../useAuth'

const getAuthConfigMock = vi.fn()
const getProfileMock = vi.fn()
const loginApiMock = vi.fn()
const logoutApiMock = vi.fn()
const setProxyAuthModeMock = vi.fn()

vi.mock('../../services/api', () => ({
  authAPI: {
    getAuthConfig: () => getAuthConfigMock(),
    getProfile: () => getProfileMock(),
    login: (username: string, password: string) => loginApiMock(username, password),
    logout: () => logoutApiMock(),
  },
  setProxyAuthMode: (enabled: boolean) => setProxyAuthModeMock(enabled),
}))

function AuthProbe() {
  const { user, isAuthenticated, isLoading, proxyAuthEnabled, login, logout } = useAuth()

  return (
    <div>
      <div>loading:{String(isLoading)}</div>
      <div>authenticated:{String(isAuthenticated)}</div>
      <div>proxy:{String(proxyAuthEnabled)}</div>
      <div>user:{user?.username ?? 'none'}</div>
      <button
        onClick={async () => {
          const mustChangePassword = await login('admin', 'secret')
          window.dispatchEvent(
            new CustomEvent('auth-login-result', { detail: { mustChangePassword } })
          )
        }}
      >
        Login
      </button>
      <button onClick={() => void logout()}>Logout</button>
    </div>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    getAuthConfigMock.mockResolvedValue({ data: { proxy_auth_enabled: false } })
    getProfileMock.mockResolvedValue({
      data: { id: 1, username: 'admin', email: 'admin@example.com', is_admin: true },
    })
    loginApiMock.mockResolvedValue({
      data: { access_token: 'jwt-token', must_change_password: false },
    })
    logoutApiMock.mockResolvedValue({})
  })

  it('hydrates a JWT session from an existing access token', async () => {
    localStorage.setItem('access_token', 'persisted-token')

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(setProxyAuthModeMock).toHaveBeenCalledWith(false)
      expect(getProfileMock).toHaveBeenCalledTimes(1)
      expect(screen.getByText('authenticated:true')).toBeInTheDocument()
      expect(screen.getByText('user:admin')).toBeInTheDocument()
    })
  })

  it('clears an invalid persisted JWT when profile loading fails', async () => {
    localStorage.setItem('access_token', 'stale-token')
    getProfileMock.mockRejectedValueOnce(new Error('invalid token'))

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('authenticated:false')).toBeInTheDocument()
      expect(screen.getByText('user:none')).toBeInTheDocument()
      expect(localStorage.getItem('access_token')).toBeNull()
    })
  })

  it('retries proxy-auth profile loading and authenticates when a later attempt succeeds', async () => {
    vi.useFakeTimers()
    getAuthConfigMock.mockResolvedValue({ data: { proxy_auth_enabled: true } })
    getProfileMock.mockRejectedValueOnce(new Error('temporary failure')).mockResolvedValueOnce({
      data: { id: 1, username: 'proxy-user', email: 'proxy@example.com', is_admin: true },
    })

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await vi.advanceTimersByTimeAsync(1000)

    await waitFor(() => {
      expect(setProxyAuthModeMock).toHaveBeenCalledWith(true)
      expect(screen.getByText('proxy:true')).toBeInTheDocument()
      expect(screen.getByText('authenticated:true')).toBeInTheDocument()
      expect(screen.getByText('user:proxy-user')).toBeInTheDocument()
    })

    vi.useRealTimers()
  })

  it('stores the token and updates auth state after login', async () => {
    const user = userEvent.setup()
    const loginResultListener = vi.fn()
    window.addEventListener('auth-login-result', loginResultListener as EventListener)

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:false')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() => {
      expect(loginApiMock).toHaveBeenCalledWith('admin', 'secret')
      expect(localStorage.getItem('access_token')).toBe('jwt-token')
      expect(screen.getByText('authenticated:true')).toBeInTheDocument()
      expect(screen.getByText('user:admin')).toBeInTheDocument()
    })

    window.removeEventListener('auth-login-result', loginResultListener as EventListener)
  })

  it('clears auth state on logout even when the API call fails', async () => {
    localStorage.setItem('access_token', 'persisted-token')
    logoutApiMock.mockRejectedValue(new Error('network error'))

    const user = userEvent.setup()

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:true')
    await user.click(screen.getByRole('button', { name: 'Logout' }))

    await waitFor(() => {
      expect(screen.getByText('authenticated:false')).toBeInTheDocument()
      expect(screen.getByText('user:none')).toBeInTheDocument()
      expect(localStorage.getItem('access_token')).toBeNull()
    })
  })
})
