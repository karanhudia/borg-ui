import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CompactWarningDialog from '../CompactWarningDialog'

describe('CompactWarningDialog', () => {
  const mockOnConfirm = vi.fn()
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    mockOnConfirm.mockClear()
    mockOnCancel.mockClear()
  })

  describe('Rendering', () => {
    it('renders dialog title', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('Confirm Repository Compaction')).toBeInTheDocument()
    })

    it('renders repository name', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="my-backup-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('my-backup-repo')).toBeInTheDocument()
    })

    it('renders description text', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(
        screen.getByText(/Compaction removes unused segments and reclaims disk space/)
      ).toBeInTheDocument()
    })

    it('renders warning about repository being locked', () => {
      render(
        <CompactWarningDialog
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
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText('Progress tracking')).toBeInTheDocument()
    })

    it('renders tip text', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByText(/Tip: Run compaction after pruning/)).toBeInTheDocument()
    })

    it('renders Cancel button', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders Start Compacting button', () => {
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.getByRole('button', { name: /Start Compacting/ })).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      render(
        <CompactWarningDialog
          open={false}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )
      expect(screen.queryByText('Confirm Repository Compaction')).not.toBeInTheDocument()
    })
  })

  describe('User interactions', () => {
    it('calls onConfirm when Start Compacting is clicked', async () => {
      const user = userEvent.setup()
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      await user.click(screen.getByRole('button', { name: /Start Compacting/ }))
      expect(mockOnConfirm).toHaveBeenCalledTimes(1)
    })

    it('calls onCancel when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })
  })

  describe('Loading state', () => {
    it('shows Starting... text when isLoading is true', () => {
      render(
        <CompactWarningDialog
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
        <CompactWarningDialog
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
        <CompactWarningDialog
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
        <CompactWarningDialog
          open={true}
          repositoryName="test-repo"
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isLoading={false}
        />
      )
      expect(screen.getByRole('button', { name: 'Cancel' })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: /Start Compacting/ })).not.toBeDisabled()
    })
  })
})
