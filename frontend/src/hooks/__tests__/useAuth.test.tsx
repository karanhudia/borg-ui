import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import { AuthProvider, useAuth } from '../useAuth'

const getAuthConfigMock = vi.fn()
const getProfileMock = vi.fn()
const loginApiMock = vi.fn()
const verifyTotpLoginApiMock = vi.fn()
const beginPasskeyAuthenticationApiMock = vi.fn()
const finishPasskeyAuthenticationApiMock = vi.fn()
const skipPasswordSetupApiMock = vi.fn()
const logoutApiMock = vi.fn()
const setAuthTransportModeMock = vi.fn()
const setFetchAuthModeMock = vi.fn()
const fetchJsonForAuthModeMock = vi.fn()
const getPasskeyAssertionMock = vi.fn()

vi.mock('../../services/api', () => ({
  authAPI: {
    getAuthConfig: () => getAuthConfigMock(),
    getProfile: () => getProfileMock(),
    login: (username: string, password: string) => loginApiMock(username, password),
    verifyTotpLogin: (challengeToken: string, code: string) =>
      verifyTotpLoginApiMock(challengeToken, code),
    beginPasskeyAuthentication: () => beginPasskeyAuthenticationApiMock(),
    finishPasskeyAuthentication: (ceremonyToken: string, credential: unknown) =>
      finishPasskeyAuthenticationApiMock(ceremonyToken, credential),
    skipPasswordSetup: () => skipPasswordSetupApiMock(),
    logout: () => logoutApiMock(),
  },
  setAuthTransportMode: (mode: 'jwt' | 'proxy' | 'insecure-no-auth') =>
    setAuthTransportModeMock(mode),
}))

vi.mock('../../services/authRequest', () => ({
  fetchJsonForAuthMode: (path: string, init?: RequestInit, mode?: string) =>
    fetchJsonForAuthModeMock(path, init, mode),
  setFetchAuthMode: (mode: 'jwt' | 'proxy' | 'insecure-no-auth') => setFetchAuthModeMock(mode),
}))

vi.mock('../../utils/webauthn', () => ({
  getPasskeyAssertion: () => getPasskeyAssertionMock(),
}))

function AuthProbe() {
  const {
    user,
    isAuthenticated,
    isLoading,
    proxyAuthEnabled,
    insecureNoAuthEnabled,
    proxyAuthHeader,
    proxyAuthWarnings,
    authError,
    login,
    verifyTotpLogin,
    loginWithPasskey,
    markRecentPasswordConfirmation,
    logout,
  } = useAuth()

  return (
    <div>
      <div>loading:{String(isLoading)}</div>
      <div>authenticated:{String(isAuthenticated)}</div>
      <div>proxy:{String(proxyAuthEnabled)}</div>
      <div>insecure:{String(insecureNoAuthEnabled)}</div>
      <div>proxy-header:{proxyAuthHeader ?? 'none'}</div>
      <div>
        proxy-warnings:{proxyAuthWarnings.map((warning) => warning.code).join(',') || 'none'}
      </div>
      <div>auth-error:{authError ?? 'none'}</div>
      <div>user:{user?.username ?? 'none'}</div>
      <button
        onClick={async () => {
          const result = await login('admin', 'secret')
          window.dispatchEvent(new CustomEvent('auth-login-result', { detail: result }))
        }}
      >
        Login
      </button>
      <button onClick={() => void verifyTotpLogin('challenge-token', '123456')}>VerifyTotp</button>
      <button onClick={() => void loginWithPasskey()}>PasskeyLogin</button>
      <button onClick={() => markRecentPasswordConfirmation('fresh-password')}>
        MarkRecentPassword
      </button>
      <button onClick={() => void logout()}>Logout</button>
    </div>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    getAuthConfigMock.mockResolvedValue({
      data: {
        proxy_auth_enabled: false,
        insecure_no_auth_enabled: false,
        proxy_auth_header: null,
        proxy_auth_health: { enabled: false, warnings: [] },
      },
    })
    getProfileMock.mockResolvedValue({
      data: {
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        all_repositories_role: null,
        global_permissions: ['settings.users.manage'],
      },
    })
    loginApiMock.mockResolvedValue({
      data: { access_token: 'jwt-token', must_change_password: false, totp_required: false },
    })
    verifyTotpLoginApiMock.mockResolvedValue({
      data: { access_token: 'jwt-token', must_change_password: false },
    })
    beginPasskeyAuthenticationApiMock.mockResolvedValue({
      data: { ceremony_token: 'ceremony-token', options: {} },
    })
    finishPasskeyAuthenticationApiMock.mockResolvedValue({
      data: { access_token: 'jwt-token', must_change_password: false },
    })
    skipPasswordSetupApiMock.mockResolvedValue({
      data: { must_change_password: false },
    })
    getPasskeyAssertionMock.mockResolvedValue({ id: 'credential-id' })
    logoutApiMock.mockResolvedValue({})
    fetchJsonForAuthModeMock.mockReset()
  })

  it('hydrates a JWT session from an existing access token', async () => {
    localStorage.setItem('access_token', 'persisted-token')

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(setAuthTransportModeMock).toHaveBeenCalledWith('jwt')
      expect(setFetchAuthModeMock).toHaveBeenCalledWith('jwt')
      expect(screen.getByText('insecure:false')).toBeInTheDocument()
      expect(getProfileMock).toHaveBeenCalledTimes(1)
      expect(screen.getByText('authenticated:true')).toBeInTheDocument()
      expect(screen.getByText('proxy-warnings:none')).toBeInTheDocument()
      expect(screen.getByText('user:admin')).toBeInTheDocument()
    })
  })

  it('loads the profile without a JWT in insecure no-auth mode', async () => {
    getAuthConfigMock.mockResolvedValue({
      data: {
        proxy_auth_enabled: false,
        insecure_no_auth_enabled: true,
        proxy_auth_header: null,
        proxy_auth_health: { enabled: false, warnings: [] },
      },
    })
    localStorage.setItem('access_token', 'stale-token')
    fetchJsonForAuthModeMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        all_repositories_role: null,
        global_permissions: ['settings.users.manage'],
      }),
    })

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(setAuthTransportModeMock).toHaveBeenCalledWith('insecure-no-auth')
      expect(setFetchAuthModeMock).toHaveBeenCalledWith('insecure-no-auth')
      expect(screen.getByText('insecure:true')).toBeInTheDocument()
      expect(fetchJsonForAuthModeMock).toHaveBeenCalledWith('/auth/me', {}, 'insecure-no-auth')
      expect(localStorage.getItem('access_token')).toBeNull()
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
    try {
      getAuthConfigMock.mockResolvedValue({
        data: {
          proxy_auth_enabled: true,
          proxy_auth_header: 'X-Forwarded-User',
          proxy_auth_health: { enabled: true, warnings: [] },
        },
      })
      getProfileMock.mockRejectedValueOnce(new Error('temporary failure')).mockResolvedValueOnce({
        data: {
          id: 1,
          username: 'proxy-user',
          email: 'proxy@example.com',
          role: 'admin',
          all_repositories_role: null,
          global_permissions: ['settings.users.manage'],
        },
      })

      renderWithProviders(
        <AuthProvider>
          <AuthProbe />
        </AuthProvider>
      )

      await vi.runAllTimersAsync()

      await waitFor(() => {
        expect(setAuthTransportModeMock).toHaveBeenCalledWith('proxy')
        expect(setFetchAuthModeMock).toHaveBeenCalledWith('proxy')
        expect(screen.getByText('proxy:true')).toBeInTheDocument()
        expect(screen.getByText('proxy-header:X-Forwarded-User')).toBeInTheDocument()
        expect(screen.getByText('proxy-warnings:none')).toBeInTheDocument()
        expect(screen.getByText('authenticated:true')).toBeInTheDocument()
        expect(screen.getByText('user:proxy-user')).toBeInTheDocument()
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('stores the token and updates auth state after login', async () => {
    const user = userEvent.setup()

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
      expect(sessionStorage.getItem('recent_password_login')).toBe('1')
      expect(screen.getByText('authenticated:true')).toBeInTheDocument()
      expect(screen.getByText('user:admin')).toBeInTheDocument()
    })
  })

  it('marks password-based TOTP completion as eligible for the passkey prompt', async () => {
    const user = userEvent.setup()
    loginApiMock.mockResolvedValueOnce({
      data: {
        totp_required: true,
        login_challenge_token: 'challenge-token',
        must_change_password: false,
      },
    })

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:false')
    await user.click(screen.getByRole('button', { name: 'Login' }))
    await user.click(screen.getByRole('button', { name: 'VerifyTotp' }))

    await waitFor(() => {
      expect(sessionStorage.getItem('recent_password_login')).toBe('1')
      expect(localStorage.getItem('access_token')).toBe('jwt-token')
    })
  })

  it('can mark a successful password confirmation as eligible for the passkey prompt', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:false')
    await user.click(screen.getByRole('button', { name: 'MarkRecentPassword' }))

    await waitFor(() => {
      expect(sessionStorage.getItem('recent_password_login')).toBe('1')
    })
  })

  it('clears the password-login prompt marker after passkey sign-in', async () => {
    const user = userEvent.setup()
    sessionStorage.setItem('recent_password_login', '1')

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:false')
    await user.click(screen.getByRole('button', { name: 'PasskeyLogin' }))

    await waitFor(() => {
      expect(sessionStorage.getItem('recent_password_login')).toBeNull()
      expect(localStorage.getItem('access_token')).toBe('jwt-token')
    })
  })

  it('returns a pending TOTP challenge without storing a token yet', async () => {
    const user = userEvent.setup()
    loginApiMock.mockResolvedValueOnce({
      data: {
        totp_required: true,
        login_challenge_token: 'challenge-token',
        must_change_password: false,
      },
    })

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await screen.findByText('authenticated:false')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBeNull()
      expect(screen.getByText('authenticated:false')).toBeInTheDocument()
    })
  })

  it('surfaces a proxy-auth error instead of retrying forever on 401', async () => {
    getAuthConfigMock.mockResolvedValue({
      data: {
        proxy_auth_enabled: true,
        proxy_auth_header: 'X-Forwarded-User',
        proxy_auth_health: {
          enabled: true,
          warnings: [{ code: 'broad_bind', message: 'Bound broadly' }],
        },
      },
    })
    getProfileMock.mockRejectedValue({
      response: {
        status: 401,
        data: {
          detail: {
            key: 'backend.errors.auth.proxyHeaderRequired',
            params: { header: 'X-Forwarded-User' },
          },
        },
      },
    })

    renderWithProviders(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('authenticated:false')).toBeInTheDocument()
      expect(screen.getByText('proxy:true')).toBeInTheDocument()
      expect(screen.getByText('proxy-warnings:broad_bind')).toBeInTheDocument()
      expect(
        screen.getByText(
          'auth-error:Reverse proxy authentication header "X-Forwarded-User" is required'
        )
      ).toBeInTheDocument()
    })
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
      expect(sessionStorage.getItem('recent_password_login')).toBeNull()
    })
  })
})
