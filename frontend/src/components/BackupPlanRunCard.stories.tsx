import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { BackupPlanRunCard } from './BackupPlanRunsPanel'
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

// A completed run whose pre/post script hooks are surfaced in the "Plan scripts"
// section: two agent pre-backup hooks that succeeded (with exit codes) and a
// post-backup hook that failed (with its error message).
const runWithScriptExecutions: BackupPlanRun = {
  id: 351,
  backup_plan_id: plan.id,
  trigger: 'manual',
  status: 'completed_with_warnings',
  started_at: '2026-05-23T02:00:00Z',
  completed_at: '2026-05-23T02:06:12Z',
  created_at: '2026-05-23T02:00:00Z',
  repositories: [
    {
      id: 420,
      repository_id: 31,
      status: 'completed',
      repository: {
        id: 31,
        name: 'Accounting repository',
        path: '/backups/accounting',
        borg_version: 2,
      },
      backup_job: {
        id: 910,
        repository_id: 31,
        repository: '/backups/accounting',
        type: 'backup',
        status: 'completed',
        started_at: '2026-05-23T02:01:00Z',
        completed_at: '2026-05-23T02:06:00Z',
        has_logs: true,
        execution_mode: 'agent',
      },
    },
  ],
  script_executions: [
    {
      id: 1,
      script_id: null,
      script_name: 'backup-cluster-mariadb',
      hook_type: 'pre-backup',
      status: 'completed',
      started_at: '2026-05-23T02:00:00Z',
      completed_at: '2026-05-23T02:00:54Z',
      execution_time: 53.94,
      exit_code: 0,
      has_logs: true,
    },
    {
      id: 2,
      script_id: null,
      script_name: 'backup-cluster-postgres',
      hook_type: 'pre-backup',
      status: 'completed',
      started_at: '2026-05-23T02:00:54Z',
      completed_at: '2026-05-23T02:01:00Z',
      execution_time: 6.2,
      exit_code: 0,
      has_logs: true,
    },
    {
      id: 3,
      script_id: 77,
      script_name: 'notify-webhook',
      hook_type: 'post-backup',
      status: 'failed',
      started_at: '2026-05-23T02:06:00Z',
      completed_at: '2026-05-23T02:06:12Z',
      execution_time: 12.0,
      exit_code: 2,
      error_message: 'Webhook returned HTTP 503',
      has_logs: true,
    },
  ],
}

const meta = {
  title: 'Components/BackupPlanRunCard',
  component: BackupPlanRunCard,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    run: runWithScriptExecutions,
    plan,
    onCancel: () => {},
    onViewLogs: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <BackupPlanRunCard {...args} />
    </Box>
  ),
} satisfies Meta<typeof BackupPlanRunCard>

export default meta

type Story = StoryObj<typeof meta>

// Detailed run card with the "Plan scripts" section: completed agent hooks (with
// exit codes) and a failed hook showing its error.
export const WithScriptExecutions: Story = {}
