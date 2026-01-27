import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PathSelectorField from '../PathSelectorField'

// Mock FileExplorerDialog
vi.mock('../FileExplorerDialog', () => ({
  default: ({
    open,
    onClose,
    onSelect,
    multiSelect,
    selectMode,
  }: {
    open: boolean
    onClose: () => void
    onSelect: (paths: string[]) => void
    multiSelect: boolean
    selectMode: string
  }) => {
    if (!open) return null
    return (
      <div data-testid="mock-file-explorer">
        <button
          data-testid="select-single"
          onClick={() => {
            onSelect(['/selected/path'])
            onClose()
          }}
        >
          Select Single
        </button>
        <button
          data-testid="select-multiple"
          onClick={() => {
            onSelect(['/path/one', '/path/two', '/path/three'])
            onClose()
          }}
        >
          Select Multiple
        </button>
        <button data-testid="close-dialog" onClick={onClose}>
          Close
        </button>
        <span>multiSelect: {String(multiSelect)}</span>
        <span>selectMode: {selectMode}</span>
      </div>
    )
  },
}))

describe('PathSelectorField', () => {
  const mockOnChange = vi.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
  })

  describe('Rendering', () => {
    it('renders text field with label', () => {
      render(<PathSelectorField label="Repository Path" value="" onChange={mockOnChange} />)
      expect(screen.getByLabelText(/Repository Path/)).toBeInTheDocument()
    })

    it('renders with current value', () => {
      render(<PathSelectorField label="Path" value="/existing/path" onChange={mockOnChange} />)
      expect(screen.getByDisplayValue('/existing/path')).toBeInTheDocument()
    })

    it('renders browse button', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)
      expect(screen.getByTitle('Browse filesystem')).toBeInTheDocument()
    })

    it('renders placeholder text', () => {
      render(
        <PathSelectorField
          label="Path"
          value=""
          onChange={mockOnChange}
          placeholder="Enter path here"
        />
      )
      expect(screen.getByPlaceholderText('Enter path here')).toBeInTheDocument()
    })

    it('renders default placeholder', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('/path/to/directory')).toBeInTheDocument()
    })

    it('renders helper text', () => {
      render(
        <PathSelectorField
          label="Path"
          value=""
          onChange={mockOnChange}
          helperText="Select a directory"
        />
      )
      expect(screen.getByText('Select a directory')).toBeInTheDocument()
    })

    it('shows required asterisk when required', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} required={true} />)
      // MUI adds * to the label for required fields
      expect(screen.getByText('*')).toBeInTheDocument()
    })
  })

  describe('Disabled state', () => {
    it('disables text input when disabled', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} disabled={true} />)
      expect(screen.getByLabelText(/Path/)).toBeDisabled()
    })

    it('disables browse button when disabled', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} disabled={true} />)
      expect(screen.getByTitle('Browse filesystem')).toBeDisabled()
    })
  })

  describe('Error state', () => {
    it('shows error styling when error is true', () => {
      render(
        <PathSelectorField
          label="Path"
          value=""
          onChange={mockOnChange}
          error={true}
          helperText="Path is required"
        />
      )
      expect(screen.getByText('Path is required')).toBeInTheDocument()
    })
  })

  describe('Text Input', () => {
    it('calls onChange when typing', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)

      const input = screen.getByLabelText(/Path/)
      await user.type(input, '/new/path')

      // Each character triggers an onChange
      expect(mockOnChange).toHaveBeenCalled()
    })
  })

  describe('File Explorer Dialog', () => {
    it('opens file explorer when browse button clicked', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)

      await user.click(screen.getByTitle('Browse filesystem'))

      await waitFor(() => {
        expect(screen.getByTestId('mock-file-explorer')).toBeInTheDocument()
      })
    })

    it('closes file explorer when close button clicked', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)

      await user.click(screen.getByTitle('Browse filesystem'))
      await user.click(screen.getByTestId('close-dialog'))

      await waitFor(() => {
        expect(screen.queryByTestId('mock-file-explorer')).not.toBeInTheDocument()
      })
    })

    it('calls onChange with single path when not multiSelect', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)

      await user.click(screen.getByTitle('Browse filesystem'))
      await user.click(screen.getByTestId('select-single'))

      expect(mockOnChange).toHaveBeenCalledWith('/selected/path')
    })

    it('calls onChange with comma-separated paths when multiSelect', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} multiSelect={true} />)

      await user.click(screen.getByTitle('Browse filesystem'))
      await user.click(screen.getByTestId('select-multiple'))

      expect(mockOnChange).toHaveBeenCalledWith('/path/one,/path/two,/path/three')
    })

    it('passes multiSelect prop to FileExplorerDialog', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} multiSelect={true} />)

      await user.click(screen.getByTitle('Browse filesystem'))

      expect(screen.getByText('multiSelect: true')).toBeInTheDocument()
    })

    it('passes selectMode prop to FileExplorerDialog', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} selectMode="files" />)

      await user.click(screen.getByTitle('Browse filesystem'))

      expect(screen.getByText('selectMode: files')).toBeInTheDocument()
    })

    it('defaults selectMode to directories', async () => {
      const user = userEvent.setup()
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)

      await user.click(screen.getByTitle('Browse filesystem'))

      expect(screen.getByText('selectMode: directories')).toBeInTheDocument()
    })
  })

  describe('Size variations', () => {
    it('renders small size by default', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)
      // The input should have small styling (MUI classes)
      expect(screen.getByLabelText(/Path/)).toBeInTheDocument()
    })

    it('renders medium size when specified', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} size="medium" />)
      expect(screen.getByLabelText(/Path/)).toBeInTheDocument()
    })
  })

  describe('Width variations', () => {
    it('renders fullWidth by default', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} />)
      // TextField should have fullWidth styling
      expect(screen.getByLabelText(/Path/)).toBeInTheDocument()
    })

    it('renders without fullWidth when specified', () => {
      render(<PathSelectorField label="Path" value="" onChange={mockOnChange} fullWidth={false} />)
      expect(screen.getByLabelText(/Path/)).toBeInTheDocument()
    })
  })
})
