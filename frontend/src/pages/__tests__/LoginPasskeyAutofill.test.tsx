import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Navigate, Route, Routes } from 'react-router-dom'
import { renderWithProviders, screen, waitFor } from '../../test/test-utils'
import Login from '../Login'
import { AuthProvider, useAuth } from '../../hooks/useAuth'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import { resetRemoteBackendStateForTests } from '../../services/remoteBackends/storage'

const {
  getAuthConfigMock,
  getProfileMock,
  beginPasskeyAuthenticationMock,
  finishPasskeyAuthenticationMock,
  getConditionalPasskeyAssertionMock,
  trackAuthMock,
} = vi.hoisted(() => ({
  getAuthConfigMock: vi.fn(),
  getProfileMock: vi.fn(),
  beginPasskeyAuthenticationMock: vi.fn(),
  finishPasskeyAuthenticationMock: vi.fn(),
  getConditionalPasskeyAssertionMock: vi.fn(),
  trackAuthMock: vi.fn(),
}))

vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../services/api')>('../../services/api')
  return {
    ...actual,
    authAPI: {
      ...actual.authAPI,
      getAuthConfig: () => getAuthConfigMock(),
      getProfile: () => getProfileMock(),
      beginPasskeyAuthentication: () => beginPasskeyAuthenticationMock(),
      finishPasskeyAuthentication: (ceremonyToken: string, credential: unknown) =>
        finishPasskeyAuthenticationMock(ceremonyToken, credential),
    },
  }
})

vi.mock('../../utils/webauthn', () => ({
  isConditionalMediationAvailable: () => Promise.resolve(true),
  getConditionalPasskeyAssertion: () => getConditionalPasskeyAssertionMock(),
  getPasskeyAssertion: vi.fn(),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    EventAction: { LOGIN: 'Login', START: 'Start', FAIL: 'Fail' },
  }),
}))

// Same split as App: unauthenticated users only get /login, everything else redirects there;
// the authenticated tree has no /login or catch-all route, so Login must navigate itself.
function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth()
  if (isLoading) return null
  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<div>Dashboard page</div>} />
    </Routes>
  )
}

describe('Login page passkey autofill', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    resetRemoteBackendStateForTests()
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
        global_permissions: [],
        must_change_password: false,
      },
    })
    beginPasskeyAuthenticationMock.mockResolvedValue({
      data: { options: { challenge: 'challenge' }, ceremony_token: 'ceremony-token' },
    })
    getConditionalPasskeyAssertionMock.mockResolvedValue({ id: 'credential-id' })
    finishPasskeyAuthenticationMock.mockResolvedValue({
      data: { access_token: 'passkey-token', must_change_password: false },
    })
  })

  it('loads the profile and lands on the dashboard after an autofill passkey sign-in', async () => {
    renderWithProviders(
      <RemoteBackendProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </RemoteBackendProvider>,
      { initialRoute: '/login' }
    )

    await waitFor(() =>
      expect(finishPasskeyAuthenticationMock).toHaveBeenCalledWith('ceremony-token', {
        id: 'credential-id',
      })
    )
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
    expect(getProfileMock).toHaveBeenCalledTimes(1)
    expect(window.location.pathname).toBe('/dashboard')
  })
})
