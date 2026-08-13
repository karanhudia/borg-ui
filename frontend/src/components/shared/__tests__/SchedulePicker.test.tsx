import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SchedulePicker from '../SchedulePicker'

describe('SchedulePicker', () => {
  const defaultProps = {
    cronExpression: '0 2 * * *',
    timezone: 'UTC',
    onChange: vi.fn(),
  }

  it('renders cron expression and timezone', () => {
    render(<SchedulePicker {...defaultProps} />)
    expect(screen.getByDisplayValue('0 2 * * *')).toBeInTheDocument()
    expect(screen.getByDisplayValue('UTC')).toBeInTheDocument()
  })

  it('emits cronExpression updates through onChange', () => {
    const onChange = vi.fn()
    render(<SchedulePicker {...defaultProps} onChange={onChange} />)

    const cronInput = screen.getByDisplayValue('0 2 * * *')
    fireEvent.change(cronInput, { target: { value: '0 0 * * 0' } })

    expect(onChange).toHaveBeenCalledWith({ cronExpression: '0 0 * * 0' })
  })

  it('shows a next-run preview for valid cron expressions', () => {
    render(<SchedulePicker {...defaultProps} />)
    // The preview text contains the localized "Next run" label — assert via the
    // aria-label on the info icon to avoid coupling to translation strings.
    expect(screen.getAllByLabelText(/next/i).length).toBeGreaterThan(0)
  })

  it('omits the preview when the cron expression is invalid', () => {
    render(<SchedulePicker {...defaultProps} cronExpression="this is not cron" />)
    expect(screen.queryByLabelText(/next/i)).toBeNull()
  })

  it('renders a custom cron label when supplied', () => {
    render(<SchedulePicker {...defaultProps} cronLabel="Custom cron label" />)
    expect(screen.getByRole('textbox', { name: /Custom cron label/i })).toBeInTheDocument()
  })

  it('shows availability controls and emits availability policy updates', () => {
    const onChange = vi.fn()
    render(
      <SchedulePicker
        {...defaultProps}
        onChange={onChange}
        showTriggerMode
        scheduleMode="availability"
        availabilityCheckIntervalMinutes={30}
        minimumSuccessIntervalHours={20}
      />
    )

    expect(screen.getByDisplayValue('0 2 * * *')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/check every/i), { target: { value: '45' } })
    expect(onChange).toHaveBeenCalledWith({ availabilityCheckIntervalMinutes: 45 })
    fireEvent.change(screen.getByLabelText(/minimum interval/i), { target: { value: '24' } })
    expect(onChange).toHaveBeenCalledWith({ minimumSuccessIntervalHours: 24 })
  })
})
