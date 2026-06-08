import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import i18next from 'i18next'
import type { TFunction } from 'i18next'

import type { BackupPlan } from '../../types'
import { BackupPlansContent } from './BackupPlansContent'

const t = i18next.t.bind(i18next) as TFunction
const noop = () => {}

const databasePlan: BackupPlan = {
  id: 101,
  name: 'Postgres Nightly Dump',
  description: 'Database dump captured from the production host.',
  enabled: true,
  source_type: 'local',
  source_directories: ['/var/lib/postgresql/data'],
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
        backup_paths: ['/tmp/borg-ui/postgres.sql'],
        script_execution_target: 'source',
      },
    },
  ],
  exclude_patterns: [],
  database_template_id: 'postgres',
  archive_name_template: '{plan_name}-{repo_name}-{now}',
  compression: 'zstd,6',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'continue',
  schedule_enabled: true,
  cron_expression: '0 2 * * *',
  timezone: 'UTC',
  next_run: '2026-06-09T02:00:00.000Z',
  repository_count: 1,
}

const containerPlan: BackupPlan = {
  id: 102,
  name: 'Redis Container Export',
  description: 'Container filesystem export before nightly maintenance.',
  enabled: true,
  source_type: 'local',
  source_directories: ['/tmp/borg-ui/container-exports/redis.tar'],
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

const multiRepositoryPlan: BackupPlan = {
  id: 103,
  name: 'App Files To Two Repositories',
  description: 'Local application files replicated to primary and offsite repositories.',
  enabled: true,
  source_type: 'local',
  source_directories: ['/srv/app', '/etc/borg-ui'],
  exclude_patterns: ['node_modules', '*.tmp'],
  archive_name_template: '{plan_name}-{repo_name}-{now}',
  compression: 'lz4',
  repository_run_mode: 'parallel',
  max_parallel_repositories: 2,
  failure_behavior: 'continue',
  schedule_enabled: true,
  cron_expression: '30 1 * * *',
  timezone: 'UTC',
  next_run: '2026-06-09T01:30:00.000Z',
  repository_count: 2,
}

const managedAgentPlan: BackupPlan = {
  id: 104,
  name: 'Laptop Agent Backup',
  description: 'Back up developer laptop paths through an enrolled managed agent.',
  enabled: true,
  source_type: 'agent',
  source_directories: ['/Users/karan/Documents'],
  source_locations: [
    {
      source_type: 'agent',
      agent_machine_id: 42,
      paths: ['/Users/karan/Documents'],
    },
  ],
  exclude_patterns: ['Library/Caches'],
  archive_name_template: '{plan_name}-{repo_name}-{now}',
  compression: 'lz4',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'continue',
  schedule_enabled: true,
  cron_expression: '0 3 * * 1-5',
  timezone: 'UTC',
  next_run: '2026-06-09T03:00:00.000Z',
  repository_count: 1,
}

const lockedPlans = [databasePlan, containerPlan, multiRepositoryPlan, managedAgentPlan]

function CommunityLockedBackupPlans() {
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('name-asc')
  const [groupBy, setGroupBy] = useState('none')

  return (
    <Box sx={{ p: 3, maxWidth: 1120, mx: 'auto' }}>
      <BackupPlansContent
        loadingPlans={false}
        backupPlans={lockedPlans}
        processedPlans={{ groups: [{ name: null, plans: lockedPlans }] }}
        latestRunByPlan={new Map()}
        backupPlanRuns={[]}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        sortBy={sortBy}
        setSortBy={setSortBy}
        groupBy={groupBy}
        setGroupBy={setGroupBy}
        repositoryFilter={null}
        onClearRepositoryFilter={noop}
        startingPlanId={null}
        highlightedPlanId={null}
        canUseMultiRepository={false}
        canUseManagedAgents={false}
        canUseDatabaseDiscovery={false}
        canUseContainerBackups={false}
        cancellingRunId={null}
        runPending={false}
        togglePending={false}
        toggleVariables={undefined}
        openCreateWizard={noop}
        onRunPlan={noop}
        onCancelRun={noop}
        onViewLogs={noop}
        onTogglePlan={noop}
        onEditPlan={noop}
        onDeletePlan={noop}
        onViewHistory={noop}
        onViewRepositories={noop}
        formatStatusLabel={(status) => status ?? t('backupPlans.statuses.unknown')}
        t={t}
      />
    </Box>
  )
}

const meta = {
  title: 'Pages/Backup Plans/Content',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const CommunityLockedRuns: Story = {
  render: () => <CommunityLockedBackupPlans />,
}
