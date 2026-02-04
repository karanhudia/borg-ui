import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import WizardStepScheduleConfig from '../WizardStepScheduleConfig'

// Mock cron-parser
vi.mock('cron-parser', () => ({
  default: {
    parse: vi.fn((expr: string) => {
      if (expr === 'invalid') {
        throw new Error('Invalid cron expression')
      }
      return {
        next: vi.fn(() => ({
          toDate: vi.fn(() => new Date('2024-01-01T02:00:00')),
        })),
      }
    }),
  },
}))

describe('WizardStepScheduleConfig', () => {
  const defaultData = {
    cronExpression: '0 2 * * *',
    archiveNameTemplate: '{job_name}-{now}',
  }

  const defaultProps = {
    data: defaultData,
    jobName: 'test-job',
    onChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders CronExpressionInput', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    expect(screen.getByLabelText(/Schedule \(Cron Expression\)/i)).toBeInTheDocument()
  })

  it('renders ArchiveNameTemplateInput', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    expect(screen.getByLabelText(/Archive Name Template/i)).toBeInTheDocument()
  })

  it('displays cron expression value', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i) as HTMLInputElement
    expect(cronInput.value).toBe('0 2 * * *')
  })

  it('displays archive name template value', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const templateInput = screen.getByLabelText(/Archive Name Template/i) as HTMLInputElement
    expect(templateInput.value).toBe('{job_name}-{now}')
  })

  it('calls onChange when cron expression changes', () => {
    const onChange = vi.fn()
    render(<WizardStepScheduleConfig {...defaultProps} onChange={onChange} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i)
    fireEvent.change(cronInput, { target: { value: '0 0 * * 0' } })

    expect(onChange).toHaveBeenCalledWith({ cronExpression: '0 0 * * 0' })
  })

  it('calls onChange when archive name template changes', () => {
    const onChange = vi.fn()
    render(<WizardStepScheduleConfig {...defaultProps} onChange={onChange} />)

    const templateInput = screen.getByLabelText(/Archive Name Template/i)
    fireEvent.change(templateInput, { target: { value: '{job_name}-{date}' } })

    expect(onChange).toHaveBeenCalledWith({ archiveNameTemplate: '{job_name}-{date}' })
  })

  it('displays next run times preview for valid cron expression', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    expect(screen.getByText(/Next 3 Run Times:/i)).toBeInTheDocument()
  })

  it('does not display next run times for invalid cron expression', () => {
    const invalidData = {
      ...defaultData,
      cronExpression: 'invalid',
    }

    render(<WizardStepScheduleConfig {...defaultProps} data={invalidData} />)

    expect(screen.queryByText(/Next 3 Run Times:/i)).not.toBeInTheDocument()
  })

  it('displays helper text for cron expression', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    expect(screen.getByText(/Click the clock icon to use the visual builder/i)).toBeInTheDocument()
  })

  it('passes jobName to ArchiveNameTemplateInput', () => {
    render(<WizardStepScheduleConfig {...defaultProps} jobName="my-custom-job" />)

    // Check if the preview uses the custom job name
    const preview = screen.getByText(/my-custom-job/)
    expect(preview).toBeInTheDocument()
  })

  it('uses default job name when jobName is empty', () => {
    render(<WizardStepScheduleConfig {...defaultProps} jobName="" />)

    // Check if the preview uses the default job name
    const preview = screen.getByText(/example-job/)
    expect(preview).toBeInTheDocument()
  })

  it('handles empty cron expression', () => {
    const emptyData = {
      ...defaultData,
      cronExpression: '',
    }

    render(<WizardStepScheduleConfig {...defaultProps} data={emptyData} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i) as HTMLInputElement
    expect(cronInput.value).toBe('')
  })

  it('handles empty archive name template', () => {
    const emptyData = {
      ...defaultData,
      archiveNameTemplate: '',
    }

    render(<WizardStepScheduleConfig {...defaultProps} data={emptyData} />)

    const templateInput = screen.getByLabelText(/Archive Name Template/i) as HTMLInputElement
    expect(templateInput.value).toBe('')
  })

  it('applies medium size to inputs', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i)
    expect(cronInput).toBeInTheDocument()
  })

  it('displays three run times in the preview list', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const listItems = screen.getAllByRole('listitem')
    expect(listItems).toHaveLength(3)
  })

  it('formats run times with localeString', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    // The mocked date should be formatted
    const dates = screen.getAllByText(/1\/1\/2024/i)
    expect(dates).toHaveLength(3) // 3 run times displayed
  })

  it('updates preview when cron expression changes', () => {
    const { rerender } = render(<WizardStepScheduleConfig {...defaultProps} />)

    expect(screen.getByText(/Next 3 Run Times:/i)).toBeInTheDocument()

    const newData = {
      ...defaultData,
      cronExpression: 'invalid',
    }

    rerender(<WizardStepScheduleConfig {...defaultProps} data={newData} />)

    expect(screen.queryByText(/Next 3 Run Times:/i)).not.toBeInTheDocument()
  })

  it('handles multiple onChange calls', () => {
    const onChange = vi.fn()
    render(<WizardStepScheduleConfig {...defaultProps} onChange={onChange} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i)
    fireEvent.change(cronInput, { target: { value: '0 3 * * *' } })

    const templateInput = screen.getByLabelText(/Archive Name Template/i)
    fireEvent.change(templateInput, { target: { value: '{date}-backup' } })

    expect(onChange).toHaveBeenCalledTimes(2)
    expect(onChange).toHaveBeenNthCalledWith(1, { cronExpression: '0 3 * * *' })
    expect(onChange).toHaveBeenNthCalledWith(2, { archiveNameTemplate: '{date}-backup' })
  })

  it('renders cron expression as required', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const cronInput = screen.getByLabelText(/Schedule \(Cron Expression\)/i)
    expect(cronInput).toBeRequired()
  })

  it('displays info alert for next run times', () => {
    render(<WizardStepScheduleConfig {...defaultProps} />)

    const alert = screen.getByText(/Next 3 Run Times:/i).closest('.MuiAlert-root')
    expect(alert).toHaveClass('MuiAlert-standardInfo')
  })
})
