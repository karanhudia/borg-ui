import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SourceDirectoriesInput from '../SourceDirectoriesInput'

describe('SourceDirectoriesInput', () => {
  const mockOnChange = vi.fn()
  const mockOnBrowseClick = vi.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
    mockOnBrowseClick.mockClear()
  })

  describe('Rendering', () => {
    it('renders title and description', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)
      expect(screen.getByText('Source Directories & Files')).toBeInTheDocument()
      expect(screen.getByText(/Specify which directories or files to backup/)).toBeInTheDocument()
    })

    it('renders required asterisk when required=true', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} required={true} />)
      expect(screen.getByText('*')).toBeInTheDocument()
      expect(screen.getByText(/at least one required/)).toBeInTheDocument()
    })

    it('does not render required asterisk when required=false', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} required={false} />)
      expect(screen.queryByText('*')).not.toBeInTheDocument()
      expect(screen.getByText(/optional/)).toBeInTheDocument()
    })

    it('shows warning alert when required and no directories', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} required={true} />)
      expect(
        screen.getByText(/At least one source directory or file is required/)
      ).toBeInTheDocument()
    })

    it('does not show warning alert when required=false and no directories', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} required={false} />)
      expect(
        screen.queryByText(/At least one source directory or file is required/)
      ).not.toBeInTheDocument()
    })

    it('does not show warning alert when directories exist', () => {
      render(
        <SourceDirectoriesInput
          directories={['/home/user/docs']}
          onChange={mockOnChange}
          required={true}
        />
      )
      expect(
        screen.queryByText(/At least one source directory is required/)
      ).not.toBeInTheDocument()
    })

    it('renders existing directories', () => {
      const dirs = ['/home/user/docs', '/var/data']
      render(<SourceDirectoriesInput directories={dirs} onChange={mockOnChange} />)
      expect(screen.getByText('/home/user/docs')).toBeInTheDocument()
      expect(screen.getByText('/var/data')).toBeInTheDocument()
    })

    it('renders input field with placeholder', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)
      expect(
        screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      ).toBeInTheDocument()
    })

    it('renders Add button', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)
      expect(screen.getByRole('button', { name: /Add/i })).toBeInTheDocument()
    })

    it('renders browse button when onBrowseClick provided', () => {
      render(
        <SourceDirectoriesInput
          directories={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
        />
      )
      expect(screen.getByTitle('Browse directories and files')).toBeInTheDocument()
    })

    it('does not render browse button when onBrowseClick not provided', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)
      expect(screen.queryByTitle('Browse directories and files')).not.toBeInTheDocument()
    })
  })

  describe('Adding directories', () => {
    it('adds directory when clicking Add button', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '/new/directory')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['/new/directory'])
    })

    it('adds directory when pressing Enter', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '/new/directory{enter}')

      expect(mockOnChange).toHaveBeenCalledWith(['/new/directory'])
    })

    it('appends to existing directories', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={['/existing/dir']} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '/new/directory')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['/existing/dir', '/new/directory'])
    })

    it('trims whitespace from input', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '  /new/directory  ')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['/new/directory'])
    })

    it('clears input after adding', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '/new/directory')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(input).toHaveValue('')
    })

    it('does not add empty directory', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('does not add whitespace-only directory', async () => {
      const user = userEvent.setup()
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')
      await user.type(input, '   ')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Removing directories', () => {
    it('removes directory when clicking delete button', async () => {
      const user = userEvent.setup()
      render(
        <SourceDirectoriesInput
          directories={['/first/dir', '/second/dir', '/third/dir']}
          onChange={mockOnChange}
        />
      )

      // Get all delete buttons (there should be 3)
      const deleteButtons = screen.getAllByRole('button', { name: '' })
      // Filter to only get the delete icon buttons (they have DeleteIcon)
      const deleteIconButtons = deleteButtons.filter((btn) =>
        btn.querySelector('svg[data-testid="DeleteIcon"]')
      )

      // Click the second delete button (index 1)
      await user.click(deleteIconButtons[1])

      expect(mockOnChange).toHaveBeenCalledWith(['/first/dir', '/third/dir'])
    })

    it('removes first directory correctly', async () => {
      const user = userEvent.setup()
      render(
        <SourceDirectoriesInput
          directories={['/first/dir', '/second/dir']}
          onChange={mockOnChange}
        />
      )

      const deleteButtons = screen.getAllByRole('button', { name: '' })
      const deleteIconButtons = deleteButtons.filter((btn) =>
        btn.querySelector('svg[data-testid="DeleteIcon"]')
      )

      await user.click(deleteIconButtons[0])

      expect(mockOnChange).toHaveBeenCalledWith(['/second/dir'])
    })

    it('removes last directory correctly', async () => {
      const user = userEvent.setup()
      render(
        <SourceDirectoriesInput
          directories={['/first/dir', '/second/dir']}
          onChange={mockOnChange}
        />
      )

      const deleteButtons = screen.getAllByRole('button', { name: '' })
      const deleteIconButtons = deleteButtons.filter((btn) =>
        btn.querySelector('svg[data-testid="DeleteIcon"]')
      )

      await user.click(deleteIconButtons[1])

      expect(mockOnChange).toHaveBeenCalledWith(['/first/dir'])
    })
  })

  describe('Browse functionality', () => {
    it('calls onBrowseClick when browse button clicked', async () => {
      const user = userEvent.setup()
      render(
        <SourceDirectoriesInput
          directories={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
        />
      )

      await user.click(screen.getByTitle('Browse directories and files'))

      expect(mockOnBrowseClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('Disabled state', () => {
    it('disables input when disabled=true', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} disabled={true} />)
      expect(screen.getByPlaceholderText('/home/user/documents or /var/log/app.log')).toBeDisabled()
    })

    it('disables Add button when disabled=true', () => {
      render(<SourceDirectoriesInput directories={[]} onChange={mockOnChange} disabled={true} />)
      expect(screen.getByRole('button', { name: /Add/i })).toBeDisabled()
    })

    it('disables delete buttons when disabled=true', () => {
      render(
        <SourceDirectoriesInput
          directories={['/some/dir']}
          onChange={mockOnChange}
          disabled={true}
        />
      )
      const deleteButtons = screen.getAllByRole('button')
      // The delete button should be disabled
      const deleteBtn = deleteButtons.find((btn) =>
        btn.querySelector('svg[data-testid="DeleteIcon"]')
      )
      expect(deleteBtn).toBeDisabled()
    })

    it('disables browse button when disabled=true', () => {
      render(
        <SourceDirectoriesInput
          directories={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
          disabled={true}
        />
      )
      expect(screen.getByTitle('Browse directories and files')).toBeDisabled()
    })
  })
})
