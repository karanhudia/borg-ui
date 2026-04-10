import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Login from '../Login'
import { toast } from 'react-hot-toast'

const { loginMock, navigateMock, trackAuthMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  navigateMock: vi.fn(),
  trackAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth.tsx', () => ({
  useAuth: () => ({
    login: loginMock,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    EventAction: {
      LOGIN: 'Login',
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
  })

  it('submits credentials, tracks login, and redirects to the dashboard by default', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue(false)

    renderWithProviders(<Login />)

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('admin', 'secret')
      expect(trackAuthMock).toHaveBeenCalledWith('Login')
      expect(toast.success).toHaveBeenCalled()
      expect(navigateMock).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('redirects to account settings when the backend requires a password change', async () => {
    const user = userEvent.setup()
    loginMock.mockResolvedValue(true)

    renderWithProviders(<Login />)

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/settings/account')
    })
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

    renderWithProviders(<Login />)

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/^password$/i), 'wrong-secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Incorrect username or password')
    })
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
    expect(trackAuthMock).not.toHaveBeenCalled()
  })
})
