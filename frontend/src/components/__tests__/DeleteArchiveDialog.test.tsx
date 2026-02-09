import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DeleteArchiveDialog from '../DeleteArchiveDialog'

describe('DeleteArchiveDialog', () => {
  const mockHandlers = {
    onClose: vi.fn(),
    onConfirm: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    const { container } = render(
      <DeleteArchiveDialog open={false} archiveName="backup-2024-01-15" {...mockHandlers} />
    )

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders dialog when open', () => {
    render(<DeleteArchiveDialog open={true} archiveName="backup-2024-01-15" {...mockHandlers} />)

    expect(screen.getByText('Delete Archive')).toBeInTheDocument()
    expect(screen.getByText(/backup-2024-01-15/)).toBeInTheDocument()
  })

  it('displays warning message', () => {
    render(<DeleteArchiveDialog open={true} archiveName="backup-2024-01-15" {...mockHandlers} />)

    expect(screen.getByText('This action cannot be undone!')).toBeInTheDocument()
    expect(screen.getByText(/The deletion will run in the background/)).toBeInTheDocument()
  })

  it('calls onClose when Cancel button is clicked', () => {
    render(<DeleteArchiveDialog open={true} archiveName="backup-2024-01-15" {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(mockHandlers.onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onConfirm with archive name when Delete button is clicked', () => {
    render(<DeleteArchiveDialog open={true} archiveName="backup-2024-01-15" {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(mockHandlers.onConfirm).toHaveBeenCalledWith('backup-2024-01-15')
  })

  it('disables Delete button when deleting', () => {
    render(
      <DeleteArchiveDialog
        open={true}
        archiveName="backup-2024-01-15"
        deleting={true}
        {...mockHandlers}
      />
    )

    const deleteButton = screen.getByRole('button', { name: /starting/i })
    expect(deleteButton).toBeDisabled()
  })

  it('shows "Starting..." text when deleting', () => {
    render(
      <DeleteArchiveDialog
        open={true}
        archiveName="backup-2024-01-15"
        deleting={true}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Starting...')).toBeInTheDocument()
  })

  it('does not call onConfirm if archiveName is null', () => {
    render(<DeleteArchiveDialog open={true} archiveName={null} {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(mockHandlers.onConfirm).not.toHaveBeenCalled()
  })
})
