import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ScheduledJobsTable from '../ScheduledJobsTable'

vi.mock('../ScheduleJobCard', () => ({
  default: ({ job }: { job: { name: string } }) => (
    <div data-testid="schedule-job-card">{job.name}</div>
  ),
}))

const baseJob = {
  id: 1,
  name: 'Daily Backup',
  cron_expression: '0 2 * * *',
  repository: null,
  repository_id: 1,
  repository_ids: null,
  enabled: true,
  last_run: null,
  next_run: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  description: 'Daily backup job',
  archive_name_template: null,
  run_repository_scripts: false,
  pre_backup_script_id: null,
  post_backup_script_id: null,
  run_prune_after: true,
  run_compact_after: false,
  prune_keep_hourly: 0,
  prune_keep_daily: 7,
  prune_keep_weekly: 4,
  prune_keep_monthly: 6,
  prune_keep_quarterly: 0,
  prune_keep_yearly: 1,
  last_prune: null,
  last_compact: null,
}

const defaultProps = {
  jobs: [baseJob],
  repositories: [{ id: 1, name: 'My Repo', path: '/backups/my-repo' }],
  isLoading: false,
  canManageJob: () => true,
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onDuplicate: vi.fn(),
  onRunNow: vi.fn(),
  onToggle: vi.fn(),
}

describe('ScheduledJobsTable', () => {
  it('renders the section title', () => {
    render(<ScheduledJobsTable {...defaultProps} />)
    expect(screen.getByText('All Scheduled Jobs')).toBeInTheDocument()
  })

  it('renders a card for each job', () => {
    render(<ScheduledJobsTable {...defaultProps} />)
    expect(screen.getAllByTestId('schedule-job-card')).toHaveLength(1)
    expect(screen.getByText('Daily Backup')).toBeInTheDocument()
  })

  it('renders multiple job cards', () => {
    const props = {
      ...defaultProps,
      jobs: [baseJob, { ...baseJob, id: 2, name: 'Weekly Backup' }],
    }
    render(<ScheduledJobsTable {...props} />)
    expect(screen.getAllByTestId('schedule-job-card')).toHaveLength(2)
  })

  it('shows loading state when isLoading is true', () => {
    render(<ScheduledJobsTable {...defaultProps} isLoading={true} />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows empty state when jobs array is empty', () => {
    render(<ScheduledJobsTable {...defaultProps} jobs={[]} />)
    expect(screen.getByText('No scheduled jobs found')).toBeInTheDocument()
  })

  it('renders the jobs list without an outer card wrapper', () => {
    const { container } = render(<ScheduledJobsTable {...defaultProps} />)
    expect(container.querySelector('.MuiCard-root')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('schedule-job-card')).toHaveLength(1)
  })
})
