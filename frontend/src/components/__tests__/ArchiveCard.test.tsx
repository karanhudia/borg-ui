import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ArchiveCard from '../ArchiveCard'

describe('ArchiveCard', () => {
  const mockArchive = {
    id: '1',
    name: 'backup-2024-01-15',
    archive: 'backup-2024-01-15',
    start: '2024-01-15T10:30:00Z',
    time: '2024-01-15T10:30:00Z',
  }

  const mockHandlers = {
    onView: vi.fn(),
    onRestore: vi.fn(),
    onMount: vi.fn(),
    onDelete: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders archive name and date', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    expect(screen.getByText('backup-2024-01-15')).toBeInTheDocument()
    // Date formatting is locale-dependent, just check it's rendered
    expect(screen.getAllByText(/2024/)).toHaveLength(2) // Archive name + formatted date
  })

  it('renders all action buttons', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    expect(screen.getByRole('button', { name: /view/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /mount/i })).toBeInTheDocument()
    // Delete button is an IconButton without text
    const deleteButton = screen.getByRole('button', { name: '' })
    expect(deleteButton).toBeInTheDocument()
  })

  it('calls onView when View button is clicked', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /view/i }))

    expect(mockHandlers.onView).toHaveBeenCalledWith(mockArchive)
    expect(mockHandlers.onView).toHaveBeenCalledTimes(1)
  })

  it('calls onRestore when Restore button is clicked', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /restore/i }))

    expect(mockHandlers.onRestore).toHaveBeenCalledWith(mockArchive)
    expect(mockHandlers.onRestore).toHaveBeenCalledTimes(1)
  })

  it('calls onMount when Mount button is clicked', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    fireEvent.click(screen.getByRole('button', { name: /mount/i }))

    expect(mockHandlers.onMount).toHaveBeenCalledWith(mockArchive)
    expect(mockHandlers.onMount).toHaveBeenCalledTimes(1)
  })

  it('calls onDelete with archive name when delete button is clicked', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    // Find the delete icon button (IconButton with Trash2 icon)
    const buttons = screen.getAllByRole('button')
    const deleteButton = buttons[buttons.length - 1] // Last button is delete

    fireEvent.click(deleteButton)

    expect(mockHandlers.onDelete).toHaveBeenCalledWith('backup-2024-01-15')
    expect(mockHandlers.onDelete).toHaveBeenCalledTimes(1)
  })

  it('disables Mount button when mountDisabled is true', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} mountDisabled={true} />)

    const mountButton = screen.getByRole('button', { name: /mount/i })
    expect(mountButton).toBeDisabled()
  })

  it('enables Mount button when mountDisabled is false', () => {
    render(<ArchiveCard archive={mockArchive} {...mockHandlers} mountDisabled={false} />)

    const mountButton = screen.getByRole('button', { name: /mount/i })
    expect(mountButton).not.toBeDisabled()
  })

  it('has hover effect styling', () => {
    const { container } = render(<ArchiveCard archive={mockArchive} {...mockHandlers} />)

    const card = container.querySelector('.MuiCard-root')
    expect(card).toHaveStyle({ transition: 'all 0.2s' })
  })
})
