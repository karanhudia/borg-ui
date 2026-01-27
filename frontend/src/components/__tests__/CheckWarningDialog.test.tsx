import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CheckWarningDialog from '../CheckWarningDialog'

describe('CheckWarningDialog', () => {
  const mockOnConfirm = vi.fn()
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    mockOnConfirm.mockClear()
    mockOnCancel.mockClear()
  })

  describe('Rendering', () => {
    it('renders dialog title', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('Confirm Repository Check')).toBeInTheDocument()
    })

    it('renders repository name', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="my-backup-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('my-backup-repo')).toBeInTheDocument()
    })

    it('renders warning about repository being locked', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('Repository will be locked')).toBeInTheDocument()
    })

    it('renders progress tracking info', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('Progress tracking')).toBeInTheDocument()
    })

    it('renders accessibility info about other repos', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText(/Other repositories will remain accessible/)).toBeInTheDocument()
    })

    it('renders max duration input with default value', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      const input = screen.getByRole('spinbutton')
      expect(input).toHaveValue(3600)
    })

    it('renders max duration helper text', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText(/Maximum time for the check operation/)).toBeInTheDocument()
    })

    it('renders Cancel button', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders Start Check button', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByRole('button', { name: /Start Check/ })).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      render(
        <CheckWarningDialog
          open={false}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.queryByText('Confirm Repository Check')).not.toBeInTheDocument()
    })
  })

  describe('User interactions', () => {
    it('calls onConfirm with default duration when Start Check is clicked', async () => {
      const user = userEvent.setup()
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      await user.click(screen.getByRole('button', { name: /Start Check/ }))
      expect(mockOnConfirm).toHaveBeenCalledWith(3600)
    })

    it('calls onCancel when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('calls onConfirm with custom duration', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '7200' } })
      fireEvent.click(screen.getByRole('button', { name: /Start Check/ }))

      expect(mockOnConfirm).toHaveBeenCalledWith(7200)
    })

    it('handles empty input by using default value', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '' } })

      // The component should convert NaN to 3600 (default)
      expect(input).toHaveValue(3600)
    })

    it('handles invalid input by using default value', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: 'abc' } })

      // The component should convert NaN to 3600 (default)
      expect(input).toHaveValue(3600)
    })

    it('allows zero as duration', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '0' } })

      expect(input).toHaveValue(0)
    })
  })

  describe('Loading state', () => {
    it('shows Starting... text when isLoading is true', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isLoading={true}
        />
      )
      expect(screen.getByRole('button', { name: /Starting.../ })).toBeInTheDocument()
    })

    it('disables Cancel button when isLoading is true', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isLoading={true}
        />
      )
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    })

    it('disables confirm button when isLoading is true', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isLoading={true}
        />
      )
      expect(screen.getByRole('button', { name: /Starting.../ })).toBeDisabled()
    })

    it('enables buttons when isLoading is false', () => {
      render(
        <CheckWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isLoading={false}
        />
      )
      expect(screen.getByRole('button', { name: 'Cancel' })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: /Start Check/ })).not.toBeDisabled()
    })
  })
})
