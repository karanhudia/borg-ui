import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { BackupPlansContent } from '../BackupPlansContent'
import type { BackupPlan, BackupPlanRun } from '../../../types'

const theme = createTheme()

const t = ((key: string, options?: { defaultValue?: string; count?: number; id?: number }) => {
  const translations: Record<string, string> = {
    'backupPlans.title': 'Backup Plans',
    'backupPlans.subtitle': 'Define sources, settings, schedules, and repositories.',
    'backupPlans.loading': 'Loading backup plans...',
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
    isDark: false,
    startingPlanId: null,
    highlightedPlanId: null,
    canUseMultiRepository: true,
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
    const user = userEvent.setup()
    const onViewRepositories = vi.fn()

    renderContent({ onViewRepositories })

    await user.click(screen.getByRole('button', { name: 'View repositories' }))

    expect(onViewRepositories).toHaveBeenCalledWith(basePlan.id)
  })
})
