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
} = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  navigateMock: vi.fn(),
  changePasswordFromRecentLoginMock: vi.fn(),
  skipPasswordSetupMock: vi.fn(),
  onCompleteMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
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

    await user.type(screen.getByLabelText(/^new password$/i), 'new-password-123')
    await user.type(screen.getByLabelText(/^confirm new password$/i), 'new-password-123')
    await user.click(screen.getByRole('button', { name: /^next$/i }))

    await waitFor(() => {
      expect(changePasswordFromRecentLoginMock).toHaveBeenCalledWith('new-password-123')
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
    expect(toast.error).toHaveBeenCalledWith('New passwords do not match')
  })
})
