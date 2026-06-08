import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { BackupPlansContent } from '../BackupPlansContent'
import type { BackupPlan, BackupPlanRun } from '../../../types'

const { mockTrack } = vi.hoisted(() => ({
  mockTrack: vi.fn(),
}))

vi.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track: mockTrack,
    EventCategory: { BACKUP: 'Backup' },
    EventAction: {
      VIEW: 'View',
      START: 'Start',
      STOP: 'Stop',
      EDIT: 'Edit',
      DELETE: 'Delete',
      SEARCH: 'Search',
      FILTER: 'Filter',
    },
  }),
}))

const theme = createTheme()

const t = ((
  key: string,
  options?: {
    defaultValue?: string
    count?: number
    id?: number
    name?: string
    feature?: string
    features?: string
  }
) => {
  const translations: Record<string, string> = {
    'backupPlans.title': 'Backup Plans',
    'backupPlans.subtitle': 'Define sources, settings, schedules, and repositories.',
    'backupPlans.loading': 'Loading backup plans...',
    'backupPlans.filters.linkedRepository': `Showing plans linked to ${
      options?.name ?? 'Repository'
    }`,
    'backupPlans.filters.clearRepository': 'Clear repository filter',
    'backupPlans.actions.create': 'Create Backup Plan',
    'backupPlans.actions.edit': 'Edit',
    'backupPlans.actions.viewRepositories': 'View repositories',
    'backupPlans.actions.history': 'History',
    'backupPlans.actions.delete': 'Delete',
    'backupPlans.actions.run': 'Run',
    'backupPlans.runsPanel.cancelRun': 'Cancel Run',
    'backupPlans.runsDialog.runNumber': `Run #${options?.id ?? 1}`,
    'backupPlans.runsPanel.repositoryProgress': 'Repository progress',
    'backupPlans.wizard.review.sources': 'Sources',
    'backupPlans.wizard.review.repositories': 'Repositories',
    'backupPlans.wizard.review.sourceLocation': 'Source location',
    'backupPlans.wizard.review.compression': 'Compression',
    'backupPlans.status.sourcePathCount': `${options?.count ?? 0} sources`,
    'backupPlans.status.repositoryCount': `${options?.count ?? 0} repositories`,
    'backupPlans.status.lastRunLabel': 'Last run',
    'backupPlans.status.nextRunLabel': 'Next run',
    'backupPlans.status.manualOnly': 'Manual only',
    'backupPlans.status.localSource': 'Local source',
    'backupPlans.status.remoteSource': 'Remote source',
    'backupPlans.status.pro': 'Pro',
    'backupPlans.status.proRequired': 'Pro required',
    'backupPlans.sourceChooser.managedAgent': 'Managed agent',
    'backupPlans.sourceChooser.databaseTitle': 'Database scan',
    'backupPlans.sourceChooser.kindContainer': 'Container',
    'backupPlans.runTooltipPro':
      'This plan uses a Pro-only feature. Edit it or upgrade to Pro to run it.',
    'backupPlans.runTooltipProFeature': `This plan uses ${
      options?.feature ?? 'a Pro-only feature'
    }, which requires Pro. Edit it or upgrade to Pro to run it.`,
    'backupPlans.runTooltipProFeatures': `This plan uses Pro-only features: ${
      options?.features ?? 'advanced backup features'
    }. Edit it or upgrade to Pro to run it.`,
    'backupPlans.proFeatureLabels.multiRepository': 'multiple repositories or parallel execution',
    'backupPlans.proFeatureLabels.managedAgent': 'managed-agent backups',
    'backupPlans.proFeatureLabels.database': 'database backups',
    'backupPlans.proFeatureLabels.container': 'container backups',
    'backupPlans.status.enabled': 'Enabled',
    'backupPlans.status.disabled': 'Disabled',
    'backupPlans.status.clickToEnable': 'Click to enable',
    'backupPlans.status.clickToDisable': 'Click to disable',
    'backup.runningJobs.progress.initializing': 'Initializing',
    'backup.runningJobs.progress.processing': 'Processing',
    'backup.runningJobs.progress.finalizing': 'Finalizing',
    'backup.runningJobs.progress.filesProcessed': 'Files processed',
    'backup.runningJobs.progress.originalSize': 'Original size',
    'backup.runningJobs.progress.speed': 'Speed',
    'backup.runningJobs.progress.eta': 'ETA',
    'common.never': 'Never',
  }

  return translations[key] ?? options?.defaultValue ?? key
}) as TFunction

const basePlan: BackupPlan = {
  id: 7,
  name: 'Daily Plan',
  description: 'Production data',
  enabled: true,
  source_type: 'local',
  source_directories: ['/srv/data'],
  exclude_patterns: [],
  archive_name_template: '{plan_name}-{repo_name}-{now}',
  compression: 'lz4',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'continue',
  schedule_enabled: false,
  timezone: 'UTC',
  repository_count: 1,
}

const activeRun: BackupPlanRun = {
  id: 99,
  backup_plan_id: 7,
  status: 'running',
  trigger: 'manual',
  started_at: '2026-05-15T10:00:00Z',
  completed_at: null,
  repositories: [
    {
      id: 101,
      repository_id: 11,
      status: 'running',
      started_at: '2026-05-15T10:00:00Z',
      completed_at: null,
      repository: { id: 11, name: 'Primary Repo', path: '/backups/primary' },
      backup_job: {
        id: 501,
        repository: '/backups/primary',
        repository_id: 11,
        status: 'running',
        started_at: '2026-05-15T10:00:00Z',
        progress: 25,
        has_logs: true,
        progress_details: {
          nfiles: 12,
          current_file: '/srv/data/file.db',
          original_size: 1024,
          total_expected_size: 4096,
          backup_speed: 2.5,
          estimated_time_remaining: 30,
        },
      },
    },
  ],
}

function renderContent(overrides: Partial<React.ComponentProps<typeof BackupPlansContent>> = {}) {
  const props: React.ComponentProps<typeof BackupPlansContent> = {
    loadingPlans: false,
    backupPlans: [basePlan],
    processedPlans: { groups: [{ name: null, plans: [basePlan] }] },
    latestRunByPlan: new Map(),
    backupPlanRuns: [],
    searchQuery: '',
    setSearchQuery: vi.fn(),
    sortBy: 'name-asc',
    setSortBy: vi.fn(),
    groupBy: 'none',
    setGroupBy: vi.fn(),
    repositoryFilter: null,
    onClearRepositoryFilter: vi.fn(),
    startingPlanId: null,
    highlightedPlanId: null,
    canUseMultiRepository: true,
    canUseManagedAgents: true,
    canUseDatabaseDiscovery: true,
    canUseContainerBackups: true,
    cancellingRunId: null,
    runPending: false,
    togglePending: false,
    toggleVariables: undefined,
    openCreateWizard: vi.fn(),
    onRunPlan: vi.fn(),
    onCancelRun: vi.fn(),
    onViewLogs: vi.fn(),
    onTogglePlan: vi.fn(),
    onEditPlan: vi.fn(),
    onDeletePlan: vi.fn(),
    onViewHistory: vi.fn(),
    onViewRepositories: vi.fn(),
    formatStatusLabel: (status) => status ?? 'unknown',
    t,
    ...overrides,
  }

  return render(
    <ThemeProvider theme={theme}>
      <BackupPlansContent {...props} />
    </ThemeProvider>
  )
}

describe('BackupPlansContent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders card skeletons while backup plans are loading', () => {
    const { container } = renderContent({
      loadingPlans: true,
      backupPlans: [],
      processedPlans: { groups: [] },
    })

    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    expect(screen.queryByText('Loading backup plans...')).not.toBeInTheDocument()
  })

  it('keeps search, sort, and group controls visible while backup plans are loading', () => {
    renderContent({
      loadingPlans: true,
      backupPlans: [],
      processedPlans: { groups: [] },
    })

    expect(screen.getByPlaceholderText('Search backup plans...')).toBeInTheDocument()
    expect(screen.getByText('Name A → Z')).toBeInTheDocument()
    expect(screen.getByText('No grouping')).toBeInTheDocument()
  })

  it('keeps the original plan card visible when the plan has an active run', () => {
    renderContent({
      latestRunByPlan: new Map([[basePlan.id, activeRun]]),
      backupPlanRuns: [activeRun],
    })

    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel Run' })).toBeInTheDocument()
  })

  it('calls the repository navigation action from a backup plan card', async () => {
    const onViewRepositories = vi.fn()

    renderContent({ onViewRepositories })

    fireEvent.click(screen.getByRole('button', { name: 'View repositories' }))

    expect(onViewRepositories).toHaveBeenCalledWith(basePlan.id)
  })

  it('tracks backup plan toolbar and card workflow analytics', async () => {
    renderContent()

    fireEvent.change(screen.getByPlaceholderText('Search backup plans...'), {
      target: { value: 'daily' },
    })
    expect(mockTrack).toHaveBeenCalledWith(
      'Backup',
      'Search',
      expect.objectContaining({
        entity: 'backup_plan',
        section: 'backup_plans',
        query_length: 5,
        result_count: 1,
      })
    )

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    expect(mockTrack).toHaveBeenCalledWith(
      'Backup',
      'Start',
      expect.objectContaining({
        entity: 'backup_plan',
        operation: 'run_plan',
        schedule_enabled: false,
      })
    )

    fireEvent.click(screen.getByRole('button', { name: 'View repositories' }))
    expect(mockTrack).toHaveBeenCalledWith(
      'Backup',
      'View',
      expect.objectContaining({
        entity: 'backup_plan',
        operation: 'view_linked_repositories',
        repository_count: 1,
      })
    )
  })

  it('shows and clears the linked repository filter context', async () => {
    const user = userEvent.setup()
    const onClearRepositoryFilter = vi.fn()

    renderContent({
      repositoryFilter: { id: 11, name: 'Primary Repo' },
      onClearRepositoryFilter,
    })

    expect(screen.getByRole('status')).toHaveTextContent('Showing plans linked to Primary Repo')

    await user.click(screen.getByRole('button', { name: 'Clear repository filter' }))

    expect(onClearRepositoryFilter).toHaveBeenCalledTimes(1)
  })

  it('labels managed-agent backup plan sources after save', () => {
    renderContent({
      backupPlans: [{ ...basePlan, source_type: 'agent' }],
      processedPlans: { groups: [{ name: null, plans: [{ ...basePlan, source_type: 'agent' }] }] },
    })

    expect(screen.getByText('Managed agent')).toBeInTheDocument()
  })

  it('disables managed-agent backup plan runs behind the Pro chip when unavailable', () => {
    const agentPlan: BackupPlan = {
      ...basePlan,
      source_type: 'agent',
      source_locations: [
        {
          source_type: 'agent',
          agent_machine_id: 42,
          paths: ['/home/borg/app-data'],
        },
      ],
    }
    const onRunPlan = vi.fn()

    renderContent({
      backupPlans: [agentPlan],
      processedPlans: { groups: [{ name: null, plans: [agentPlan] }] },
      canUseManagedAgents: false,
      onRunPlan,
    })

    expect(screen.getByText('Pro required')).toBeInTheDocument()
    expect(screen.getByText('Managed agent')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    expect(onRunPlan).not.toHaveBeenCalled()
  })

  it('disables database backup plan runs behind the Pro chip when unavailable', () => {
    const databasePlan: BackupPlan = {
      ...basePlan,
      database_template_id: 'postgres',
      source_locations: [
        {
          source_type: 'local',
          paths: ['/var/lib/postgresql/data'],
          database: {
            template_id: 'postgres',
            engine: 'PostgreSQL',
            display_name: 'Postgres',
            backup_strategy: 'pg_dump',
            capture_mode: 'dump',
            backup_paths: ['/tmp/postgres.sql'],
            script_execution_target: 'source',
          },
        },
      ],
    }
    const onRunPlan = vi.fn()

    renderContent({
      backupPlans: [databasePlan],
      processedPlans: { groups: [{ name: null, plans: [databasePlan] }] },
      canUseDatabaseDiscovery: false,
      onRunPlan,
    })

    expect(screen.getByText('Pro required')).toBeInTheDocument()
    expect(screen.getByText('Database scan')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    expect(onRunPlan).not.toHaveBeenCalled()
  })

  it('disables container backup plan runs behind the Pro chip when unavailable', () => {
    const containerPlan: BackupPlan = {
      ...basePlan,
      source_locations: [
        {
          source_type: 'local',
          paths: ['/tmp/borg-ui/container-exports/redis.tar'],
          container: {
            container_name: 'redis',
            display_name: 'Redis',
            image: 'redis:7',
            backup_mode: 'export',
            export_path: '/tmp/borg-ui/container-exports/redis.tar',
            script_execution_target: 'source',
          },
        },
      ],
    }

    renderContent({
      backupPlans: [containerPlan],
      processedPlans: { groups: [{ name: null, plans: [containerPlan] }] },
      canUseContainerBackups: false,
    })

    expect(screen.getByText('Pro required')).toBeInTheDocument()
    expect(screen.getByText('Container')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled()
  })
})
