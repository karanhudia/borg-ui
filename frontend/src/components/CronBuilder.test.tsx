import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CronBuilder from './CronBuilder'

// Mock dateUtils to avoid timezone complexity in component tests
vi.mock('../utils/dateUtils', () => ({
  convertCronToLocal: (cron: string) => cron, // Identity for test simplicity
  convertCronToUTC: (cron: string) => cron, // Identity for test simplicity
}))

describe('CronBuilder', () => {
  it('renders correctly with initial daily value', () => {
    render(<CronBuilder value="0 2 * * *" onChange={() => {}} />)

    // Should show "Daily" selected
    expect(screen.getByText('Daily')).toBeInTheDocument()
    // Should show time inputs
    expect(screen.getByText('Run daily at')).toBeInTheDocument()

    // The inputs should reflect 2:00 AM
    // Hours (0 2 => 2 AM)
    const inputs = screen.getAllByRole('spinbutton')
    // Hour
    expect(inputs[0]).toHaveValue(2)
    // Minute
    expect(inputs[1]).toHaveValue(0)
  })

  it('switches to Weekly frequency and shows days', () => {
    const handleChange = vi.fn()
    render(<CronBuilder value="0 2 * * *" onChange={handleChange} />)

    // Click "Weekly" toggle
    fireEvent.click(screen.getByText('Weekly'))

    // Should show "Run on" and day buttons
    expect(screen.getByText('Run on')).toBeInTheDocument()
    // Should have 7 day buttons (M T W T F S S)
    // Filter for the day toggles (length might include main toggles)
    // We can look for specific day letters or just check basic presence
    expect(screen.getByText('M')).toBeInTheDocument()
    expect(screen.getAllByText('S')).toHaveLength(2) // Sat, Sun
  })

  it('updates time when inputs change', () => {
    const handleChange = vi.fn()
    render(<CronBuilder value="0 2 * * *" onChange={handleChange} />)

    const inputs = screen.getAllByRole('spinbutton')
    const hourInput = inputs[0]

    // Change hour to 5
    fireEvent.change(hourInput, { target: { value: '5' } })

    // Since we mocked convert to identity, it should return constructed cron
    // 5 AM => 0 5 * * *
    expect(handleChange).toHaveBeenCalledWith('0 5 * * *')
  })

  it('handles interval inputs in Hourly mode', () => {
    const handleChange = vi.fn()
    render(
      <CronBuilder
        value="0 0 * * *" // Start daily
        onChange={handleChange}
      />
    )

    // Switch to Hourly
    fireEvent.click(screen.getByText('Hourly'))

    // Finding the "Run every [ ] hours" input
    // There are two inputs: Hour Interval and Minute Offset
    const inputs = screen.getAllByRole('spinbutton')
    const intervalInput = inputs[0]

    // Set interval to 8
    fireEvent.change(intervalInput, { target: { value: '8' } })

    // Should construct hourly cron
    // Default is */6, we changed to 8. starting minute 0.
    // 0 */8 * * *
    expect(handleChange).toHaveBeenCalledWith('0 */8 * * *')
  })
})
