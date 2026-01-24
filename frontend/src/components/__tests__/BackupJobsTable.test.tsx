import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import BackupJobsTable from '../BackupJobsTable'

describe('BackupJobsTable', () => {
  const mockJobs = [
    {
      id: 1,
      repository: '/backup/repo1',
      repository_path: '/backup/repo1',
      type: 'backup',
      status: 'completed',
      started_at: '2024-01-20T10:00:00Z',
      completed_at: '2024-01-20T10:30:00Z',
      triggered_by: 'manual',
      has_logs: true,
    },
    {
      id: 2,
      repository: '/backup/repo2',
      repository_path: '/backup/repo2',
      type: 'restore',
      status: 'running',
      started_at: '2024-01-20T11:00:00Z',
      triggered_by: 'schedule',
      schedule_id: 5,
    },
    {
      id: 3,
      repository: '/backup/repo3',
      repository_path: '/backup/repo3',
      type: 'check',
      status: 'failed',
      started_at: '2024-01-20T09:00:00Z',
      completed_at: '2024-01-20T09:15:00Z',
      triggered_by: 'manual',
      error_message: 'Repository corrupted',
    },
  ]

  const mockRepositories = [
    { id: 1, name: 'Repo 1', path: '/backup/repo1' },
    { id: 2, name: 'Repo 2', path: '/backup/repo2' },
    { id: 3, name: 'Repo 3', path: '/backup/repo3' },
  ]

  const mockCallbacks = {
    onViewLogs: vi.fn(),
    onDownloadLogs: vi.fn(),
    onErrorDetails: vi.fn(),
    onCancelJob: vi.fn(),
    onBreakLock: vi.fn(),
    onRunNow: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders table with jobs', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      expect(screen.getByText('#1')).toBeInTheDocument()
      expect(screen.getByText('#2')).toBeInTheDocument()
      expect(screen.getByText('#3')).toBeInTheDocument()
    })

    it('displays job IDs with # prefix', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      expect(screen.getByText('#1')).toBeInTheDocument()
      expect(screen.getByText('#2')).toBeInTheDocument()
      expect(screen.getByText('#3')).toBeInTheDocument()
    })

    it('displays repository information', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} repositories={mockRepositories} />)

      // Repository paths are always shown in RepositoryCell
      expect(screen.getAllByText('/backup/repo1').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo2').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo3').length).toBeGreaterThan(0)
    })

    it('displays started date', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      // Check that dates are rendered (format will depend on dateUtils implementation)
      const startedCells = screen.getAllByText(/2024/i)
      expect(startedCells.length).toBeGreaterThan(0)
    })

    it('renders table headers', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      expect(screen.getByText('Job ID')).toBeInTheDocument()
      expect(screen.getByText('Repository')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
      expect(screen.getByText('Started')).toBeInTheDocument()
      expect(screen.getByText('Duration')).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('shows default empty state when no jobs', () => {
      renderWithProviders(<BackupJobsTable jobs={[]} />)

      expect(screen.getByText('No jobs found')).toBeInTheDocument()
      expect(screen.getByText('No backup jobs to display')).toBeInTheDocument()
    })

    it('shows custom empty state', () => {
      const customEmptyState = {
        title: 'Custom Title',
        description: 'Custom Description',
      }

      renderWithProviders(<BackupJobsTable jobs={[]} emptyState={customEmptyState} />)

      expect(screen.getByText('Custom Title')).toBeInTheDocument()
      expect(screen.getByText('Custom Description')).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('shows loading state', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} loading={true} />)

      // Loading spinner should be visible
      const loadingIndicator = document.querySelector('.MuiCircularProgress-root')
      expect(loadingIndicator).toBeInTheDocument()
    })
  })

  describe('Type Column', () => {
    it('does not show type column by default', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      expect(screen.queryByText('Type')).not.toBeInTheDocument()
    })

    it('shows type column when enabled', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} showTypeColumn={true} />)

      expect(screen.getByText('Type')).toBeInTheDocument()
    })

    it('displays correct type labels', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} showTypeColumn={true} />)

      expect(screen.getByText('Backup')).toBeInTheDocument()
      expect(screen.getByText('Restore')).toBeInTheDocument()
      expect(screen.getByText('Repository Check')).toBeInTheDocument()
    })

    it('displays type for all job types correctly', () => {
      const allTypesJobs = [
        { id: 1, repository: '/test', type: 'backup', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
        { id: 2, repository: '/test', type: 'restore', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
        { id: 3, repository: '/test', type: 'check', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
        { id: 4, repository: '/test', type: 'compact', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
        { id: 5, repository: '/test', type: 'prune', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
        { id: 6, repository: '/test', type: 'package', status: 'completed', started_at: '2024-01-20T10:00:00Z' },
      ]

      renderWithProviders(<BackupJobsTable jobs={allTypesJobs} showTypeColumn={true} />)

      expect(screen.getByText('Backup')).toBeInTheDocument()
      expect(screen.getByText('Restore')).toBeInTheDocument()
      expect(screen.getByText('Repository Check')).toBeInTheDocument()
      expect(screen.getByText('Compact')).toBeInTheDocument()
      expect(screen.getByText('Prune')).toBeInTheDocument()
      expect(screen.getByText('Package Install')).toBeInTheDocument()
    })
  })

  describe('Trigger Column', () => {
    it('does not show trigger column by default', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} />)

      expect(screen.queryByText('Trigger')).not.toBeInTheDocument()
    })

    it('shows trigger column when enabled', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} showTriggerColumn={true} />)

      expect(screen.getByText('Trigger')).toBeInTheDocument()
    })

    it('shows icons for manual and scheduled triggers', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} showTriggerColumn={true} />)

      // Check for calendar and user icons (lucide icons)
      const icons = document.querySelectorAll('.lucide')
      expect(icons.length).toBeGreaterThan(0)
    })
  })

  describe('Actions', () => {
    it('shows View Logs action when enabled', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ viewLogs: true }}
          onViewLogs={mockCallbacks.onViewLogs}
        />
      )

      // Query by aria-label from tooltip
      const viewButtons = screen.getAllByLabelText('View Logs')
      expect(viewButtons.length).toBeGreaterThan(0)
    })

    it('calls onViewLogs when View Logs is clicked', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ viewLogs: true }}
          onViewLogs={mockCallbacks.onViewLogs}
        />
      )

      // The aria-label is on the span, need to find the button inside
      const viewButtonContainer = screen.getAllByLabelText('View Logs')[0]
      const viewButton = viewButtonContainer.querySelector('button')
      expect(viewButton).toBeInTheDocument()

      if (viewButton) {
        await user.click(viewButton)
        expect(mockCallbacks.onViewLogs).toHaveBeenCalledWith(mockJobs[0])
      }
    })

    it('shows Download Logs only for jobs with logs', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ downloadLogs: true }}
          onDownloadLogs={mockCallbacks.onDownloadLogs}
        />
      )

      // Only job 1 has has_logs: true
      const downloadButtons = screen.getAllByLabelText('Download Logs')
      expect(downloadButtons.length).toBe(1)
    })

    it('shows Error Details only for failed jobs with error message', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ errorInfo: true }}
          onErrorDetails={mockCallbacks.onErrorDetails}
        />
      )

      // Only job 3 has status: 'failed' and error_message
      const errorButtons = screen.getAllByLabelText('View Error')
      expect(errorButtons.length).toBe(1)
    })

    it('calls onErrorDetails when Error Details is clicked', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ errorInfo: true }}
          onErrorDetails={mockCallbacks.onErrorDetails}
        />
      )

      const errorButtonContainer = screen.getByLabelText('View Error')
      const errorButton = errorButtonContainer.querySelector('button')
      expect(errorButton).toBeInTheDocument()

      if (errorButton) {
        await user.click(errorButton)
        expect(mockCallbacks.onErrorDetails).toHaveBeenCalledWith(mockJobs[2])
      }
    })

    it('shows Cancel only for running jobs', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ cancel: true }}
          onCancelJob={mockCallbacks.onCancelJob}
        />
      )

      // Only job 2 has status: 'running'
      const cancelButtons = screen.getAllByLabelText('Cancel Backup')
      expect(cancelButtons.length).toBe(1)
    })

    it('calls onCancelJob when Cancel is clicked', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ cancel: true }}
          onCancelJob={mockCallbacks.onCancelJob}
        />
      )

      const cancelButtonContainer = screen.getByLabelText('Cancel Backup')
      const cancelButton = cancelButtonContainer.querySelector('button')
      expect(cancelButton).toBeInTheDocument()

      if (cancelButton) {
        await user.click(cancelButton)
        expect(mockCallbacks.onCancelJob).toHaveBeenCalledWith(mockJobs[1])
      }
    })

    it('shows Break Lock only for running jobs', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ breakLock: true }}
          onBreakLock={mockCallbacks.onBreakLock}
        />
      )

      // Only job 2 has status: 'running'
      const breakLockButtons = screen.getAllByLabelText('Break Lock')
      expect(breakLockButtons.length).toBe(1)
    })

    it('shows Run Now only for non-running jobs', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ runNow: true }}
          onRunNow={mockCallbacks.onRunNow}
        />
      )

      // Jobs 1 and 3 are not running
      const runNowButtons = screen.getAllByLabelText('Run Now')
      expect(runNowButtons.length).toBe(2)
    })

    it('calls onRunNow when Run Now is clicked', async () => {
      const user = userEvent.setup()

      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{ runNow: true }}
          onRunNow={mockCallbacks.onRunNow}
        />
      )

      const runNowButtonContainer = screen.getAllByLabelText('Run Now')[0]
      const runNowButton = runNowButtonContainer.querySelector('button')
      expect(runNowButton).toBeInTheDocument()

      if (runNowButton) {
        await user.click(runNowButton)
        expect(mockCallbacks.onRunNow).toHaveBeenCalledWith(mockJobs[0])
      }
    })
  })

  describe('Repository Display', () => {
    it('shows repository path for all jobs', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} repositories={mockRepositories} />)

      // Repository paths are displayed in RepositoryCell
      expect(screen.getAllByText('/backup/repo1').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo2').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo3').length).toBeGreaterThan(0)
    })

    it('shows repository path when no repositories list provided', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} repositories={[]} />)

      expect(screen.getAllByText('/backup/repo1').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo2').length).toBeGreaterThan(0)
      expect(screen.getAllByText('/backup/repo3').length).toBeGreaterThan(0)
    })

    it('handles package type jobs differently', () => {
      const packageJob = [
        {
          id: 1,
          type: 'package',
          package_name: 'borg-backup',
          archive_name: 'borg-backup-v2',
          status: 'completed',
          started_at: '2024-01-20T10:00:00Z',
          completed_at: '2024-01-20T10:30:00Z',
        },
      ]

      renderWithProviders(<BackupJobsTable jobs={packageJob} showTypeColumn={true} />)

      expect(screen.getByText('borg-backup-v2')).toBeInTheDocument()
      expect(screen.getByText('Package Install')).toBeInTheDocument()
    })
  })

  describe('Action Configuration', () => {
    it('does not show actions when callbacks are not provided', () => {
      renderWithProviders(<BackupJobsTable jobs={mockJobs} actions={{ viewLogs: true }} />)

      expect(screen.queryByRole('button', { name: /View Logs/i })).not.toBeInTheDocument()
    })

    it('shows multiple actions when configured', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          actions={{
            viewLogs: true,
            downloadLogs: true,
            errorInfo: true,
            cancel: true,
            runNow: true,
          }}
          onViewLogs={mockCallbacks.onViewLogs}
          onDownloadLogs={mockCallbacks.onDownloadLogs}
          onErrorDetails={mockCallbacks.onErrorDetails}
          onCancelJob={mockCallbacks.onCancelJob}
          onRunNow={mockCallbacks.onRunNow}
        />
      )

      // Check that various actions are present using aria-labels
      expect(screen.getAllByLabelText('View Logs').length).toBeGreaterThan(0)
      expect(screen.getAllByLabelText('Run Now').length).toBeGreaterThan(0)
    })
  })

  describe('Integration Tests', () => {
    it('renders complete table with all features', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={mockJobs}
          repositories={mockRepositories}
          showTypeColumn={true}
          showTriggerColumn={true}
          actions={{
            viewLogs: true,
            downloadLogs: true,
            errorInfo: true,
            cancel: true,
            breakLock: true,
            runNow: true,
          }}
          onViewLogs={mockCallbacks.onViewLogs}
          onDownloadLogs={mockCallbacks.onDownloadLogs}
          onErrorDetails={mockCallbacks.onErrorDetails}
          onCancelJob={mockCallbacks.onCancelJob}
          onBreakLock={mockCallbacks.onBreakLock}
          onRunNow={mockCallbacks.onRunNow}
        />
      )

      // Check headers
      expect(screen.getByText('Job ID')).toBeInTheDocument()
      expect(screen.getByText('Repository')).toBeInTheDocument()
      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('Trigger')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()

      // Check jobs are rendered
      expect(screen.getByText('#1')).toBeInTheDocument()
      expect(screen.getByText('#2')).toBeInTheDocument()
      expect(screen.getByText('#3')).toBeInTheDocument()

      // Check types
      expect(screen.getByText('Backup')).toBeInTheDocument()
      expect(screen.getByText('Restore')).toBeInTheDocument()
      expect(screen.getByText('Repository Check')).toBeInTheDocument()
    })

    it('handles empty jobs array gracefully', () => {
      renderWithProviders(
        <BackupJobsTable
          jobs={[]}
          showTypeColumn={true}
          showTriggerColumn={true}
          onViewLogs={mockCallbacks.onViewLogs}
        />
      )

      expect(screen.getByText('No jobs found')).toBeInTheDocument()
    })
  })
})
