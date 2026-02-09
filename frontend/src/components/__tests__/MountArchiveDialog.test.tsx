import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import MountArchiveDialog from '../MountArchiveDialog'

describe('MountArchiveDialog', () => {
  const mockArchive = {
    id: '1',
    name: 'backup-2024-01-15',
    archive: 'backup-2024-01-15',
    start: '2024-01-15T10:00:00Z',
    time: '2024-01-15T10:00:00Z',
  }

  const mockHandlers = {
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    onMountPointChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    const { container } = render(
      <MountArchiveDialog open={false} archive={mockArchive} mountPoint="" {...mockHandlers} />
    )

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders dialog when open', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    expect(screen.getByText('Mount Archive')).toBeInTheDocument()
    expect(screen.getByText('backup-2024-01-15')).toBeInTheDocument()
  })

  it('displays info alert about read-only filesystem', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    expect(
      screen.getByText(/The archive will be mounted as a read-only filesystem/)
    ).toBeInTheDocument()
  })

  it('renders mount point input with placeholder', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    const input = screen.getByLabelText('Mount Name')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('placeholder', 'my-backup-2024')
  })

  it('displays current mount point value', () => {
    render(
      <MountArchiveDialog
        open={true}
        archive={mockArchive}
        mountPoint="my-mount"
        {...mockHandlers}
      />
    )

    const input = screen.getByLabelText('Mount Name') as HTMLInputElement
    expect(input.value).toBe('my-mount')
  })

  it('calls onMountPointChange when input changes', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    const input = screen.getByLabelText('Mount Name')
    fireEvent.change(input, { target: { value: 'new-mount' } })

    expect(mockHandlers.onMountPointChange).toHaveBeenCalledWith('new-mount')
  })

  it('displays helper text with mount path preview', () => {
    render(
      <MountArchiveDialog
        open={true}
        archive={mockArchive}
        mountPoint="my-mount"
        {...mockHandlers}
      />
    )

    expect(screen.getByText(/Will be mounted at: \/data\/mounts\/my-mount/)).toBeInTheDocument()
  })

  it('shows placeholder in helper text when mount point is empty', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    expect(screen.getByText(/Will be mounted at: \/data\/mounts\/<name>/)).toBeInTheDocument()
  })

  it('calls onClose when Cancel button is clicked', () => {
    render(<MountArchiveDialog open={true} archive={mockArchive} mountPoint="" {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(mockHandlers.onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onConfirm when Mount button is clicked', () => {
    render(
      <MountArchiveDialog
        open={true}
        archive={mockArchive}
        mountPoint="my-mount"
        {...mockHandlers}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /^mount$/i }))
    expect(mockHandlers.onConfirm).toHaveBeenCalledTimes(1)
  })

  it('disables Mount button when mounting', () => {
    render(
      <MountArchiveDialog
        open={true}
        archive={mockArchive}
        mountPoint="my-mount"
        mounting={true}
        {...mockHandlers}
      />
    )

    const mountButton = screen.getByRole('button', { name: /mounting/i })
    expect(mountButton).toBeDisabled()
  })

  it('shows "Mounting..." text when mounting', () => {
    render(
      <MountArchiveDialog
        open={true}
        archive={mockArchive}
        mountPoint="my-mount"
        mounting={true}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Mounting...')).toBeInTheDocument()
  })

  it('handles null archive gracefully', () => {
    render(<MountArchiveDialog open={true} archive={null} mountPoint="" {...mockHandlers} />)

    expect(screen.getByText('Mount Archive')).toBeInTheDocument()
  })
})
