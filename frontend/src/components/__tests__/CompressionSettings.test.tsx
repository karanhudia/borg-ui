import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CompressionSettings from '../CompressionSettings'

describe('CompressionSettings', () => {
  const mockOnChange = vi.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
  })

  describe('Rendering', () => {
    it('renders compression settings title', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByText('Compression Settings')).toBeInTheDocument()
    })

    it('renders compression algorithm selector', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByRole('combobox')).toBeInTheDocument()
    })

    it('renders level input for lz4 algorithm', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('Leave empty for default')).toBeInTheDocument()
    })

    it('renders obfuscate input', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('e.g., 110, 250')).toBeInTheDocument()
    })

    it('renders auto-detect checkbox for lz4', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByRole('checkbox')).toBeInTheDocument()
    })

    it('shows compression preview alert', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByText(/Final compression spec:/)).toBeInTheDocument()
    })
  })

  describe('Algorithm selection', () => {
    it('parses lz4 value correctly', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/lz4/)
    })

    it('parses zstd value correctly', () => {
      render(<CompressionSettings value="zstd,5" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/zstd/)
    })

    it('parses none value correctly', () => {
      render(<CompressionSettings value="none" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/none/)
    })

    it('parses zlib value correctly', () => {
      render(<CompressionSettings value="zlib,6" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/zlib/)
    })

    it('parses lzma value correctly', () => {
      render(<CompressionSettings value="lzma" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/lzma/)
    })
  })

  describe('Conditional rendering', () => {
    it('hides level and other inputs when algorithm is none', () => {
      render(<CompressionSettings value="none" onChange={mockOnChange} />)
      expect(screen.queryByPlaceholderText('Leave empty for default')).not.toBeInTheDocument()
      expect(screen.queryByPlaceholderText('e.g., 110, 250')).not.toBeInTheDocument()
    })

    it('shows level input when algorithm is zstd', () => {
      render(<CompressionSettings value="zstd" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('1-22 (default: 3)')).toBeInTheDocument()
    })

    it('shows level input when algorithm is zlib', () => {
      render(<CompressionSettings value="zlib" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('0-9 (default: 6)')).toBeInTheDocument()
    })

    it('shows level input when algorithm is lzma', () => {
      render(<CompressionSettings value="lzma" onChange={mockOnChange} />)
      expect(screen.getByPlaceholderText('0-9 (default: 6, max useful: 6)')).toBeInTheDocument()
    })

    it('parses auto value as lz4 with autoDetect enabled', () => {
      render(<CompressionSettings value="auto" onChange={mockOnChange} />)
      // "auto" parses to algorithm=lz4 with autoDetect=true
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/lz4/)
      // Auto-detect checkbox should be checked
      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeChecked()
    })

    it('parses obfuscate value as lz4 algorithm', () => {
      // "obfuscate" alone doesn't have a value after it, so it defaults to lz4
      render(<CompressionSettings value="obfuscate,110" onChange={mockOnChange} />)
      // With proper obfuscate value, algorithm defaults to lz4
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/lz4/)
    })
  })

  describe('onChange behavior', () => {
    it('calls onChange when algorithm changes', async () => {
      const user = userEvent.setup()
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)

      // Open the select dropdown
      const select = screen.getByRole('combobox')
      await user.click(select)

      // Select zstd
      const zstdOption = screen.getByRole('option', { name: /zstd/ })
      await user.click(zstdOption)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })
    })

    it('calls onChange when level changes', () => {
      render(<CompressionSettings value="zstd" onChange={mockOnChange} />)

      const levelInput = screen.getByPlaceholderText('1-22 (default: 3)')
      fireEvent.change(levelInput, { target: { value: '10' } })

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('calls onChange when obfuscate changes', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)

      const obfuscateInput = screen.getByPlaceholderText('e.g., 110, 250')
      fireEvent.change(obfuscateInput, { target: { value: '110' } })

      expect(mockOnChange).toHaveBeenCalled()
    })

    it('calls onChange when auto-detect is toggled', async () => {
      const user = userEvent.setup()
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })
    })
  })

  describe('Disabled state', () => {
    it('disables algorithm select when disabled=true', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} disabled={true} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables level input when disabled=true', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} disabled={true} />)
      const levelInput = screen.getByPlaceholderText('Leave empty for default')
      expect(levelInput).toBeDisabled()
    })

    it('disables obfuscate input when disabled=true', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} disabled={true} />)
      const obfuscateInput = screen.getByPlaceholderText('e.g., 110, 250')
      expect(obfuscateInput).toBeDisabled()
    })

    it('disables auto-detect checkbox when disabled=true', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} disabled={true} />)
      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeDisabled()
    })
  })

  describe('Helper text', () => {
    it('shows zstd specific helper text', () => {
      render(<CompressionSettings value="zstd" onChange={mockOnChange} />)
      expect(screen.getByText(/zstd: Level 1-22/)).toBeInTheDocument()
    })

    it('shows zlib specific helper text', () => {
      render(<CompressionSettings value="zlib" onChange={mockOnChange} />)
      expect(screen.getByText(/zlib: Level 0-9/)).toBeInTheDocument()
    })

    it('shows lzma specific helper text', () => {
      render(<CompressionSettings value="lzma" onChange={mockOnChange} />)
      expect(screen.getByText(/lzma: Level 0-9/)).toBeInTheDocument()
    })

    it('shows lz4 default helper text for auto value', () => {
      // "auto" parses to lz4 with autoDetect, so we see lz4 helper text
      render(<CompressionSettings value="auto" onChange={mockOnChange} />)
      expect(screen.getByText(/Leave empty to use default level/)).toBeInTheDocument()
    })

    it('shows auto-detect description text', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByText(/Uses lz4 to test if data is compressible/)).toBeInTheDocument()
    })

    it('shows obfuscate helper text', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByText(/Obfuscate compressed chunk sizes/)).toBeInTheDocument()
    })
  })

  describe('Auto value parsing', () => {
    it('shows enabled level input for auto value (parsed as lz4)', () => {
      // "auto" parses to lz4 with autoDetect=true, not algorithm="auto"
      render(<CompressionSettings value="auto" onChange={mockOnChange} />)
      const levelInput = screen.getByPlaceholderText('Leave empty for default')
      expect(levelInput).not.toBeDisabled()
    })
  })

  describe('External value changes', () => {
    it('updates state when value prop changes', () => {
      const { rerender } = render(<CompressionSettings value="lz4" onChange={mockOnChange} />)

      rerender(<CompressionSettings value="zstd,10" onChange={mockOnChange} />)

      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/zstd/)
    })

    it('handles empty value by defaulting to lz4', () => {
      render(<CompressionSettings value="" onChange={mockOnChange} />)
      const select = screen.getByRole('combobox')
      expect(select).toHaveTextContent(/lz4/)
    })
  })

  describe('Compression preview', () => {
    it('shows lz4 preview', () => {
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)
      expect(screen.getByRole('alert')).toHaveTextContent(/lz4/)
    })

    it('shows zstd preview with level', () => {
      render(<CompressionSettings value="zstd,10" onChange={mockOnChange} />)
      expect(screen.getByRole('alert')).toHaveTextContent(/zstd/)
    })

    it('shows auto,lz4 preview when auto-detect is enabled', async () => {
      const user = userEvent.setup()
      render(<CompressionSettings value="lz4" onChange={mockOnChange} />)

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/auto,lz4/)
      })
    })
  })
})
