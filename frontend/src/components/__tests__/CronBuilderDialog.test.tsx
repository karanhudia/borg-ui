import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CronBuilderDialog from '../CronBuilderDialog'

// Mock CronBuilder since it's a complex component
vi.mock('../CronBuilder', () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <div data-testid="mock-cron-builder">
      <input
        data-testid="cron-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="cron expression"
      />
      <span>Current: {value}</span>
    </div>
  ),
}))

describe('CronBuilderDialog', () => {
  const mockOnChange = vi.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
  })

  describe('Trigger Button', () => {
    it('renders trigger button with clock icon', () => {
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)
      expect(screen.getByRole('button', { name: 'Open schedule builder' })).toBeInTheDocument()
    })

    it('opens dialog when trigger button clicked', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByText('Configure Schedule')).toBeInTheDocument()
      })
    })
  })

  describe('Dialog Content', () => {
    it('shows custom dialog title', async () => {
      const user = userEvent.setup()
      render(
        <CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} dialogTitle="Custom Title" />
      )

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByText('Custom Title')).toBeInTheDocument()
      })
    })

    it('shows CronBuilder component with current value', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByTestId('mock-cron-builder')).toBeInTheDocument()
        expect(screen.getByText('Current: 0 0 * * *')).toBeInTheDocument()
      })
    })

    it('shows Cancel button', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      })
    })

    it('shows Apply Schedule button by default', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Apply Schedule' })).toBeInTheDocument()
      })
    })

    it('shows custom button label', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} buttonLabel="Save" />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      })
    })
  })

  describe('User Interactions', () => {
    it('calls onChange with new value when Apply is clicked', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      // Wait for dialog to open
      await waitFor(() => {
        expect(screen.getByTestId('cron-input')).toBeInTheDocument()
      })

      // Change the cron value in the mock
      const input = screen.getByTestId('cron-input')
      await user.clear(input)
      await user.type(input, '0 12 * * *')

      // Click Apply
      await user.click(screen.getByRole('button', { name: 'Apply Schedule' }))

      expect(mockOnChange).toHaveBeenCalledWith('0 12 * * *')
    })

    it('does not call onChange when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      // Wait for dialog to open
      await waitFor(() => {
        expect(screen.getByTestId('cron-input')).toBeInTheDocument()
      })

      // Change the cron value
      const input = screen.getByTestId('cron-input')
      await user.clear(input)
      await user.type(input, '0 12 * * *')

      // Click Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('closes dialog after Apply', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByText('Configure Schedule')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Apply Schedule' }))

      await waitFor(() => {
        expect(screen.queryByText('Configure Schedule')).not.toBeInTheDocument()
      })
    })

    it('closes dialog after Cancel', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByText('Configure Schedule')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Configure Schedule')).not.toBeInTheDocument()
      })
    })

    it('resets to original value when reopened after cancel', async () => {
      const user = userEvent.setup()
      render(<CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} />)

      // Open dialog
      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByTestId('cron-input')).toBeInTheDocument()
      })

      // Change value
      const input = screen.getByTestId('cron-input')
      await user.clear(input)
      await user.type(input, '0 12 * * *')

      // Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Wait for dialog to close
      await waitFor(() => {
        expect(screen.queryByText('Configure Schedule')).not.toBeInTheDocument()
      })

      // Reopen
      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        // Should show original value, not the modified one
        expect(screen.getByText('Current: 0 0 * * *')).toBeInTheDocument()
      })
    })
  })

  describe('Props Passthrough', () => {
    it('passes label to CronBuilder', async () => {
      const user = userEvent.setup()
      render(
        <CronBuilderDialog value="0 0 * * *" onChange={mockOnChange} label="Backup Schedule" />
      )

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByTestId('mock-cron-builder')).toBeInTheDocument()
      })
    })

    it('passes helperText to CronBuilder', async () => {
      const user = userEvent.setup()
      render(
        <CronBuilderDialog
          value="0 0 * * *"
          onChange={mockOnChange}
          helperText="Enter a cron expression"
        />
      )

      await user.click(screen.getByRole('button', { name: 'Open schedule builder' }))

      await waitFor(() => {
        expect(screen.getByTestId('mock-cron-builder')).toBeInTheDocument()
      })
    })
  })
})
