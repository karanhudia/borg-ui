import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import PasskeyEnrollmentPrompt from '../PasskeyEnrollmentPrompt'
import { toast } from 'react-hot-toast'

const {
  enrollPasskeyFromRecentLoginMock,
  onSnoozeMock,
  onIgnoreMock,
  onSuccessMock,
  trackAuthMock,
} = vi.hoisted(() => ({
  enrollPasskeyFromRecentLoginMock: vi.fn(),
  onSnoozeMock: vi.fn(),
  onIgnoreMock: vi.fn(),
  onSuccessMock: vi.fn(),
  trackAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    enrollPasskeyFromRecentLogin: enrollPasskeyFromRecentLoginMock,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    EventAction: {
      VIEW: 'View',
      START: 'Start',
      COMPLETE: 'Complete',
      FAIL: 'Fail',
    },
  }),
}))

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

describe('PasskeyEnrollmentPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    enrollPasskeyFromRecentLoginMock.mockResolvedValue(undefined)
    onSuccessMock.mockResolvedValue(undefined)
  })

  it('tracks a prompt view and successful enrollment', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PasskeyEnrollmentPrompt
        open
        onSnooze={onSnoozeMock}
        onIgnore={onIgnoreMock}
        onSuccess={onSuccessMock}
      />
    )

    expect(trackAuthMock).toHaveBeenCalledWith('View', { surface: 'post_login_passkey_prompt' })

    await user.click(screen.getByRole('button', { name: /set up passkey/i }))

    await waitFor(() => {
      expect(trackAuthMock).toHaveBeenCalledWith('Start', {
        surface: 'post_login_passkey_prompt',
        operation: 'enroll_passkey',
      })
      expect(enrollPasskeyFromRecentLoginMock).toHaveBeenCalledTimes(1)
      expect(trackAuthMock).toHaveBeenCalledWith('Complete', {
        surface: 'post_login_passkey_prompt',
        operation: 'enroll_passkey',
      })
      expect(toast.success).toHaveBeenCalledWith('Passkey added')
      expect(onSuccessMock).toHaveBeenCalledTimes(1)
    })
  })

  it('tracks snooze and ignore actions', async () => {
    const user = userEvent.setup()

    const { rerender } = renderWithProviders(
      <PasskeyEnrollmentPrompt
        open
        onSnooze={onSnoozeMock}
        onIgnore={onIgnoreMock}
        onSuccess={onSuccessMock}
      />
    )

    await user.click(screen.getByRole('button', { name: /remind me later/i }))
    expect(trackAuthMock).toHaveBeenCalledWith('Snooze', { surface: 'post_login_passkey_prompt' })
    expect(onSnoozeMock).toHaveBeenCalledTimes(1)

    rerender(
      <PasskeyEnrollmentPrompt
        open
        onSnooze={onSnoozeMock}
        onIgnore={onIgnoreMock}
        onSuccess={onSuccessMock}
      />
    )

    await user.click(screen.getByRole('button', { name: /don't ask again/i }))
    expect(trackAuthMock).toHaveBeenCalledWith('Ignore', { surface: 'post_login_passkey_prompt' })
    expect(onIgnoreMock).toHaveBeenCalledTimes(1)
  })

  it('handles enrollment rejection without an unhandled rejection and allows retry', async () => {
    enrollPasskeyFromRecentLoginMock.mockRejectedValueOnce({
      response: { data: { detail: 'Passkey enrollment was cancelled.' } },
    })
    const unhandledRejection = vi.fn()
    window.addEventListener('unhandledrejection', unhandledRejection)
    const user = userEvent.setup()

    try {
      renderWithProviders(
        <PasskeyEnrollmentPrompt
          open
          onSnooze={onSnoozeMock}
          onIgnore={onIgnoreMock}
          onSuccess={onSuccessMock}
        />
      )

      await user.click(screen.getByRole('button', { name: /set up passkey/i }))

      await waitFor(() => {
        expect(trackAuthMock).toHaveBeenCalledWith('Fail', {
          surface: 'post_login_passkey_prompt',
          operation: 'enroll_passkey',
        })
        expect(toast.error).toHaveBeenCalledWith('Passkey enrollment was cancelled.')
        expect(screen.getByRole('button', { name: /set up passkey/i })).toBeEnabled()
      })
      expect(onSuccessMock).not.toHaveBeenCalled()
      expect(toast.success).not.toHaveBeenCalled()
      expect(onSnoozeMock).not.toHaveBeenCalled()
      expect(onIgnoreMock).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: /set up passkey/i }))

      await waitFor(() => {
        expect(enrollPasskeyFromRecentLoginMock).toHaveBeenCalledTimes(2)
        expect(onSuccessMock).toHaveBeenCalledTimes(1)
      })
      expect(unhandledRejection).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('unhandledrejection', unhandledRejection)
    }
  })
})
