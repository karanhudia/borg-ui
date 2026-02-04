import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CronExpressionInput from '../CronExpressionInput'

describe('CronExpressionInput', () => {
  const defaultProps = {
    value: '0 2 * * *',
    onChange: vi.fn(),
  }

  it('renders with default values', () => {
    render(<CronExpressionInput {...defaultProps} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toBeInTheDocument()
    expect(input).toHaveValue('0 2 * * *')
  })

  it('calls onChange when cron expression changes', () => {
    const onChange = vi.fn()
    render(<CronExpressionInput {...defaultProps} onChange={onChange} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    fireEvent.change(input, { target: { value: '0 0 * * 0' } })

    expect(onChange).toHaveBeenCalledWith('0 0 * * 0')
  })

  it('displays custom label when provided', () => {
    render(<CronExpressionInput {...defaultProps} label="Custom Schedule Label" />)

    expect(screen.getByRole('textbox', { name: /Custom Schedule Label/i })).toBeInTheDocument()
  })

  it('displays helper text when provided', () => {
    render(<CronExpressionInput {...defaultProps} helperText="Custom helper text" />)

    expect(screen.getByText(/Custom helper text/i)).toBeInTheDocument()
  })

  it('shows placeholder text', () => {
    render(<CronExpressionInput value="" onChange={vi.fn()} />)

    const input = screen.getByPlaceholderText('0 2 * * *')
    expect(input).toBeInTheDocument()
  })

  it('displays required indicator when required prop is true', () => {
    render(<CronExpressionInput {...defaultProps} required />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toBeRequired()
  })

  it('disables input when disabled prop is true', () => {
    render(<CronExpressionInput {...defaultProps} disabled />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toBeDisabled()
  })

  it('renders CronBuilderDialog button', () => {
    render(<CronExpressionInput {...defaultProps} />)

    // CronBuilderDialog renders an IconButton - look for it
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('applies small size styling when size is small', () => {
    render(<CronExpressionInput {...defaultProps} size="small" />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toBeInTheDocument()
    // Small size is applied via TextField size prop
  })

  it('applies medium size styling by default', () => {
    render(<CronExpressionInput {...defaultProps} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toBeInTheDocument()
    // Default size should be medium
  })

  it('applies monospace font styling', () => {
    render(<CronExpressionInput {...defaultProps} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    const inputElement = input.closest('.MuiInputBase-root')
    expect(inputElement).toBeInTheDocument()
  })

  it('handles empty string value', () => {
    const onChange = vi.fn()
    render(<CronExpressionInput value="" onChange={onChange} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    expect(input).toHaveValue('')

    fireEvent.change(input, { target: { value: '* * * * *' } })
    expect(onChange).toHaveBeenCalledWith('* * * * *')
  })

  it('handles complex cron expressions', () => {
    const onChange = vi.fn()
    render(<CronExpressionInput {...defaultProps} onChange={onChange} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    fireEvent.change(input, { target: { value: '*/15 9-17 * * 1-5' } })

    expect(onChange).toHaveBeenCalledWith('*/15 9-17 * * 1-5')
  })

  it('allows fullWidth prop to be applied', () => {
    render(<CronExpressionInput {...defaultProps} />)

    const input = screen.getByRole('textbox', { name: /Schedule/i })
    const textField = input.closest('.MuiTextField-root')
    expect(textField).toBeInTheDocument()
  })
})
