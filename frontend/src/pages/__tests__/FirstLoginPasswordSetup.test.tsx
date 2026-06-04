import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import FirstLoginPasswordSetup from '../FirstLoginPasswordSetup'
import { toast } from 'react-hot-toast'

const {
  useAuthMock,
  navigateMock,
  changePasswordFromRecentLoginMock,
  skipPasswordSetupMock,
  onCompleteMock,
  trackAuthMock,
} = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  navigateMock: vi.fn(),
  changePasswordFromRecentLoginMock: vi.fn(),
  skipPasswordSetupMock: vi.fn(),
  onCompleteMock: vi.fn(),
  trackAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    EventAction: {
      VIEW: 'View',
      COMPLETE: 'Complete',
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

describe('FirstLoginPasswordSetup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    useAuthMock.mockReturnValue({
      user: { username: 'admin' },
      mustChangePassword: true,
      canChangePasswordFromRecentLogin: true,
      changePasswordFromRecentLogin: changePasswordFromRecentLoginMock,
      skipPasswordSetup: skipPasswordSetupMock,
    })
    changePasswordFromRecentLoginMock.mockResolvedValue(undefined)
    skipPasswordSetupMock.mockResolvedValue(undefined)
  })

  it('changes the password and continues to the dashboard', async () => {
    const user = userEvent.setup()

    renderWithProviders(<FirstLoginPasswordSetup onComplete={onCompleteMock} />)

    expect(trackAuthMock).toHaveBeenCalledWith('View', { surface: 'first_login_password_setup' })

    await user.type(screen.getByLabelText(/^new password$/i), 'new-password-123')
    await user.type(screen.getByLabelText(/^confirm new password$/i), 'new-password-123')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await waitFor(() => {
      expect(changePasswordFromRecentLoginMock).toHaveBeenCalledWith('new-password-123')
      expect(trackAuthMock).toHaveBeenCalledWith('Complete', {
        surface: 'first_login_password_setup',
        operation: 'change_password',
      })
      expect(toast.success).toHaveBeenCalledWith('Password changed successfully')
      expect(onCompleteMock).toHaveBeenCalled()
    })
  })

  it('allows skipping the password change and continues to the dashboard', async () => {
    const user = userEvent.setup()

    renderWithProviders(<FirstLoginPasswordSetup onComplete={onCompleteMock} />)
    await user.click(screen.getByRole('button', { name: /skip for now/i }))

    expect(changePasswordFromRecentLoginMock).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(skipPasswordSetupMock).toHaveBeenCalled()
      expect(trackAuthMock).toHaveBeenCalledWith('Skip', {
        surface: 'first_login_password_setup',
        operation: 'change_password',
      })
      expect(onCompleteMock).toHaveBeenCalled()
    })
  })

  it('blocks submission when the passwords do not match', async () => {
    const user = userEvent.setup()

    renderWithProviders(<FirstLoginPasswordSetup onComplete={onCompleteMock} />)

    await user.type(screen.getByLabelText(/^new password$/i), 'new-password-123')
    await user.type(screen.getByLabelText(/^confirm new password$/i), 'different-password')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    expect(changePasswordFromRecentLoginMock).not.toHaveBeenCalled()
    expect(trackAuthMock).toHaveBeenCalledWith('Fail', {
      surface: 'first_login_password_setup',
      operation: 'change_password_validation',
      reason: 'password_mismatch',
    })
    expect(toast.error).toHaveBeenCalledWith('New passwords do not match')
  })
})
