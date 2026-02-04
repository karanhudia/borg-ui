import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import BackupHistorySection from '../BackupHistorySection'

// Mock BackupJobsTable
vi.mock('../BackupJobsTable', () => ({
  default: ({ jobs, loading }: { jobs: unknown[]; loading: boolean }) => {
    if (loading) {
      return <div>Loading backup jobs...</div>
    }
    return <div data-testid="backup-jobs-table">Table with {jobs.length} jobs</div>
  },
}))

describe('BackupHistorySection', () => {
  const mockScheduledJobs = [
    {
      id: 1,
      name: 'Daily Backup',
      cron_expression: '0 2 * * *',
      repository: null,
      repository_id: null,
      repository_ids: [1],
      enabled: true,
      last_run: null,
      next_run: null,
      created_at: '2023-01-01T00:00:00Z',
      updated_at: null,
      description: null,
      archive_name_template: null,
      run_repository_scripts: false,
      pre_backup_script_id: null,
      post_backup_script_id: null,
      run_prune_after: false,
      run_compact_after: false,
      prune_keep_hourly: 0,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_quarterly: 0,
      prune_keep_yearly: 1,
      last_prune: null,
      last_compact: null,
    },
    {
      id: 2,
      name: 'Weekly Backup',
      cron_expression: '0 3 * * 0',
      repository: null,
      repository_id: null,
      repository_ids: [2],
      enabled: true,
      last_run: null,
      next_run: null,
      created_at: '2023-01-01T00:00:00Z',
      updated_at: null,
      description: null,
      archive_name_template: null,
      run_repository_scripts: false,
      pre_backup_script_id: null,
      post_backup_script_id: null,
      run_prune_after: false,
      run_compact_after: false,
      prune_keep_hourly: 0,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_quarterly: 0,
      prune_keep_yearly: 1,
      last_prune: null,
      last_compact: null,
    },
  ]

  const mockRepositories = [
    { id: 1, name: 'Repo A', path: '/path/to/repo-a' },
    { id: 2, name: 'Repo B', path: '/path/to/repo-b' },
  ]

  const mockBackupJobs = [
    {
      id: '1',
      repository: '/path/to/repo-a',
      status: 'completed' as const,
      started_at: '2024-01-01T12:00:00Z',
      completed_at: '2024-01-01T13:00:00Z',
      scheduled_job_id: 1,
    },
    {
      id: '2',
      repository: '/path/to/repo-b',
      status: 'failed' as const,
      started_at: '2024-01-02T12:00:00Z',
      scheduled_job_id: 2,
      error_message: 'Connection error',
    },
    {
      id: '3',
      repository: '/path/to/repo-a',
      status: 'completed_with_warnings' as const,
      started_at: '2024-01-03T12:00:00Z',
      completed_at: '2024-01-03T13:00:00Z',
      scheduled_job_id: 1,
    },
  ]

  const defaultProps = {
    backupJobs: mockBackupJobs,
    scheduledJobs: mockScheduledJobs,
    repositories: mockRepositories,
    isLoading: false,
    isAdmin: true,
    filterSchedule: 'all' as const,
    filterRepository: 'all',
    filterStatus: 'all',
    onFilterScheduleChange: vi.fn(),
    onFilterRepositoryChange: vi.fn(),
    onFilterStatusChange: vi.fn(),
  }

  it('renders header and description', () => {
    render(<BackupHistorySection {...defaultProps} />)

    expect(screen.getByText('Backup History')).toBeInTheDocument()
    expect(screen.getByText(/Showing 3 of 3 backup jobs/)).toBeInTheDocument()
  })

  it('renders three filter dropdowns', () => {
    render(<BackupHistorySection {...defaultProps} />)

    expect(screen.getAllByText('Schedule').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Repository').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Status').length).toBeGreaterThan(0)
  })

  it('renders BackupJobsTable with all jobs', () => {
    render(<BackupHistorySection {...defaultProps} />)

    expect(screen.getByTestId('backup-jobs-table')).toBeInTheDocument()
    expect(screen.getByText('Table with 3 jobs')).toBeInTheDocument()
  })

  it('shows loading state when isLoading is true', () => {
    render(<BackupHistorySection {...defaultProps} isLoading={true} />)

    expect(screen.getByText('Loading backup jobs...')).toBeInTheDocument()
  })

  it('filters by schedule', () => {
    render(<BackupHistorySection {...defaultProps} filterSchedule={1} />)

    // Jobs 1 and 3 have scheduled_job_id = 1
    expect(screen.getByText('Table with 2 jobs')).toBeInTheDocument()
    expect(screen.getByText(/Showing 2 of 3 backup jobs \(filtered\)/)).toBeInTheDocument()
  })

  it('filters by repository', () => {
    render(<BackupHistorySection {...defaultProps} filterRepository="/path/to/repo-a" />)

    // Jobs 1 and 3 have repository = '/path/to/repo-a'
    expect(screen.getByText('Table with 2 jobs')).toBeInTheDocument()
    expect(screen.getByText(/Showing 2 of 3 backup jobs \(filtered\)/)).toBeInTheDocument()
  })

  it('filters by completed status', () => {
    render(<BackupHistorySection {...defaultProps} filterStatus="completed" />)

    // Only job 1 has status = 'completed'
    expect(screen.getByText('Table with 1 jobs')).toBeInTheDocument()
    expect(screen.getByText(/Showing 1 of 3 backup jobs \(filtered\)/)).toBeInTheDocument()
  })

  it('filters by failed status', () => {
    render(<BackupHistorySection {...defaultProps} filterStatus="failed" />)

    // Only job 2 has status = 'failed'
    expect(screen.getByText('Table with 1 jobs')).toBeInTheDocument()
  })

  it('filters by warning status', () => {
    render(<BackupHistorySection {...defaultProps} filterStatus="warning" />)

    // Only job 3 has status = 'completed_with_warnings'
    expect(screen.getByText('Table with 1 jobs')).toBeInTheDocument()
  })

  it('combines multiple filters', () => {
    render(
      <BackupHistorySection
        {...defaultProps}
        filterSchedule={1}
        filterRepository="/path/to/repo-a"
        filterStatus="completed"
      />
    )

    // Only job 1 matches all filters
    expect(screen.getByText('Table with 1 jobs')).toBeInTheDocument()
  })

  it('calls onFilterScheduleChange when schedule filter changes', () => {
    const onFilterScheduleChange = vi.fn()
    render(
      <BackupHistorySection {...defaultProps} onFilterScheduleChange={onFilterScheduleChange} />
    )

    const scheduleSelect = screen.getByText('All Schedules')
    fireEvent.mouseDown(scheduleSelect)

    const listbox = within(screen.getByRole('listbox'))
    const dailyOption = listbox.getByText('Daily Backup')
    fireEvent.click(dailyOption)

    expect(onFilterScheduleChange).toHaveBeenCalledWith(1)
  })

  it('calls onFilterRepositoryChange when repository filter changes', () => {
    const onFilterRepositoryChange = vi.fn()
    render(
      <BackupHistorySection {...defaultProps} onFilterRepositoryChange={onFilterRepositoryChange} />
    )

    const repoSelect = screen.getByText('All Repositories')
    fireEvent.mouseDown(repoSelect)

    const listbox = within(screen.getByRole('listbox'))
    const repoOption = listbox.getByText('Repo A')
    fireEvent.click(repoOption)

    expect(onFilterRepositoryChange).toHaveBeenCalledWith('/path/to/repo-a')
  })

  it('calls onFilterStatusChange when status filter changes', () => {
    const onFilterStatusChange = vi.fn()
    render(<BackupHistorySection {...defaultProps} onFilterStatusChange={onFilterStatusChange} />)

    const statusSelect = screen.getByText('All Status')
    fireEvent.mouseDown(statusSelect)

    const listbox = within(screen.getByRole('listbox'))
    const completedOption = listbox.getByText('Completed')
    fireEvent.click(completedOption)

    expect(onFilterStatusChange).toHaveBeenCalledWith('completed')
  })

  it('renders all schedule options in dropdown', () => {
    render(<BackupHistorySection {...defaultProps} />)

    const scheduleSelect = screen.getByText('All Schedules')
    fireEvent.mouseDown(scheduleSelect)

    const listbox = within(screen.getByRole('listbox'))
    expect(listbox.getByText('All Schedules')).toBeInTheDocument()
    expect(listbox.getByText('Daily Backup')).toBeInTheDocument()
    expect(listbox.getByText('Weekly Backup')).toBeInTheDocument()
  })

  it('renders all repository options in dropdown', () => {
    render(<BackupHistorySection {...defaultProps} />)

    const repoSelect = screen.getByText('All Repositories')
    fireEvent.mouseDown(repoSelect)

    const listbox = within(screen.getByRole('listbox'))
    expect(listbox.getByText('All Repositories')).toBeInTheDocument()
    expect(listbox.getByText('Repo A')).toBeInTheDocument()
    expect(listbox.getByText('Repo B')).toBeInTheDocument()
  })

  it('renders all status options in dropdown', () => {
    render(<BackupHistorySection {...defaultProps} />)

    const statusSelect = screen.getByText('All Status')
    fireEvent.mouseDown(statusSelect)

    const listbox = within(screen.getByRole('listbox'))
    expect(listbox.getByText('All Status')).toBeInTheDocument()
    expect(listbox.getByText('Completed')).toBeInTheDocument()
    expect(listbox.getByText('Failed')).toBeInTheDocument()
    expect(listbox.getByText('Warning')).toBeInTheDocument()
  })

  it('shows no filtered indicator when no filters are applied', () => {
    render(<BackupHistorySection {...defaultProps} />)

    const description = screen.getByText(/Showing 3 of 3 backup jobs/)
    expect(description.textContent).not.toContain('(filtered)')
  })

  it('renders empty state when all jobs are filtered out', () => {
    render(<BackupHistorySection {...defaultProps} filterStatus="completed" filterSchedule={2} />)

    // No jobs match: schedule 2 has only a failed job
    expect(screen.getByText('Table with 0 jobs')).toBeInTheDocument()
    expect(screen.getByText(/Showing 0 of 3 backup jobs \(filtered\)/)).toBeInTheDocument()
  })

  it('renders with empty backup jobs array', () => {
    render(<BackupHistorySection {...defaultProps} backupJobs={[]} />)

    expect(screen.getByText('Table with 0 jobs')).toBeInTheDocument()
    expect(screen.getByText(/Showing 0 of 0 backup jobs/)).toBeInTheDocument()
  })
})
