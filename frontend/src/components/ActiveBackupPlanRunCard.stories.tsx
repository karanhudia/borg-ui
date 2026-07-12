import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ActiveBackupPlanRunCard from './ActiveBackupPlanRunCard'
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

// An in-flight run in its POST-backup phase: the borg job has finished (so it
// carries no current file), and a post-backup agent hook is streaming its latest
// line. The activity ticker must show the live hook line, not a stale backup file.
const runWithLiveHook: BackupPlanRun = {
  id: 352,
  backup_plan_id: plan.id,
  trigger: 'manual',
  status: 'running',
  started_at: '2026-05-23T02:00:00Z',
  created_at: '2026-05-23T02:00:00Z',
  repositories: [
    {
      id: 421,
      repository_id: 31,
      status: 'completed',
      repository: {
        id: 31,
        name: 'Accounting repository',
        path: '/backups/accounting',
        borg_version: 2,
      },
      backup_job: {
        id: 911,
        repository_id: 31,
        repository: '/backups/accounting',
        type: 'backup',
        status: 'completed',
        started_at: '2026-05-23T02:01:00Z',
        completed_at: '2026-05-23T02:06:00Z',
        has_logs: true,
        execution_mode: 'agent',
        // No progress_details → getCurrentFile() returns null.
      },
    },
  ],
  script_executions: [
    {
      id: 5,
      script_id: null,
      script_name: 'sync-offsite',
      hook_type: 'post-backup',
      status: 'running',
      started_at: '2026-05-23T02:06:10Z',
      has_logs: true,
      current_line: 'rsync: transferring invoices-2026-05.tar.gz (4,812 files)',
    },
  ],
}

// Contrast: the borg job itself is running and reporting its current file — the
// activity ticker shows that file (no hook is running).
const runWithBackupInProgress: BackupPlanRun = {
  ...runWithLiveHook,
  id: 353,
  repositories: [
    {
      id: 422,
      repository_id: 31,
      status: 'running',
      repository: {
        id: 31,
        name: 'Accounting repository',
        path: '/backups/accounting',
        borg_version: 2,
      },
      backup_job: {
        id: 912,
        repository_id: 31,
        repository: '/backups/accounting',
        type: 'backup',
        status: 'running',
        started_at: '2026-05-23T02:01:00Z',
        has_logs: true,
        execution_mode: 'agent',
        progress_details: {
          original_size: 8_100_000_000,
          nfiles: 12_004,
          current_file: '/srv/accounting/ledgers/2026/invoices-2026-05.sqlite',
        },
      },
    },
  ],
  script_executions: [],
}

const meta = {
  title: 'Components/ActiveBackupPlanRunCard',
  component: ActiveBackupPlanRunCard,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    run: runWithLiveHook,
    plan,
    onCancel: () => {},
    onViewLogs: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <ActiveBackupPlanRunCard {...args} />
    </Box>
  ),
} satisfies Meta<typeof ActiveBackupPlanRunCard>

export default meta

type Story = StoryObj<typeof meta>

// The changed state: a running post-backup hook streams its latest line while the
// backup itself has finished, so the activity ticker shows the live hook output.
export const LiveHookActivity: Story = {}

// The other branch: a running borg job supplies the current file for the ticker.
export const BackupInProgress: Story = {
  args: {
    run: runWithBackupInProgress,
  },
}
