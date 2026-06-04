import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ScheduleJobCard from './ScheduleJobCard'

const repositories = [
  {
    id: 1,
    name: 'External Drive Repository',
    path: '/mnt/external/borg',
  },
]

const baseJob = {
  id: 42,
  name: 'External drive maintenance',
  cron_expression: '0 21 * * *',
  timezone: 'UTC',
  repository: null,
  repository_id: 1,
  repository_ids: null,
  enabled: true,
  last_run: '2026-05-28T21:00:00.000Z',
  next_run: '2026-06-03T21:00:00.000Z',
  description: 'Back up, prune, and compact when the drive is connected.',
  run_prune_after: true,
  run_compact_after: true,
  prune_keep_hourly: 0,
  prune_keep_daily: 7,
  prune_keep_weekly: 4,
  prune_keep_monthly: 6,
  prune_keep_quarterly: 0,
  prune_keep_yearly: 1,
  last_prune: '2026-05-28T21:12:00.000Z',
  last_compact: '2026-05-28T21:18:00.000Z',
}

const noop = () => {}

const meta = {
  title: 'Components/ScheduleJobCard',
  component: ScheduleJobCard,
  parameters: {
    layout: 'centered',
  },
  args: {
    repositories,
    canManage: true,
    onEdit: noop,
    onDelete: noop,
    onDuplicate: noop,
    onRunNow: noop,
    onToggle: noop,
  },
  render: (args) => (
    <Box sx={{ width: 640, maxWidth: 'calc(100vw - 32px)' }}>
      <ScheduleJobCard {...args} />
    </Box>
  ),
} satisfies Meta<typeof ScheduleJobCard>

export default meta

type Story = StoryObj<typeof meta>

export const EnabledSchedule: Story = {
  args: {
    job: baseJob,
  },
}

export const DisabledManualRun: Story = {
  args: {
    job: {
      ...baseJob,
      enabled: false,
      next_run: null,
    },
  },
}

export const DisabledManualRunPending: Story = {
  args: {
    job: {
      ...baseJob,
      enabled: false,
      next_run: null,
    },
    isRunNowPending: true,
  },
}
