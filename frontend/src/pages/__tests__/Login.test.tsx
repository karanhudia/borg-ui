import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Login from '../Login'
import { toast } from 'react-hot-toast'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import {
  createRemoteBackendClient,
  resetRemoteBackendStateForTests,
  updateRemoteBackendHealth,
} from '../../services/remoteBackends/storage'

const {
  loginMock,
  verifyTotpLoginMock,
  loginWithOidcExchangeTokenMock,
  loginWithPasskeyMock,
  navigateMock,
  trackAuthMock,
} = vi.hoisted(() => ({
  loginMock: vi.fn(),
  verifyTotpLoginMock: vi.fn(),
  loginWithOidcExchangeTokenMock: vi.fn(),
  loginWithPasskeyMock: vi.fn(),
  navigateMock: vi.fn(),
  trackAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth.tsx', () => ({
  useAuth: () => ({
    login: loginMock,
    verifyTotpLogin: verifyTotpLoginMock,
    loginWithOidcExchangeToken: loginWithOidcExchangeTokenMock,
    loginWithPasskey: loginWithPasskeyMock,
    mustChangePassword: false,
    oidcEnabled: true,
    oidcProviderName: 'Authentik',
    oidcDisableLocalAuth: false,
  }),
}))

vi.mock('../FirstLoginPasswordSetup', () => ({
  default: () => <div>Password Setup Card</div>,
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    EventAction: {
      LOGIN: 'Login',
      START: 'Start',
      FAIL: 'Fail',
    },
  }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    resetRemoteBackendStateForTests()
  })

  function renderLogin() {
    return renderWithProviders(
      <RemoteBackendProvider>
        <Login />
      </RemoteBackendProvider>
    )
  }

  it('submits credentials, tracks login, and redirects to the dashboard by default', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({ totpRequired: false, mustChangePassword: false })

    renderLogin()

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('admin', 'secret')
      expect(trackAuthMock).toHaveBeenCalledWith('Login', {
        method: 'password',
        requires_password_setup: false,
      })
      expect(toast.success).toHaveBeenCalled()
      expect(navigateMock).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('replaces the login card with the password setup card for first-time users', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({ totpRequired: false, mustChangePassword: true })

    renderLogin()

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Login successful!')
    })
    expect(screen.getByText('Password Setup Card')).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('shows the translated backend error and resets loading after a failed login', async () => {
    const user = userEvent.setup()
    loginMock.mockRejectedValue({
      response: {
        data: {
          detail: 'backend.errors.auth.incorrectCredentials',
        },
      },
    })

    renderLogin()

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'wrong-secret')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Incorrect username or password')
    })
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled()
    expect(trackAuthMock).not.toHaveBeenCalled()
  })

  it('switches to TOTP verification when the backend requires a second factor', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue({
      totpRequired: true,
      mustChangePassword: false,
      loginChallengeToken: 'challenge-token',
    })
    verifyTotpLoginMock.mockResolvedValue({ mustChangePassword: false })

    renderLogin()

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    expect(await screen.findByLabelText(/authentication code/i)).toBeInTheDocument()

    await user.type(screen.getByLabelText(/authentication code/i), '123456')
    await user.click(screen.getByRole('button', { name: /verify code/i }))

    await waitFor(() => {
      expect(verifyTotpLoginMock).toHaveBeenCalledWith('challenge-token', '123456')
      expect(navigateMock).toHaveBeenCalledWith('/dashboard')
      expect(trackAuthMock).toHaveBeenCalledWith('Login', {
        method: 'totp',
        requires_password_setup: false,
      })
    })
  })

  it('supports passkey login from the login page', async () => {
    const user = userEvent.setup()
    loginWithPasskeyMock.mockResolvedValue({ mustChangePassword: false })

    renderLogin()

    await user.click(screen.getByRole('button', { name: /sign in with passkey/i }))

    await waitFor(() => {
      expect(trackAuthMock).toHaveBeenCalledWith('Start', { method: 'passkey', surface: 'login' })
      expect(loginWithPasskeyMock).toHaveBeenCalled()
      expect(navigateMock).toHaveBeenCalledWith('/dashboard')
      expect(trackAuthMock).toHaveBeenCalledWith('Login', {
        method: 'passkey',
        requires_password_setup: false,
      })
    })
  })

  it('completes OIDC login with one exchange when the completion effect re-enters', async () => {
    loginWithOidcExchangeTokenMock.mockResolvedValue({ mustChangePassword: false })

    renderWithProviders(
      <StrictMode>
        <RemoteBackendProvider>
          <Login />
        </RemoteBackendProvider>
      </StrictMode>,
      { initialRoute: '/login?oidc=complete' }
    )

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/dashboard')
    })
    expect(loginWithOidcExchangeTokenMock).toHaveBeenCalledTimes(1)
  })

  it('shows a server selector below credentials without a manage action', async () => {
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

    renderLogin()

    const passwordInput = screen.getByLabelText(/^password$/i)
    const serverSelect = screen.getByLabelText(/^server$/i)
    expect(
      passwordInput.compareDocumentPosition(serverSelect) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()

    await user.click(serverSelect)
    expect(await screen.findByRole('option', { name: /studio nas/i })).toBeInTheDocument()
    expect(screen.queryByText(/manage remote clients/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('option', { name: /studio nas/i }))

    expect(screen.getByLabelText(/^server$/i)).toHaveTextContent('Studio NAS')
  })
})
