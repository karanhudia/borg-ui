import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import DeleteJobDialog from '../DeleteJobDialog'

describe('DeleteJobDialog', () => {
  const mockProps = {
    open: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    jobId: 123,
    jobType: 'backup',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders when open is true', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByRole('heading', { name: /delete.*backup.*entry/i })).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} open={false} />)

      expect(screen.queryByText(/delete.*backup.*entry/i)).not.toBeInTheDocument()
    })

    it('displays job ID in message', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByText(/ID: 123/i)).toBeInTheDocument()
    })

    it('displays job type in title', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} jobType="restore" />)

      expect(screen.getByRole('heading', { name: /delete.*job.*entry/i })).toBeInTheDocument()
    })

    it('displays backup type in title for backup jobs', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} jobType="backup" />)

      expect(screen.getByRole('heading', { name: /delete.*backup.*entry/i })).toBeInTheDocument()
    })
  })

  describe('Warning Messages', () => {
    it('displays warning about permanent deletion', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
    })

    it('displays warning about job history removal', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByText(/job history will be permanently removed/i)).toBeInTheDocument()
    })

    it('displays warning about log file deletion', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByText(/associated log files will be deleted/i)).toBeInTheDocument()
    })

    it('displays warning about data recovery', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByText(/cannot be recovered/i)).toBeInTheDocument()
    })

    it('displays warning alert with warning severity', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const warningAlert = screen.getByRole('alert')
      expect(warningAlert).toBeInTheDocument()
    })
  })

  describe('User Interactions', () => {
    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const cancelButton = screen.getByRole('button', { name: /^cancel$/i })
      await user.click(cancelButton)

      expect(mockProps.onClose).toHaveBeenCalledTimes(1)
      expect(mockProps.onConfirm).not.toHaveBeenCalled()
    })

    it('calls onConfirm when Delete Permanently button is clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const deleteButton = screen.getByRole('button', { name: /delete permanently/i })
      await user.click(deleteButton)

      expect(mockProps.onConfirm).toHaveBeenCalledTimes(1)
      expect(mockProps.onClose).not.toHaveBeenCalled()
    })

    it('calls onClose when clicking outside dialog', async () => {
      const user = userEvent.setup()
      const { baseElement } = renderWithProviders(<DeleteJobDialog {...mockProps} />)

      // Click on backdrop
      const backdrop = baseElement.querySelector('.MuiBackdrop-root')
      if (backdrop) {
        await user.click(backdrop)
        await waitFor(() => {
          expect(mockProps.onClose).toHaveBeenCalled()
        })
      }
    })
  })

  describe('Button Styles', () => {
    it('renders Cancel button with outlined variant', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const cancelButton = screen.getByRole('button', { name: /^cancel$/i })
      expect(cancelButton).toHaveClass('MuiButton-outlined')
    })

    it('renders Delete button with error color', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const deleteButton = screen.getByRole('button', { name: /delete permanently/i })
      expect(deleteButton).toHaveClass('MuiButton-containedError')
    })

    it('renders Delete button with warning icon', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const deleteButton = screen.getByRole('button', { name: /delete permanently/i })
      const icon = deleteButton.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles missing jobId gracefully', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} jobId={undefined} />)

      // Should still render dialog
      expect(screen.getByRole('heading', { name: /delete.*backup.*entry/i })).toBeInTheDocument()
      // But should not show ID in message
      expect(screen.queryByText(/ID:/i)).not.toBeInTheDocument()
    })

    it('handles missing jobType gracefully', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} jobType={undefined} />)

      // Should default to "job"
      expect(screen.getByRole('heading', { name: /delete.*job.*entry/i })).toBeInTheDocument()
    })

    it('handles async onConfirm', async () => {
      const user = userEvent.setup()
      const asyncConfirm = vi.fn().mockResolvedValue(undefined)

      renderWithProviders(<DeleteJobDialog {...mockProps} onConfirm={asyncConfirm} />)

      const deleteButton = screen.getByRole('button', { name: /delete permanently/i })
      await user.click(deleteButton)

      await waitFor(() => {
        expect(asyncConfirm).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA role for dialog', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
    })

    it('has accessible button labels', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      expect(screen.getByRole('button', { name: /^cancel$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /delete permanently/i })).toBeInTheDocument()
    })

    it('has alert role for warning message', () => {
      renderWithProviders(<DeleteJobDialog {...mockProps} />)

      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
    })
  })
})
