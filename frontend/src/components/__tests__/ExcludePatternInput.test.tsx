import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ExcludePatternInput from '../ExcludePatternInput'

describe('ExcludePatternInput', () => {
  const mockOnChange = vi.fn()
  const mockOnBrowseClick = vi.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
    mockOnBrowseClick.mockClear()
  })

  describe('Rendering', () => {
    it('renders title and description', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)
      expect(screen.getByText('Exclude Patterns (Optional)')).toBeInTheDocument()
      expect(screen.getByText(/Specify patterns to exclude/)).toBeInTheDocument()
    })

    it('renders existing patterns', () => {
      const patterns = ['*.log', '*.tmp', 'node_modules']
      render(<ExcludePatternInput patterns={patterns} onChange={mockOnChange} />)
      expect(screen.getByText('*.log')).toBeInTheDocument()
      expect(screen.getByText('*.tmp')).toBeInTheDocument()
      expect(screen.getByText('node_modules')).toBeInTheDocument()
    })

    it('renders input field with placeholder', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('*.log or /path/to/exclude')).toBeInTheDocument()
    })

    it('renders Add button', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)
      expect(screen.getByRole('button', { name: /Add/i })).toBeInTheDocument()
    })

    it('renders browse button when onBrowseClick provided', () => {
      render(
        <ExcludePatternInput
          patterns={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
        />
      )
      expect(screen.getByTitle('Browse to exclude')).toBeInTheDocument()
    })

    it('does not render browse button when onBrowseClick not provided', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)
      expect(screen.queryByTitle('Browse to exclude')).not.toBeInTheDocument()
    })
  })

  describe('Adding patterns', () => {
    it('adds pattern when clicking Add button', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '*.log')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['*.log'])
    })

    it('adds pattern when pressing Enter', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '__pycache__{enter}')

      expect(mockOnChange).toHaveBeenCalledWith(['__pycache__'])
    })

    it('appends to existing patterns', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={['*.log']} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '*.tmp')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['*.log', '*.tmp'])
    })

    it('trims whitespace from input', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '  *.log  ')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).toHaveBeenCalledWith(['*.log'])
    })

    it('clears input after adding', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '*.log')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(input).toHaveValue('')
    })

    it('does not add empty pattern', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('does not add whitespace-only pattern', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('*.log or /path/to/exclude')
      await user.type(input, '   ')
      await user.click(screen.getByRole('button', { name: /Add/i }))

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Removing patterns', () => {
    it('removes pattern when clicking delete button', async () => {
      const user = userEvent.setup()
      render(
        <ExcludePatternInput
          patterns={['*.log', '*.tmp', 'node_modules']}
          onChange={mockOnChange}
        />
      )

      // Get all delete buttons
      const deleteButtons = screen
        .getAllByRole('button')
        .filter((btn) => btn.querySelector('svg[data-testid="DeleteIcon"]'))

      // Click the second delete button (index 1 = *.tmp)
      await user.click(deleteButtons[1])

      expect(mockOnChange).toHaveBeenCalledWith(['*.log', 'node_modules'])
    })

    it('removes first pattern correctly', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={['*.log', '*.tmp']} onChange={mockOnChange} />)

      const deleteButtons = screen
        .getAllByRole('button')
        .filter((btn) => btn.querySelector('svg[data-testid="DeleteIcon"]'))

      await user.click(deleteButtons[0])

      expect(mockOnChange).toHaveBeenCalledWith(['*.tmp'])
    })

    it('removes last pattern correctly', async () => {
      const user = userEvent.setup()
      render(<ExcludePatternInput patterns={['*.log', '*.tmp']} onChange={mockOnChange} />)

      const deleteButtons = screen
        .getAllByRole('button')
        .filter((btn) => btn.querySelector('svg[data-testid="DeleteIcon"]'))

      await user.click(deleteButtons[1])

      expect(mockOnChange).toHaveBeenCalledWith(['*.log'])
    })
  })

  describe('Browse functionality', () => {
    it('calls onBrowseClick when browse button clicked', async () => {
      const user = userEvent.setup()
      render(
        <ExcludePatternInput
          patterns={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
        />
      )

      await user.click(screen.getByTitle('Browse to exclude'))

      expect(mockOnBrowseClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('Disabled state', () => {
    it('disables input when disabled=true', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} disabled={true} />)
      expect(screen.getByPlaceholderText('*.log or /path/to/exclude')).toBeDisabled()
    })

    it('disables Add button when disabled=true', () => {
      render(<ExcludePatternInput patterns={[]} onChange={mockOnChange} disabled={true} />)
      expect(screen.getByRole('button', { name: /Add/i })).toBeDisabled()
    })

    it('disables delete buttons when disabled=true', () => {
      render(<ExcludePatternInput patterns={['*.log']} onChange={mockOnChange} disabled={true} />)
      const deleteBtn = screen
        .getAllByRole('button')
        .find((btn) => btn.querySelector('svg[data-testid="DeleteIcon"]'))
      expect(deleteBtn).toBeDisabled()
    })

    it('disables browse button when disabled=true', () => {
      render(
        <ExcludePatternInput
          patterns={[]}
          onChange={mockOnChange}
          onBrowseClick={mockOnBrowseClick}
          disabled={true}
        />
      )
      expect(screen.getByTitle('Browse to exclude')).toBeDisabled()
    })
  })
})
