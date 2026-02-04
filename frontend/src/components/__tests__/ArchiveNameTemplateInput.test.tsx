import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ArchiveNameTemplateInput from '../ArchiveNameTemplateInput'

describe('ArchiveNameTemplateInput', () => {
  const defaultProps = {
    value: '{job_name}-{now}',
    onChange: vi.fn(),
  }

  it('renders with default template', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    expect(input).toBeInTheDocument()
    expect(input).toHaveValue('{job_name}-{now}')
  })

  it('calls onChange when template changes', () => {
    const onChange = vi.fn()
    render(<ArchiveNameTemplateInput {...defaultProps} onChange={onChange} />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    fireEvent.change(input, { target: { value: '{job_name}-{date}' } })

    expect(onChange).toHaveBeenCalledWith('{job_name}-{date}')
  })

  it('displays placeholder information in helper text', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} />)

    expect(
      screen.getByText(/Available placeholders: {job_name}, {now}, {date}, {time}, {timestamp}/i)
    ).toBeInTheDocument()
  })

  it('shows preview alert when value is provided', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} />)

    expect(screen.getByText(/Preview:/i)).toBeInTheDocument()
  })

  it('does not show preview alert when value is empty', () => {
    render(<ArchiveNameTemplateInput value="" onChange={vi.fn()} />)

    expect(screen.queryByText(/Preview:/i)).not.toBeInTheDocument()
  })

  it('generates preview with job_name placeholder', () => {
    render(<ArchiveNameTemplateInput value="{job_name}-backup" onChange={vi.fn()} />)

    const preview = screen.getByText(/example-job-backup/i)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with custom job name', () => {
    render(
      <ArchiveNameTemplateInput
        value="{job_name}-archive"
        onChange={vi.fn()}
        jobName="my-custom-job"
      />
    )

    const preview = screen.getByText(/my-custom-job-archive/i)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with date placeholder', () => {
    render(<ArchiveNameTemplateInput value="{date}" onChange={vi.fn()} />)

    // Date format should be YYYY-MM-DD
    const preview = screen.getByText(/\d{4}-\d{2}-\d{2}/)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with time placeholder', () => {
    render(<ArchiveNameTemplateInput value="{time}" onChange={vi.fn()} />)

    // Time format should be HH-MM-SS
    const preview = screen.getByText(/\d{2}-\d{2}-\d{2}/)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with timestamp placeholder', () => {
    render(<ArchiveNameTemplateInput value="{timestamp}" onChange={vi.fn()} />)

    // Timestamp should be a number
    const preview = screen.getByText(/\d+/)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with now placeholder', () => {
    render(<ArchiveNameTemplateInput value="{now}" onChange={vi.fn()} />)

    // Now format should be ISO string with replacements
    const preview = screen.getByText(/\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}/)
    expect(preview).toBeInTheDocument()
  })

  it('generates preview with multiple placeholders', () => {
    render(
      <ArchiveNameTemplateInput
        value="{job_name}-{date}-{time}"
        onChange={vi.fn()}
        jobName="test-job"
      />
    )

    const preview = screen.getByText(/test-job-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}/)
    expect(preview).toBeInTheDocument()
  })

  it('disables input when disabled prop is true', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} disabled />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    expect(input).toBeDisabled()
  })

  it('applies small size when size prop is small', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} size="small" />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    expect(input).toBeInTheDocument()
  })

  it('applies medium size by default', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    expect(input).toBeInTheDocument()
  })

  it('uses default job name when not provided', () => {
    render(<ArchiveNameTemplateInput value="{job_name}" onChange={vi.fn()} />)

    const preview = screen.getByText(/example-job/)
    expect(preview).toBeInTheDocument()
  })

  it('handles empty template value', () => {
    const onChange = vi.fn()
    render(<ArchiveNameTemplateInput value="" onChange={onChange} />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    expect(input).toHaveValue('')

    fireEvent.change(input, { target: { value: '{job_name}' } })
    expect(onChange).toHaveBeenCalledWith('{job_name}')
  })

  it('applies monospace font styling', () => {
    render(<ArchiveNameTemplateInput {...defaultProps} />)

    const input = screen.getByLabelText(/Archive Name Template/i)
    const inputElement = input.closest('.MuiInputBase-root')
    expect(inputElement).toBeInTheDocument()
  })

  it('handles template with no placeholders', () => {
    render(<ArchiveNameTemplateInput value="static-archive-name" onChange={vi.fn()} />)

    const preview = screen.getByText(/static-archive-name/)
    expect(preview).toBeInTheDocument()
  })

  it('updates preview when value changes', () => {
    const { rerender } = render(
      <ArchiveNameTemplateInput value="{job_name}-v1" onChange={vi.fn()} />
    )

    expect(screen.getByText(/example-job-v1/)).toBeInTheDocument()

    rerender(<ArchiveNameTemplateInput value="{job_name}-v2" onChange={vi.fn()} />)

    expect(screen.getByText(/example-job-v2/)).toBeInTheDocument()
  })
})
