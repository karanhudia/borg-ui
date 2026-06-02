import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import BackupPlanRunsPanel from './BackupPlanRunsPanel'
import type { BackupPlan, BackupPlanRun } from '../types'

const plan: BackupPlan = {
  id: 44,
  name: 'Nightly accounting backup',
  enabled: true,
  source_type: 'local',
  source_directories: ['/srv/accounting'],
  exclude_patterns: ['*.tmp'],
  archive_name_template: '{hostname}-{now}',
  compression: 'zstd',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'stop',
  schedule_enabled: true,
  timezone: 'America/New_York',
  repository_count: 1,
}

const retryableRun: BackupPlanRun = {
  id: 340,
  backup_plan_id: plan.id,
  trigger: 'manual',
  status: 'failed',
  started_at: '2026-05-22T08:00:00Z',
  completed_at: '2026-05-22T08:06:00Z',
  created_at: '2026-05-22T08:00:00Z',
  repositories: [
    {
      id: 410,
      repository_id: 31,
      status: 'failed',
      error_message: 'Repository connection closed during archive finalization',
      repository: {
        id: 31,
        name: 'Accounting repository',
        path: '/backups/accounting',
        borg_version: 2,
      },
      backup_job: {
        id: 901,
        repository_id: 31,
        repository: '/backups/accounting',
        type: 'backup',
        status: 'failed',
        started_at: '2026-05-22T08:00:00Z',
        completed_at: '2026-05-22T08:06:00Z',
        has_logs: true,
        execution_mode: 'local',
      },
    },
  ],
}

const meta = {
  title: 'Components/BackupPlanRunsPanel',
  component: BackupPlanRunsPanel,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    plans: [plan],
    runs: [retryableRun],
    onCancel: () => {},
    onViewLogs: () => {},
    onRetry: () => {},
    canRetryRun: () => true,
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupPlanRunsPanel {...args} />
    </Box>
  ),
} satisfies Meta<typeof BackupPlanRunsPanel>

export default meta

type Story = StoryObj<typeof meta>

export const RetryableBackupPlanRun: Story = {}
