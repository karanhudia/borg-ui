import type { ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ScheduledJobsTable from './ScheduledJobsTable'

type ScheduledJobsTableProps = ComponentProps<typeof ScheduledJobsTable>
type ScheduledJob = ScheduledJobsTableProps['jobs'][number]
type Repository = ScheduledJobsTableProps['repositories'][number]

const repositories: Repository[] = [
  { id: 1, name: 'Media archive', path: '/backups/media' },
  { id: 2, name: 'Photos archive', path: '/backups/photos' },
]

const jobs: ScheduledJob[] = [
  {
    id: 42,
    name: 'Primary server batch',
    cron_expression: '0 2 * * *',
    timezone: 'America/New_York',
    repository: null,
    repository_id: null,
    repository_ids: [1, 2],
    enabled: true,
    last_run: '2026-06-02T06:00:00Z',
    next_run: '2026-06-03T06:00:00Z',
    created_at: '2026-05-20T12:00:00Z',
    updated_at: '2026-06-01T12:00:00Z',
    description: 'Wake backup server, run repository backups, prune, compact, then power off.',
    archive_name_template: '{job_name}-{now}',
    run_repository_scripts: true,
    pre_backup_script_id: 7,
    post_backup_script_id: 8,
    run_prune_after: true,
    run_compact_after: true,
    prune_keep_hourly: 0,
    prune_keep_daily: 7,
    prune_keep_weekly: 4,
    prune_keep_monthly: 6,
    prune_keep_quarterly: 0,
    prune_keep_yearly: 1,
    last_prune: '2026-06-02T07:00:00Z',
    last_compact: '2026-06-02T07:10:00Z',
  },
]

const meta = {
  title: 'Components/ScheduledJobsTable',
  component: ScheduledJobsTable,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    jobs,
    repositories,
    isLoading: false,
    title: 'Legacy Repository Jobs',
    description:
      'Legacy repository jobs continue to run here for repositories with their own source paths. Use Backup Plans for new plan-owned backup workflows.',
    canManageJob: () => true,
    onEdit: () => {},
    onDelete: () => {},
    onDuplicate: () => {},
    onRunNow: () => {},
    onToggle: () => {},
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <ScheduledJobsTable {...args} />
    </Box>
  ),
} satisfies Meta<typeof ScheduledJobsTable>

export default meta

type Story = StoryObj<typeof meta>

export const LegacyRepositoryJobs: Story = {}

export const EmptyLegacyRepositoryJobs: Story = {
  args: {
    jobs: [],
  },
}
