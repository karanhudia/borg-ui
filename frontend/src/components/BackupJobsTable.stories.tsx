import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import BackupJobsTable from './BackupJobsTable'
import type { Job } from '../types/jobs'

const jobs: Job[] = [
  {
    id: 101,
    repository: '/backups/server',
    repository_path: '/backups/server',
    type: 'backup',
    status: 'completed',
    started_at: '2026-05-22T08:00:00Z',
    completed_at: '2026-05-22T08:07:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
  },
  {
    id: 102,
    repository: '/repos/remote-direct',
    repository_path: '/repos/remote-direct',
    type: 'backup',
    status: 'running',
    progress: 42,
    started_at: '2026-05-22T08:15:00Z',
    triggered_by: 'backup_plan',
    backup_plan_id: 12,
    backup_plan_name: 'Docker volumes',
    execution_mode: 'remote_ssh',
    route_strategy: 'remote_direct',
  },
  {
    id: 103,
    repository_id: 3,
    repository: '/agent/repo',
    repository_path: '/agent/repo',
    type: 'backup',
    status: 'failed',
    started_at: '2026-05-22T07:30:00Z',
    completed_at: '2026-05-22T07:35:00Z',
    triggered_by: 'schedule',
    scheduled_job_id: 8,
    execution_mode: 'agent',
    error_message:
      'LOCK_ERROR::/agent/repo\n[Exit Code 73] Failed to create/acquire the lock (timeout)',
  },
]

const retryableFailedBackupJobs: Job[] = [
  {
    id: 201,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    repository_id: 31,
    type: 'backup',
    status: 'failed',
    started_at: '2026-05-22T09:00:00Z',
    completed_at: '2026-05-22T09:04:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
    has_logs: true,
    error_message: 'Connection closed while writing archive metadata',
  },
]

const nonRetryableDestructiveJobs: Job[] = [
  {
    id: 202,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    repository_id: 31,
    type: 'prune',
    status: 'failed',
    started_at: '2026-05-22T09:20:00Z',
    completed_at: '2026-05-22T09:22:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
    has_logs: true,
    error_message: 'Retention pass stopped after partial repository scan',
  },
]

const availabilityCheckJobs: Job[] = [
  {
    id: 203,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    repository_id: 31,
    type: 'availability_check',
    status: 'skipped',
    skip_reason: 'source_unavailable',
    started_at: '2026-05-22T09:30:00Z',
    completed_at: '2026-05-22T09:30:00Z',
    triggered_by: 'schedule',
    execution_mode: 'local',
    error_message: 'SSH source unavailable for accounting source',
  },
]

const statusComparisonJobs: Job[] = [
  {
    id: 301,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    type: 'backup',
    status: 'completed',
    started_at: '2026-05-22T08:00:00Z',
    completed_at: '2026-05-22T08:07:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
  },
  {
    id: 302,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    type: 'backup',
    status: 'completed_with_warnings',
    started_at: '2026-05-22T08:15:00Z',
    completed_at: '2026-05-22T08:22:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
  },
  {
    id: 303,
    repository: '/backups/accounting',
    repository_path: '/backups/accounting',
    type: 'backup',
    status: 'failed',
    started_at: '2026-05-22T08:30:00Z',
    completed_at: '2026-05-22T08:31:00Z',
    triggered_by: 'manual',
    execution_mode: 'local',
    error_message: 'Archive finalization failed',
  },
  availabilityCheckJobs[0],
]

const meta = {
  title: 'Components/BackupJobsTable',
  component: BackupJobsTable,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof BackupJobsTable>

export default meta

type Story = StoryObj<typeof meta>

export const TransportModes: Story = {
  args: {
    jobs,
    showTriggerColumn: true,
    actions: { breakLock: true },
    canBreakLocks: (job) => job.repository_id === 3,
    lockBreakingEnabled: true,
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

const prunedArchiveJobs: Job[] = [
  {
    id: 301,
    repository: '/backups/server',
    repository_path: '/backups/server',
    type: 'backup',
    status: 'completed',
    started_at: '2026-05-20T02:00:00Z',
    completed_at: '2026-05-20T02:06:00Z',
    triggered_by: 'schedule',
    scheduled_job_id: 8,
    execution_mode: 'local',
    archive_name: 'server-2026-05-20T02:00',
    // the nightly prune removed this archive two days later
    archive_pruned_at: '2026-05-22T03:00:00Z',
  },
  {
    id: 302,
    repository: '/backups/server',
    repository_path: '/backups/server',
    type: 'backup',
    status: 'completed',
    started_at: '2026-05-22T02:00:00Z',
    completed_at: '2026-05-22T02:05:00Z',
    triggered_by: 'schedule',
    scheduled_job_id: 8,
    execution_mode: 'local',
    archive_name: 'server-2026-05-22T02:00',
  },
]

/** A run whose archive was pruned keeps its row; "View Archive" stays but is disabled. */
export const PrunedArchive: Story = {
  args: {
    jobs: prunedArchiveJobs,
    showTriggerColumn: true,
    actions: { viewArchive: true },
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

export const RetryableFailedBackupJob: Story = {
  args: {
    jobs: retryableFailedBackupJobs,
    showTypeColumn: true,
    showTriggerColumn: true,
    actions: {
      retry: true,
      viewLogs: true,
    },
    canRetryJob: () => true,
    onRetryJob: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

export const NonRetryableDestructiveJob: Story = {
  args: {
    jobs: nonRetryableDestructiveJobs,
    showTypeColumn: true,
    showTriggerColumn: true,
    actions: {
      retry: true,
      viewLogs: true,
    },
    canRetryJob: () => true,
    onRetryJob: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

export const AvailabilityCheckSkipped: Story = {
  args: {
    jobs: availabilityCheckJobs,
    showTypeColumn: true,
    showTriggerColumn: true,
    actions: { runNow: true, delete: true },
    onRunNow: () => {},
    canDeleteJobs: true,
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

export const StatusComparison: Story = {
  args: {
    jobs: statusComparisonJobs,
    showTypeColumn: true,
    showTriggerColumn: true,
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}

// A run whose follow-up chain rides under the row, which is where DataTable's
// sub-row hook is used: a desktop table row and a mobile card both mount it.
const runWithFollowups: Job[] = [
  {
    id: 301,
    repository_id: 4,
    repository: '/backups/nas',
    repository_path: '/backups/nas',
    type: 'backup',
    kind: 'backup',
    category: 'backup',
    trigger: 'plan',
    status: 'completed',
    started_at: '2026-09-05T02:00:00Z',
    completed_at: '2026-09-05T02:12:00Z',
    triggered_by: 'backup_plan',
    execution_mode: 'local',
    followups: [
      { id: 302, type: 'operation', kind: 'archive_sync', status: 'completed' },
      { id: 303, type: 'operation', kind: 'history_merge', status: 'completed' },
      {
        id: 304,
        type: 'operation',
        kind: 'history_index',
        status: 'running',
        progress_current: 14,
        progress_total: 38,
      },
    ],
  },
]

export const RunWithFollowups: Story = {
  args: {
    jobs: runWithFollowups,
    showTypeColumn: true,
    showTriggerColumn: true,
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}
