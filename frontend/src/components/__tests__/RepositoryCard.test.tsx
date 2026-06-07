import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import RepositoryCard from '../RepositoryCard'
import * as useMaintenanceJobsModule from '../../hooks/useMaintenanceJobs'
import * as useAnalyticsModule from '../../hooks/useAnalytics'

// Mock the hooks
vi.mock('../../hooks/useMaintenanceJobs')
vi.mock('../../hooks/useAnalytics')

describe('RepositoryCard', () => {
  const mockRepository = {
    id: 1,
    name: 'Test Repository',
    path: '/path/to/repo',
    encryption: 'repokey',
    compression: 'lz4',
    source_directories: ['/source/path1', '/source/path2'],
    exclude_patterns: ['*.tmp', '*.log'],
    last_backup: '2024-01-20T10:30:00Z',
    last_check: '2024-01-19T09:00:00Z',
    last_compact: '2024-01-18T08:00:00Z',
    total_size: '10.5 GB',
    archive_count: 25,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-20T10:30:00Z',
    mode: 'full' as const,
    has_running_maintenance: false,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    next_run: null,
  }

  const mockCallbacks = {
    onViewInfo: vi.fn(),
    onCheck: vi.fn(),
    onCompact: vi.fn(),
    onPrune: vi.fn(),
    onWipeContents: vi.fn(),
    onBreakLock: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onBackupNow: vi.fn(),
    onViewArchives: vi.fn(),
    onViewBackupPlans: vi.fn(),
    onCreateBackupPlan: vi.fn(),
    onJobCompleted: vi.fn(),
    canDo: vi.fn().mockReturnValue(true),
  }

  const mockGetCompressionLabel = vi.fn((compression: string) => {
    const labels: { [key: string]: string } = {
      lz4: 'LZ4 (Fast)',
      zstd: 'Zstandard',
      zlib: 'ZLIB',
      lzma: 'LZMA',
      none: 'None',
    }
    return labels[compression] || compression
  })

  const mockAnalyticsTracking = {
    trackRepository: vi.fn(),
    trackBackup: vi.fn(),
    trackMaintenance: vi.fn(),
    trackArchive: vi.fn(),
    trackPage: vi.fn(),
    track: vi.fn(),
    trackMount: vi.fn(),
    trackSSH: vi.fn(),
    trackSettings: vi.fn(),
    trackScripts: vi.fn(),
    trackNotifications: vi.fn(),
    trackSystem: vi.fn(),
    trackPackage: vi.fn(),
    trackNavigation: vi.fn(),
    trackPlan: vi.fn(),
    trackRemoteClient: vi.fn(),
    trackAnnouncement: vi.fn(),
    trackAuth: vi.fn(),
    buildEntityData: vi.fn(),
    EventCategory: {
      REPOSITORY: 'Repository',
      BACKUP: 'Backup',
      ARCHIVE: 'Archive',
      MOUNT: 'Mount',
      MAINTENANCE: 'Maintenance',
      SSH: 'SSH Connection',
      SCRIPT: 'Script',
      NOTIFICATION: 'Notification',
      SYSTEM: 'System',
      PACKAGE: 'Package',
      SETTINGS: 'Settings',
      AUTH: 'Authentication',
      NAVIGATION: 'Navigation',
      PLAN: 'Plan',
      ANNOUNCEMENT: 'Announcement',
      REMOTE_CLIENT: 'Remote Client',
    } as const,
    EventAction: {
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
      VIEW: 'View',
      START: 'Start',
      STOP: 'Stop',
      MOUNT: 'Mount',
      UNMOUNT: 'Unmount',
      DOWNLOAD: 'Download',
      UPLOAD: 'Upload',
      TEST: 'Test',
      LOGIN: 'Login',
      LOGOUT: 'Logout',
      SEARCH: 'Search',
      FILTER: 'Filter',
      EXPORT: 'Export',
      SWITCH: 'Switch',
      COMPLETE: 'Complete',
      FAIL: 'Fail',
      FEATURE_USED: 'FeatureUsed',
      FEATURE_BLOCKED: 'FeatureBlocked',
    } as const,
  }

  const mockMaintenanceJobs = {
    hasRunningJobs: false,
    checkJob: null,
    compactJob: null,
    pruneJob: null,
    wipeJob: null,
    isLoading: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Setup default mocks
    vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue(mockMaintenanceJobs)
    vi.spyOn(useAnalyticsModule, 'useAnalytics').mockReturnValue(mockAnalyticsTracking)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders repository name and path', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Test Repository')).toBeInTheDocument()
      expect(screen.getByText('/path/to/repo')).toBeInTheDocument()
    })

    it('renders archive count', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Archives')).toBeInTheDocument()
      expect(screen.getByText('25')).toBeInTheDocument()
    })

    it('renders total size', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Total Size')).toBeInTheDocument()
      expect(screen.getByText('10.5 GB')).toBeInTheDocument()
    })

    it('renders next backup badge when an enabled schedule exists', () => {
      renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            has_schedule: true,
            schedule_enabled: true,
            schedule_name: 'Daily Backup',
            next_run: '2099-04-14T02:00:00Z',
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText(/Next:/)).toBeInTheDocument()
    })

    it('renders paused schedule badge when schedule is disabled', () => {
      renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            has_schedule: true,
            schedule_enabled: false,
            schedule_name: 'Nightly',
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Schedule paused')).toBeInTheDocument()
    })

    it('renders scheduled cloud mirror next-run state and failure state', () => {
      const scheduledMirrorStorage = {
        repository_id: 1,
        backend: 'rclone' as const,
        rclone_remote_id: 10,
        rclone_remote_name: 'prod-s3',
        rclone_remote_path: 'borg-ui/repositories/app',
        rclone_target: 'prod-s3:borg-ui/repositories/app',
        cache_present: true,
        sync_policy: 'scheduled' as const,
        sync_status: 'current',
        sync_cron_expression: '0 */6 * * *',
        sync_timezone: 'UTC',
        next_scheduled_sync_at: '2099-04-14T02:00:00Z',
      }

      const { rerender } = renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            rclone_storage: scheduledMirrorStorage,
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText(/Mirror:/)).toBeInTheDocument()

      rerender(
        <RepositoryCard
          repository={{
            ...mockRepository,
            rclone_storage: {
              ...scheduledMirrorStorage,
              sync_status: 'failed',
              last_sync_error: 'manual sync failed',
              latest_sync_job: {
                id: 3,
                triggered_by: 'manual',
                status: 'failed',
                completed_at: '2099-04-14T01:00:05Z',
                error_text: 'manual sync failed',
                has_log: true,
              },
            },
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByText('Mirror failed')).not.toBeInTheDocument()

      rerender(
        <RepositoryCard
          repository={{
            ...mockRepository,
            rclone_storage: {
              ...scheduledMirrorStorage,
              sync_status: 'failed',
              last_sync_error: 'remote unavailable',
              latest_sync_job: {
                id: 4,
                triggered_by: 'schedule',
                status: 'failed',
                scheduled_for: '2099-04-14T02:00:00Z',
                completed_at: '2099-04-14T02:00:05Z',
                error_text: 'remote unavailable',
                has_log: true,
              },
            },
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Mirror failed')).toBeInTheDocument()
    })

    it('renders N/A for missing total size', () => {
      const repoWithoutSize = { ...mockRepository, total_size: null }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithoutSize}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('N/A')).toBeInTheDocument()
    })

    it('renders encryption type', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText(/^Encryption:/i)).toBeInTheDocument()
      expect(screen.getByText('repokey')).toBeInTheDocument()
    })

    it('renders compression with label', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText(/^Compression:/i)).toBeInTheDocument()
      expect(screen.getByText('LZ4 (Fast)')).toBeInTheDocument()
      expect(mockGetCompressionLabel).toHaveBeenCalledWith('lz4')
    })

    it('renders source directories count', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText(/^Source Paths:/i)).toBeInTheDocument()
      expect(screen.getByText('2 paths')).toBeInTheDocument()
    })

    it('renders singular "path" for single source directory', () => {
      const repoWithOneSource = {
        ...mockRepository,
        source_directories: ['/source/path1'],
      }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithOneSource}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('1 path')).toBeInTheDocument()
    })

    it('does not render source paths section when empty', () => {
      const repoWithoutSources = {
        ...mockRepository,
        source_directories: [],
      }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithoutSources}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByText(/^Source Paths:/i)).not.toBeInTheDocument()
    })
  })

  describe('Observe Mode', () => {
    it('displays "Observe Only" chip for observe mode repositories', () => {
      const observeRepo = { ...mockRepository, mode: 'observe' as const }
      renderWithProviders(
        <RepositoryCard
          repository={observeRepo}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Observe Only')).toBeInTheDocument()
    })

    it('does not display "Observe Only" chip for full mode repositories', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByText('Observe Only')).not.toBeInTheDocument()
    })

    it('does not show legacy backup button for observe mode', () => {
      const observeRepo = { ...mockRepository, mode: 'observe' as const }
      renderWithProviders(
        <RepositoryCard
          repository={observeRepo}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByRole('button', { name: /Legacy Backup/i })).not.toBeInTheDocument()
    })

    it('shows legacy backup button for full mode repositories with source paths', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Legacy Backup/i })).toBeInTheDocument()
    })

    it('shows Create Backup Plan as the primary repository backup action', () => {
      renderWithProviders(
        <RepositoryCard
          repository={{ ...mockRepository, source_directories: [] }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Create Backup Plan/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Legacy Backup/i })).not.toBeInTheDocument()
    })

    it('hides Compact and Prune buttons for observe mode but still allows Delete', () => {
      const observeRepo = { ...mockRepository, mode: 'observe' as const }
      renderWithProviders(
        <RepositoryCard
          repository={observeRepo}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByRole('button', { name: /Compact/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Prune/i })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Delete/i })).toBeInTheDocument()
    })

    it('shows maintenance and destructive buttons for full mode', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          canBreakLock={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Compact/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Prune/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Break Lock/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Wipe contents/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Delete/i })).toBeInTheDocument()
    })

    it('shows Info, Check, and View Archives buttons for observe mode', () => {
      const observeRepo = { ...mockRepository, mode: 'observe' as const }
      renderWithProviders(
        <RepositoryCard
          repository={observeRepo}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Info/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Check/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /View Archives/i })).toBeInTheDocument()
    })
  })

  describe('Admin Features', () => {
    it('shows Edit button when user is admin', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Edit/i })).toBeInTheDocument()
    })

    it('does not show Edit button when user is not admin', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={false}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument()
    })

    it('does not show action buttons when user is not admin', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={false}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          canDo={() => false}
        />
      )

      expect(screen.queryByRole('button', { name: /Info/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Check/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Compact/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Break Lock/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Wipe contents/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Delete/i })).not.toBeInTheDocument()
    })
  })

  describe('Action Buttons', () => {
    it('calls onEdit when Edit button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Edit/i }))
      expect(mockCallbacks.onEdit).toHaveBeenCalledTimes(1)
    })

    it('calls onViewInfo and tracks event when Info button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Info/i }))
      expect(mockCallbacks.onViewInfo).toHaveBeenCalledTimes(1)
      expect(mockAnalyticsTracking.trackRepository).toHaveBeenCalledWith('View', mockRepository)
    })

    it('calls onCheck when Check button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Check/i }))
      expect(mockCallbacks.onCheck).toHaveBeenCalledTimes(1)
    })

    it('calls onCompact when Compact button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Compact/i }))
      expect(mockCallbacks.onCompact).toHaveBeenCalledTimes(1)
    })

    it('calls onPrune when Prune button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Prune/i }))
      expect(mockCallbacks.onPrune).toHaveBeenCalledTimes(1)
    })

    it('calls onWipeContents when Wipe contents button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Wipe contents/i }))
      expect(mockCallbacks.onWipeContents).toHaveBeenCalledTimes(1)
    })

    it('calls onBreakLock when Break Lock button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          canBreakLock={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Break Lock/i }))
      expect(mockCallbacks.onBreakLock).toHaveBeenCalledTimes(1)
    })

    it('calls onBackupNow and tracks event when Legacy Backup button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Legacy Backup/i }))
      expect(mockCallbacks.onBackupNow).toHaveBeenCalledTimes(1)
      expect(mockAnalyticsTracking.trackBackup).toHaveBeenCalledWith(
        'Start',
        'legacy_repository',
        mockRepository
      )
    })

    it('calls onCreateBackupPlan when Create Backup Plan button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={{ ...mockRepository, source_directories: [] }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Create Backup Plan/i }))
      expect(mockCallbacks.onCreateBackupPlan).toHaveBeenCalledTimes(1)
    })

    it('calls onViewArchives and tracks event when View Archives button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /View Archives/i }))
      expect(mockCallbacks.onViewArchives).toHaveBeenCalledTimes(1)
      expect(mockAnalyticsTracking.trackArchive).toHaveBeenCalledWith('View', mockRepository)
    })

    it('calls onViewBackupPlans and tracks event when View linked backup plans button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /View linked backup plans/i }))

      expect(mockCallbacks.onViewBackupPlans).toHaveBeenCalledTimes(1)
      expect(mockAnalyticsTracking.trackRepository).toHaveBeenCalledWith('View', mockRepository, {
        destination: 'backup_plans',
      })
    })

    it('calls onDelete when Delete button is clicked', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      const deleteButtons = screen.getAllByRole('button', { name: /Delete/i })
      // The last Delete button is the main delete action (first one is Prune button icon)
      fireEvent.click(deleteButtons[deleteButtons.length - 1])
      expect(mockCallbacks.onDelete).toHaveBeenCalledTimes(1)
    })
  })

  describe('Maintenance Jobs', () => {
    it('disables all action buttons when maintenance is running', () => {
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
      })

      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByRole('button', { name: /Info/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Check/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Compact/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Prune/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Legacy Backup/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Create Backup Plan/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /View Archives/i })).toBeDisabled()
    })

    it('shows progress message for check job', () => {
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
        checkJob: {
          id: 1,
          progress: 50,
          progress_message: 'Checking repository integrity...',
          started_at: '2024-01-20T10:00:00Z',
        },
      })

      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Checking repository integrity...')).toBeInTheDocument()
    })

    it('shows progress message for compact job', () => {
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
        compactJob: {
          id: 2,
          progress: 75,
          progress_message: 'Compacting segments...',
          started_at: '2024-01-20T10:00:00Z',
        },
      })

      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Compacting segments...')).toBeInTheDocument()
    })

    it('shows spinning icon for check button when check job is running', () => {
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
        checkJob: {
          id: 1,
          progress: 50,
          progress_message: 'Checking...',
          started_at: '2024-01-20T10:00:00Z',
        },
      })

      const { container } = renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Check button should have spinning icon
      const checkButton = screen.getByRole('button', { name: /Check/i })
      expect(checkButton).toBeInTheDocument()
      // Verify the button contains a refresh icon with animate-spin class
      const spinningIcon = container.querySelector('.animate-spin')
      expect(spinningIcon).toBeInTheDocument()
    })

    it('calls onJobCompleted and invalidates queries when jobs complete', async () => {
      // Start with running jobs
      const { rerender } = renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={true}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Initial state: jobs running
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
      })

      // Jobs complete
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: false,
      })

      // Rerender to trigger the useEffect
      rerender(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={true}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      await waitFor(() => {
        expect(mockCallbacks.onJobCompleted).toHaveBeenCalledWith(mockRepository.id)
      })
    })
  })

  describe('Date Display', () => {
    it('displays "Never" for repositories without last_backup', () => {
      const repoWithoutBackup = { ...mockRepository, last_backup: null }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithoutBackup}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Never')).toBeInTheDocument()
    })

    it('displays "Never" for repositories without last_check', () => {
      const repoWithoutCheck = { ...mockRepository, last_check: null }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithoutCheck}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getAllByText('Never').length).toBeGreaterThan(0)
    })

    it('displays "Never" for repositories without last_compact', () => {
      const repoWithoutCompact = { ...mockRepository, last_compact: null }
      renderWithProviders(
        <RepositoryCard
          repository={repoWithoutCompact}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getAllByText('Never').length).toBeGreaterThan(0)
    })
  })

  describe('Rclone Storage', () => {
    it('exposes enable cloud mirror for eligible local repositories', () => {
      const onEdit = vi.fn()

      renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            repository_type: 'local',
            storage_backend: 'local',
            execution_target: 'local',
            connection_id: null,
            rclone_storage: null,
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          onEdit={onEdit}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Enable cloud mirror/i }))

      expect(onEdit).toHaveBeenCalled()
    })

    it('exposes enable cloud mirror for eligible SSH repositories', () => {
      const onEdit = vi.fn()

      renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            repository_type: 'ssh',
            storage_backend: 'ssh',
            execution_target: 'ssh',
            executor_type: 'server',
            connection_id: 1,
            rclone_storage: null,
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          onEdit={onEdit}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: /Enable cloud mirror/i }))

      expect(onEdit).toHaveBeenCalled()
    })

    it('exposes enable cloud mirror for eligible managed-agent repositories', () => {
      const onEdit = vi.fn()

      renderWithProviders(
        <RepositoryCard
          repository={{
            ...mockRepository,
            repository_type: 'local',
            storage_backend: 'agent_local',
            execution_target: 'agent',
            executor_type: 'agent',
            agent_machine_id: 101,
            agent_machine_name: 'workstation.local',
            agent_machine_status: 'online',
            rclone_storage: null,
          }}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          onEdit={onEdit}
        />
      )

      expect(screen.getByText('Agent: workstation.local')).toBeInTheDocument()
      expect(screen.getByText('Online')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /Enable cloud mirror/i }))

      expect(onEdit).toHaveBeenCalled()
    })

    it('renders rclone sync status, target, and mirror actions', () => {
      const rcloneRepository = {
        ...mockRepository,
        repository_type: 'rclone' as const,
        storage_backend: 'rclone' as const,
        path: '/data/rclone-cache/repositories/1',
        rclone_storage: {
          repository_id: 1,
          backend: 'rclone' as const,
          rclone_remote_id: 10,
          rclone_remote_name: 'local-test',
          rclone_remote_path: 'borg-ui/app',
          rclone_target: 'local-test:borg-ui/app',
          cache_path: '/data/rclone-cache/repositories/1',
          cache_present: true,
          sync_policy: 'after_success' as const,
          sync_status: 'current',
          last_synced_at: '2024-01-20T10:30:00Z',
        },
      }

      renderWithProviders(
        <RepositoryCard
          repository={rcloneRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          onRcloneSync={vi.fn()}
          onRcloneHydrate={vi.fn()}
        />
      )

      expect(screen.getByText('Synced')).toBeInTheDocument()
      expect(screen.getByText('local-test:borg-ui/app')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Sync cloud mirror/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Hydrate local cache/i })).toBeInTheDocument()
    })

    it('renders failed rclone sync state clearly', () => {
      const rcloneRepository = {
        ...mockRepository,
        repository_type: 'rclone' as const,
        storage_backend: 'rclone' as const,
        rclone_storage: {
          repository_id: 1,
          backend: 'rclone' as const,
          rclone_remote_id: 10,
          rclone_remote_name: 'local-test',
          rclone_remote_path: 'borg-ui/app',
          rclone_target: 'local-test:borg-ui/app',
          cache_present: true,
          sync_policy: 'manual' as const,
          sync_status: 'failed',
          last_sync_error: 'remote unavailable',
        },
      }

      renderWithProviders(
        <RepositoryCard
          repository={rcloneRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      expect(screen.getByText('Sync failed')).toBeInTheDocument()
    })

    it('renders managed-agent mirror sync status with agent state', () => {
      const agentMirrorRepository = {
        ...mockRepository,
        repository_type: 'local' as const,
        storage_backend: 'agent_local' as const,
        execution_target: 'agent' as const,
        executor_type: 'agent' as const,
        agent_machine_id: 101,
        agent_machine_name: 'workstation.local',
        agent_machine_status: 'offline',
        rclone_storage: {
          repository_id: 1,
          backend: 'rclone' as const,
          rclone_remote_id: 10,
          rclone_remote_name: 'prod-s3',
          rclone_remote_path: 'borg-ui/agent',
          rclone_target: 'prod-s3:borg-ui/agent',
          cache_path: null,
          cache_present: true,
          sync_direction: 'agent_to_remote',
          sync_policy: 'manual' as const,
          sync_status: 'pending',
          agent_machine_name: 'workstation.local',
          agent_machine_status: 'offline',
        },
      }

      renderWithProviders(
        <RepositoryCard
          repository={agentMirrorRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          onRcloneSync={vi.fn()}
          onRcloneHydrate={vi.fn()}
        />
      )

      expect(screen.getByText('Agent: workstation.local')).toBeInTheDocument()
      expect(screen.getByText('Offline')).toBeInTheDocument()
      expect(screen.getByText('Sync pending')).toBeInTheDocument()
      expect(screen.getByText('prod-s3:borg-ui/agent')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Hydrate local cache/i })).not.toBeInTheDocument()
    })
  })

  describe('Progress Display', () => {
    it('displays progress information when jobs are running', () => {
      const startTime = new Date('2024-01-20T10:00:00Z').toISOString()

      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
        checkJob: {
          id: 1,
          progress: 50,
          progress_message: 'Checking...',
          started_at: startTime,
        },
      })

      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Verify progress message is displayed
      expect(screen.getByText('Checking...')).toBeInTheDocument()
    })

    it('clears progress display when jobs are not running', () => {
      // Start with running jobs
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: true,
        checkJob: {
          id: 1,
          progress: 50,
          progress_message: 'Checking...',
          started_at: '2024-01-20T10:00:00Z',
        },
      })

      const { rerender } = renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Verify progress is showing
      expect(screen.getByText('Checking...')).toBeInTheDocument()

      // Jobs stop
      vi.spyOn(useMaintenanceJobsModule, 'useMaintenanceJobs').mockReturnValue({
        ...mockMaintenanceJobs,
        hasRunningJobs: false,
      })

      rerender(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Progress message should not be visible anymore
      expect(screen.queryByText('Checking...')).not.toBeInTheDocument()
    })
  })

  describe('Integration Tests', () => {
    it('renders complete card with all features for full mode admin view', () => {
      renderWithProviders(
        <RepositoryCard
          repository={mockRepository}
          isInJobsSet={false}
          canManageRepository={true}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
        />
      )

      // Header elements
      expect(screen.getByText('Test Repository')).toBeInTheDocument()
      expect(screen.getByText('/path/to/repo')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Edit/i })).toBeInTheDocument()

      // Stats
      expect(screen.getByText('25')).toBeInTheDocument()
      expect(screen.getByText('10.5 GB')).toBeInTheDocument()
      expect(screen.getByText('repokey')).toBeInTheDocument()
      expect(screen.getByText('LZ4 (Fast)')).toBeInTheDocument()
      expect(screen.getByText('2 paths')).toBeInTheDocument()

      // Action buttons
      expect(screen.getByRole('button', { name: /Info/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Check/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Compact/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Prune/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Legacy Backup/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Create Backup Plan/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /View Archives/i })).toBeInTheDocument()

      // Delete button (last one in list)
      const deleteButtons = screen.getAllByRole('button', { name: /Delete/i })
      expect(deleteButtons.length).toBeGreaterThan(0)
    })

    it('renders minimal view for observe mode non-admin', () => {
      const observeRepo = { ...mockRepository, mode: 'observe' as const }
      renderWithProviders(
        <RepositoryCard
          repository={observeRepo}
          isInJobsSet={false}
          canManageRepository={false}
          getCompressionLabel={mockGetCompressionLabel}
          {...mockCallbacks}
          canDo={() => false}
        />
      )

      // Header elements
      expect(screen.getByText('Test Repository')).toBeInTheDocument()
      expect(screen.getByText('Observe Only')).toBeInTheDocument()

      // No Edit button
      expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument()

      // No action buttons
      expect(screen.queryByRole('button', { name: /Info/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Backup Now/i })).not.toBeInTheDocument()
    })
  })
})
