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
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <BackupJobsTable {...args} />
    </Box>
  ),
}
