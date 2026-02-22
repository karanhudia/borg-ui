import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LockErrorDialog from '../LockErrorDialog'
import { repositoriesAPI } from '../../services/api'
import { toast } from 'react-hot-toast'
import { AxiosResponse } from 'axios'

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    breakLock: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('LockErrorDialog', () => {
  const mockOnClose = vi.fn()
  const mockOnLockBroken = vi.fn()
  const mockConfirm = vi.fn()
  const defaultProps = {
    open: true,
    onClose: mockOnClose,
    repositoryId: 1,
    repositoryName: 'test-repo',
    onLockBroken: mockOnLockBroken,
    isAdmin: true, // Default to admin for existing tests
  }

  beforeEach(() => {
    mockOnClose.mockClear()
    mockOnLockBroken.mockClear()
    mockConfirm.mockClear()
    vi.mocked(repositoriesAPI.breakLock).mockClear()
    vi.mocked(toast.success).mockClear()
    vi.mocked(toast.error).mockClear()
    // Mock window.confirm using stubGlobal
    vi.stubGlobal('confirm', mockConfirm)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('Rendering', () => {
    it('renders dialog title', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(screen.getByText('Repository Locked')).toBeInTheDocument()
    })

    it('renders repository name in subtitle', () => {
      render(<LockErrorDialog {...defaultProps} repositoryName="my-backup" />)
      expect(screen.getByText('my-backup')).toBeInTheDocument()
    })

    it('renders warning alert', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(
        screen.getByText(/If no backup is currently running, this is likely a stale lock/)
      ).toBeInTheDocument()
    })

    it('renders causes list', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(screen.getByText('What causes this?')).toBeInTheDocument()
      expect(screen.getByText(/Previous backup was interrupted or crashed/)).toBeInTheDocument()
      expect(screen.getByText(/Network connection dropped during SSH backup/)).toBeInTheDocument()
      expect(screen.getByText(/Container was restarted during an operation/)).toBeInTheDocument()
      expect(screen.getByText(/Repository cache locks from stale operations/)).toBeInTheDocument()
    })

    it('renders precautions list', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(screen.getByText('Before breaking the lock:')).toBeInTheDocument()
      expect(
        screen.getByText(/Make sure no backup process is currently running/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Check that no other client is accessing this repository/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/This will break both repository and cache locks/)
      ).toBeInTheDocument()
    })

    it('renders Cancel button', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders Break Lock button', () => {
      render(<LockErrorDialog {...defaultProps} />)
      expect(screen.getByRole('button', { name: /Break Lock/ })).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      render(<LockErrorDialog {...defaultProps} open={false} />)
      expect(screen.queryByText('Repository Locked')).not.toBeInTheDocument()
    })
  })

  describe('User interactions', () => {
    it('calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })

    it('shows confirmation dialog when Break Lock is clicked', async () => {
      mockConfirm.mockReturnValue(false)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))
      expect(mockConfirm).toHaveBeenCalledWith(
        expect.stringContaining('Are you CERTAIN no backup or operation is currently running')
      )
    })

    it('does not call API when confirmation is cancelled', async () => {
      mockConfirm.mockReturnValue(false)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))
      expect(repositoriesAPI.breakLock).not.toHaveBeenCalled()
    })

    it('calls API when confirmation is accepted', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockResolvedValue({} as AxiosResponse)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(repositoriesAPI.breakLock).toHaveBeenCalledWith(1)
      })
    })

    it('shows success toast on successful lock break', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockResolvedValue({} as AxiosResponse)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Lock removed successfully! You can now retry your operation.'
        )
      })
    })

    it('calls onLockBroken callback on success', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockResolvedValue({} as AxiosResponse)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(mockOnLockBroken).toHaveBeenCalledTimes(1)
      })
    })

    it('calls onClose after successful lock break', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockResolvedValue({} as AxiosResponse)
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalledTimes(1)
      })
    })

    it('shows error toast on API failure', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockRejectedValue({
        response: { data: { detail: 'Lock operation failed' } },
      })
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Lock operation failed')
      })
    })

    it('shows generic error toast when no detail in response', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockRejectedValue({})
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to break lock')
      })
    })
  })

  describe('Loading state', () => {
    it('shows Breaking Lock... text while processing', async () => {
      mockConfirm.mockReturnValue(true)
      // Make the API call hang
      vi.mocked(repositoriesAPI.breakLock).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Breaking Lock.../ })).toBeInTheDocument()
      })
    })

    it('disables Cancel button while breaking', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
      })
    })

    it('disables Break Lock button while breaking', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()
      render(<LockErrorDialog {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Breaking Lock.../ })).toBeDisabled()
      })
    })
  })

  describe('Optional onLockBroken callback', () => {
    it('works without onLockBroken callback', async () => {
      mockConfirm.mockReturnValue(true)
      vi.mocked(repositoriesAPI.breakLock).mockResolvedValue({} as AxiosResponse)
      const user = userEvent.setup()
      render(
        <LockErrorDialog
          open={true}
          onClose={mockOnClose}
          repositoryId={1}
          repositoryName="test-repo"
          isAdmin={true}
          // No onLockBroken callback
        />
      )

      await user.click(screen.getByRole('button', { name: /Break Lock/ }))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalled()
        expect(mockOnClose).toHaveBeenCalled()
      })
    })
  })

  describe('Admin restrictions', () => {
    it('enables Break Lock button for admin users', () => {
      render(<LockErrorDialog {...defaultProps} isAdmin={true} />)
      const breakLockButton = screen.getByRole('button', { name: /Break Lock/ })
      expect(breakLockButton).not.toBeDisabled()
    })

    it('disables Break Lock button for non-admin users', () => {
      render(<LockErrorDialog {...defaultProps} isAdmin={false} />)
      const breakLockButton = screen.getByRole('button', { name: /Break Lock/ })
      expect(breakLockButton).toBeDisabled()
    })

    it('disables Break Lock button when isAdmin is undefined (defaults to false)', () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { isAdmin, ...propsWithoutAdmin } = defaultProps
      render(<LockErrorDialog {...propsWithoutAdmin} />)
      const breakLockButton = screen.getByRole('button', { name: /Break Lock/ })
      expect(breakLockButton).toBeDisabled()
    })

    it('shows admin warning alert for non-admin users', () => {
      render(<LockErrorDialog {...defaultProps} isAdmin={false} />)
      expect(screen.getByText(/Admin privileges required/)).toBeInTheDocument()
      expect(screen.getByText(/Only administrators can break repository locks/)).toBeInTheDocument()
    })

    it('does not show admin warning alert for admin users', () => {
      render(<LockErrorDialog {...defaultProps} isAdmin={true} />)
      expect(screen.queryByText(/Admin privileges required/)).not.toBeInTheDocument()
    })

    it('does not call API when non-admin clicks disabled Break Lock button', async () => {
      mockConfirm.mockReturnValue(true)
      render(<LockErrorDialog {...defaultProps} isAdmin={false} />)

      const breakLockButton = screen.getByRole('button', { name: /Break Lock/ })
      expect(breakLockButton).toBeDisabled()

      // Button is disabled, so clicking should not trigger API
      expect(repositoriesAPI.breakLock).not.toHaveBeenCalled()
    })
  })
})
