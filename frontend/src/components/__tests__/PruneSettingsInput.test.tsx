import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import PruneSettingsInput from '../PruneSettingsInput'

describe('PruneSettingsInput', () => {
  const defaultValues = {
    keepHourly: 0,
    keepDaily: 7,
    keepWeekly: 4,
    keepMonthly: 6,
    keepQuarterly: 0,
    keepYearly: 1,
  }

  it('renders all six input fields', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    expect(screen.getByLabelText(/Keep Hourly/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Keep Daily/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Keep Weekly/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Keep Monthly/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Keep Quarterly/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Keep Yearly/i)).toBeInTheDocument()
  })

  it('displays correct initial values', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    expect(screen.getByLabelText(/Keep Hourly/i)).toHaveValue(0)
    expect(screen.getByLabelText(/Keep Daily/i)).toHaveValue(7)
    expect(screen.getByLabelText(/Keep Weekly/i)).toHaveValue(4)
    expect(screen.getByLabelText(/Keep Monthly/i)).toHaveValue(6)
    expect(screen.getByLabelText(/Keep Quarterly/i)).toHaveValue(0)
    expect(screen.getByLabelText(/Keep Yearly/i)).toHaveValue(1)
  })

  it('calls onChange when hourly value changes', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    const hourlyInput = screen.getByLabelText(/Keep Hourly/i)
    fireEvent.change(hourlyInput, { target: { value: '24' } })

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValues,
      keepHourly: 24,
    })
  })

  it('calls onChange when daily value changes', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    const dailyInput = screen.getByLabelText(/Keep Daily/i)
    fireEvent.change(dailyInput, { target: { value: '14' } })

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValues,
      keepDaily: 14,
    })
  })

  it('prevents negative values', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    const dailyInput = screen.getByLabelText(/Keep Daily/i)
    fireEvent.change(dailyInput, { target: { value: '-5' } })

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValues,
      keepDaily: 0, // Should be clamped to 0
    })
  })

  it('handles invalid input gracefully', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    const weeklyInput = screen.getByLabelText(/Keep Weekly/i)
    fireEvent.change(weeklyInput, { target: { value: 'invalid' } })

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValues,
      keepWeekly: 0, // Should default to 0 for invalid input
    })
  })

  it('disables all inputs when disabled prop is true', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} disabled={true} />)

    expect(screen.getByLabelText(/Keep Hourly/i)).toBeDisabled()
    expect(screen.getByLabelText(/Keep Daily/i)).toBeDisabled()
    expect(screen.getByLabelText(/Keep Weekly/i)).toBeDisabled()
    expect(screen.getByLabelText(/Keep Monthly/i)).toBeDisabled()
    expect(screen.getByLabelText(/Keep Quarterly/i)).toBeDisabled()
    expect(screen.getByLabelText(/Keep Yearly/i)).toBeDisabled()
  })

  it('displays helper text for each field', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    expect(screen.getByText(/Hourly backups to keep/i)).toBeInTheDocument()
    expect(screen.getByText(/Daily backups to keep/i)).toBeInTheDocument()
    expect(screen.getByText(/Weekly backups to keep/i)).toBeInTheDocument()
    expect(screen.getByText(/Monthly backups to keep/i)).toBeInTheDocument()
    expect(screen.getByText(/Quarterly backups to keep/i)).toBeInTheDocument()
    expect(screen.getByText(/Yearly backups to keep/i)).toBeInTheDocument()
  })

  it('handles zero values correctly', () => {
    const onChange = vi.fn()
    const allZeroValues = {
      keepHourly: 0,
      keepDaily: 0,
      keepWeekly: 0,
      keepMonthly: 0,
      keepQuarterly: 0,
      keepYearly: 0,
    }

    render(<PruneSettingsInput values={allZeroValues} onChange={onChange} />)

    Object.values(screen.getAllByRole('spinbutton')).forEach((input) => {
      expect(input).toHaveValue(0)
    })
  })

  it('handles large values correctly', () => {
    const onChange = vi.fn()
    render(<PruneSettingsInput values={defaultValues} onChange={onChange} />)

    const yearlyInput = screen.getByLabelText(/Keep Yearly/i)
    fireEvent.change(yearlyInput, { target: { value: '999' } })

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValues,
      keepYearly: 999,
    })
  })
})
