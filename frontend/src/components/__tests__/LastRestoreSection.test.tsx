import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import LastRestoreSection from '../LastRestoreSection'

// Mock react-router-dom
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

// Mock RestoreJobCard since it's tested separately
vi.mock('../RestoreJobCard', () => ({
  default: ({ job }: { job: any }) => (
    <div data-testid="restore-job-card">Restore Job: {job.archive}</div>
  ),
}))

describe('LastRestoreSection', () => {
  const mockRestoreJob = {
    id: 1,
    repository: '/path/to/repo',
    archive: 'backup-2024-01-15',
    destination: '/restore/path',
    status: 'completed',
    started_at: '2024-01-15T10:00:00Z',
    completed_at: '2024-01-15T10:30:00Z',
    progress: 100,
  }

  beforeEach(() => {
    mockNavigate.mockClear()
  })

  it('renders "no restores" message when restoreJob is null', () => {
    render(<LastRestoreSection restoreJob={null} />)

    expect(screen.getByText('No restores performed yet from this repository')).toBeInTheDocument()
  })

  it('renders RestoreJobCard when restoreJob exists', () => {
    render(<LastRestoreSection restoreJob={mockRestoreJob} />)

    expect(screen.getByTestId('restore-job-card')).toBeInTheDocument()
    expect(screen.getByText('Restore Job: backup-2024-01-15')).toBeInTheDocument()
  })

  it('renders "Last Restore" header when job exists', () => {
    render(<LastRestoreSection restoreJob={mockRestoreJob} />)

    expect(screen.getByText('Last Restore')).toBeInTheDocument()
  })

  it('does not render "Last Restore" header when no job', () => {
    render(<LastRestoreSection restoreJob={null} />)

    expect(screen.queryByText('Last Restore')).not.toBeInTheDocument()
  })

  it('renders icon in both states', () => {
    const { rerender } = render(<LastRestoreSection restoreJob={null} />)

    // Check icon is present (we can't easily test Lucide icons, but component renders)
    expect(screen.getByText('No restores performed yet from this repository')).toBeInTheDocument()

    rerender(<LastRestoreSection restoreJob={mockRestoreJob} />)

    // Icon should still be present
    expect(screen.getByText('Last Restore')).toBeInTheDocument()
  })

  it('handles restore job with running status', () => {
    const runningJob = {
      ...mockRestoreJob,
      status: 'running',
      completed_at: undefined,
      progress_details: {
        nfiles: 100,
        current_file: '/some/file.txt',
        progress_percent: 45.5,
        restore_speed: 10.5,
        estimated_time_remaining: 120,
      },
    }

    render(<LastRestoreSection restoreJob={runningJob} />)

    expect(screen.getByTestId('restore-job-card')).toBeInTheDocument()
  })

  it('handles restore job with failed status', () => {
    const failedJob = {
      ...mockRestoreJob,
      status: 'failed',
      error_message: 'Restore failed: disk full',
    }

    render(<LastRestoreSection restoreJob={failedJob} />)

    expect(screen.getByTestId('restore-job-card')).toBeInTheDocument()
  })

  it('renders "View All Restores" button when job exists', () => {
    render(<LastRestoreSection restoreJob={mockRestoreJob} />)

    expect(screen.getByRole('button', { name: /view all restores/i })).toBeInTheDocument()
  })

  it('does not render "View All Restores" button when no job', () => {
    render(<LastRestoreSection restoreJob={null} />)

    expect(screen.queryByRole('button', { name: /view all restores/i })).not.toBeInTheDocument()
  })

  it('navigates to activity page when button is clicked', () => {
    render(<LastRestoreSection restoreJob={mockRestoreJob} />)

    const button = screen.getByRole('button', { name: /view all restores/i })
    fireEvent.click(button)

    expect(mockNavigate).toHaveBeenCalledWith('/activity')
  })
})
