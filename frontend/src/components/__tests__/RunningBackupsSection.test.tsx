import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RunningBackupsSection from '../RunningBackupsSection'
import { BackupJob } from '../../types'

// Mock formatBytes from dateUtils
vi.mock('../../utils/dateUtils', () => ({
  formatBytes: vi.fn((bytes: number) => `${bytes} bytes`),
}))

describe('RunningBackupsSection', () => {
  const mockGetRepositoryName = vi.fn((path: string) => `Repository: ${path}`)
  const mockFormatRelativeTime = vi.fn((date: string | null | undefined) => {
    if (!date) return 'Never'
    return '2 hours ago'
  })
  const mockFormatDurationSeconds = vi.fn((seconds: number) => `${seconds}s`)
  const mockGetMaintenanceStatusLabel = vi.fn((status: string) => {
    if (status === 'prune_running') return 'Pruning repository...'
    if (status === 'compact_running') return 'Compacting repository...'
    return null
  })
  const mockGetMaintenanceStatusColor = vi.fn(() => 'info' as const)
  const mockOnCancelBackup = vi.fn()

  const mockRunningJob: BackupJob = {
    id: 1,
    repository: '/path/to/repo',
    status: 'running',
    started_at: '2024-01-01T12:00:00Z',
    progress_details: {
      nfiles: 1000,
      original_size: 5000000,
      compressed_size: 3000000,
      deduplicated_size: 2000000,
      current_file: '/home/user/document.pdf',
      backup_speed: 10.5,
      total_expected_size: 10000000,
      estimated_time_remaining: 300,
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when runningBackupJobs is empty', () => {
    const { container } = render(
      <RunningBackupsSection
        runningBackupJobs={[]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(container.firstChild).toBeNull()
  })

  it('renders header with running backups count', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Running Scheduled Backups')).toBeInTheDocument()
    expect(screen.getByText('1 active')).toBeInTheDocument()
  })

  it('displays job ID and repository name', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText(/Job #1/)).toBeInTheDocument()
    expect(screen.getByText(/Repository: \/path\/to\/repo/)).toBeInTheDocument()
    expect(mockGetRepositoryName).toHaveBeenCalledWith('/path/to/repo')
  })

  it('displays started time using formatRelativeTime', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText(/Started: 2 hours ago/)).toBeInTheDocument()
    expect(mockFormatRelativeTime).toHaveBeenCalledWith('2024-01-01T12:00:00Z')
  })

  it('displays current file being processed', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Current File:')).toBeInTheDocument()
    expect(screen.getByText('/home/user/document.pdf')).toBeInTheDocument()
  })

  it('displays files processed count', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Files Processed:')).toBeInTheDocument()
    expect(screen.getByText('1,000')).toBeInTheDocument()
  })

  it('displays size information', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Original Size:')).toBeInTheDocument()
    expect(screen.getByText('Compressed:')).toBeInTheDocument()
    expect(screen.getByText('Deduplicated:')).toBeInTheDocument()
  })

  it('displays backup speed', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Speed:')).toBeInTheDocument()
    expect(screen.getByText('10.50 MB/s')).toBeInTheDocument()
  })

  it('displays ETA when estimated_time_remaining is present', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('ETA:')).toBeInTheDocument()
    expect(mockFormatDurationSeconds).toHaveBeenCalledWith(300)
  })

  it('displays maintenance status when present', () => {
    const jobWithMaintenance: BackupJob = {
      ...mockRunningJob,
      maintenance_status: 'prune_running',
    }

    render(
      <RunningBackupsSection
        runningBackupJobs={[jobWithMaintenance]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('Pruning repository...')).toBeInTheDocument()
    expect(mockGetMaintenanceStatusLabel).toHaveBeenCalledWith('prune_running')
  })

  it('renders cancel button', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    const cancelButton = screen.getByRole('button', { name: /cancel backup/i })
    expect(cancelButton).toBeInTheDocument()
    expect(cancelButton).not.toBeDisabled()
  })

  it('calls onCancelBackup with confirmation', () => {
    // Mock window.confirm
    const confirmSpy = vi.fn(() => true)
    vi.stubGlobal('confirm', confirmSpy)

    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    const cancelButton = screen.getByRole('button', { name: /cancel backup/i })
    fireEvent.click(cancelButton)

    expect(confirmSpy).toHaveBeenCalledWith('Are you sure you want to cancel backup job #1?')
    expect(mockOnCancelBackup).toHaveBeenCalledWith(1)

    vi.unstubAllGlobals()
  })

  it('does not call onCancelBackup when confirmation is declined', () => {
    const confirmSpy = vi.fn(() => false)
    vi.stubGlobal('confirm', confirmSpy)

    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    const cancelButton = screen.getByRole('button', { name: /cancel backup/i })
    fireEvent.click(cancelButton)

    expect(confirmSpy).toHaveBeenCalled()
    expect(mockOnCancelBackup).not.toHaveBeenCalled()

    vi.unstubAllGlobals()
  })

  it('disables cancel button when isCancelling is true', () => {
    render(
      <RunningBackupsSection
        runningBackupJobs={[mockRunningJob]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={true}
      />
    )

    const cancelButton = screen.getByRole('button', { name: /cancel backup/i })
    expect(cancelButton).toBeDisabled()
  })

  it('renders multiple running jobs', () => {
    const jobs: BackupJob[] = [
      { ...mockRunningJob, id: 1 },
      { ...mockRunningJob, id: 2 },
    ]

    render(
      <RunningBackupsSection
        runningBackupJobs={jobs}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.getByText('2 active')).toBeInTheDocument()
    expect(screen.getByText(/Job #1/)).toBeInTheDocument()
    expect(screen.getByText(/Job #2/)).toBeInTheDocument()
  })

  it('handles job without current_file gracefully', () => {
    const jobWithoutFile: BackupJob = {
      ...mockRunningJob,
      progress_details: {
        ...mockRunningJob.progress_details!,
        current_file: '',
      },
    }

    render(
      <RunningBackupsSection
        runningBackupJobs={[jobWithoutFile]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.queryByText('Current File:')).not.toBeInTheDocument()
  })

  it('handles job without ETA gracefully', () => {
    const jobWithoutETA: BackupJob = {
      ...mockRunningJob,
      progress_details: {
        ...mockRunningJob.progress_details!,
        estimated_time_remaining: 0,
      },
    }

    render(
      <RunningBackupsSection
        runningBackupJobs={[jobWithoutETA]}
        getRepositoryName={mockGetRepositoryName}
        formatRelativeTime={mockFormatRelativeTime}
        formatDurationSeconds={mockFormatDurationSeconds}
        getMaintenanceStatusLabel={mockGetMaintenanceStatusLabel}
        getMaintenanceStatusColor={mockGetMaintenanceStatusColor}
        onCancelBackup={mockOnCancelBackup}
        isCancelling={false}
      />
    )

    expect(screen.queryByText('ETA:')).not.toBeInTheDocument()
  })
})
