import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { ComponentProps } from 'react'
import { fn } from 'storybook/test'
import { CapabilityLaunchpad } from './CapabilityLaunchpad'
import { makeT, TokenContext } from './tokens'
import type { DashboardOverview } from './types'

type Summary = DashboardOverview['summary']
type Repositories = DashboardOverview['repository_health']
type LaunchpadArgs = ComponentProps<typeof CapabilityLaunchpad>

const T = makeT(true)
const handlers = {
  onNavigate: fn(),
}

const summary: Summary = {
  total_repositories: 3,
  local_repositories: 1,
  ssh_repositories: 2,
  active_schedules: 1,
  total_schedules: 2,
  active_backup_plans: 2,
  total_backup_plans: 3,
  active_automations: 3,
  total_automations: 4,
  success_rate_30d: 94,
  successful_jobs_30d: 31,
  failed_jobs_30d: 2,
  total_jobs_30d: 33,
}

const repositories: Repositories = [
  {
    id: 1,
    name: 'Documents',
    type: 'local',
    mode: 'full',
    last_backup: '2026-06-05T10:00:00.000Z',
    last_check: '2026-06-05T10:30:00.000Z',
    last_compact: '2026-06-01T10:00:00.000Z',
    last_restore_check: '2026-06-04T10:00:00.000Z',
    archive_count: 42,
    total_size: '248 GB',
    health_status: 'healthy',
    warnings: [],
    next_run: null,
    has_schedule: true,
    schedule_enabled: true,
    schedule_name: 'Nightly',
    backup_plan_count: 1,
    backup_plan_scheduled_count: 1,
    backup_plan_names: ['Nightly Documents'],
    backup_plan_next_run: '2026-06-06T03:00:00.000Z',
    restore_check_configured: true,
    latest_restore_check_status: 'completed',
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'healthy',
      compact: 'healthy',
      restore: 'healthy',
    },
  },
  {
    id: 2,
    name: 'NAS Offsite',
    type: 'ssh',
    mode: 'full',
    last_backup: '2026-06-05T11:00:00.000Z',
    last_check: null,
    last_compact: null,
    last_restore_check: null,
    archive_count: 12,
    total_size: '1.1 TB',
    health_status: 'warning',
    warnings: ['Restore check is not configured'],
    next_run: null,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    backup_plan_count: 1,
    backup_plan_scheduled_count: 0,
    backup_plan_names: ['Media Offsite'],
    backup_plan_next_run: null,
    restore_check_configured: false,
    latest_restore_check_status: null,
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'unknown',
      compact: 'unknown',
      restore: 'unknown',
    },
  },
  {
    id: 3,
    name: 'Imported Provider',
    type: 'rclone',
    mode: 'observe',
    last_backup: null,
    last_check: '2026-06-03T10:00:00.000Z',
    last_compact: null,
    last_restore_check: '2026-06-03T11:00:00.000Z',
    archive_count: 78,
    total_size: '624 GB',
    health_status: 'healthy',
    warnings: [],
    next_run: null,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    backup_plan_count: 0,
    backup_plan_scheduled_count: 0,
    backup_plan_names: [],
    backup_plan_next_run: null,
    restore_check_configured: true,
    latest_restore_check_status: 'completed',
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'healthy',
      compact: 'unknown',
      restore: 'healthy',
    },
  },
]

const meta = {
  title: 'Pages/DashboardV3/CapabilityLaunchpad',
  component: CapabilityLaunchpad,
  parameters: {
    layout: 'centered',
    backgrounds: {
      default: 'Dashboard dark',
      values: [{ name: 'Dashboard dark', value: '#111827' }],
    },
  },
} satisfies Meta<typeof CapabilityLaunchpad>

export default meta

type Story = StoryObj<typeof meta>

function renderLaunchpad(args: LaunchpadArgs) {
  return (
    <TokenContext.Provider value={T}>
      <Box sx={{ width: 232, maxWidth: 'calc(100vw - 32px)', color: T.textPrimary }}>
        <CapabilityLaunchpad {...args} />
      </Box>
    </TokenContext.Provider>
  )
}

export const MixedAdoption: Story = {
  args: {
    summary,
    repositories,
    cloudRemoteCount: 2,
    remoteClientCount: 1,
    ...handlers,
  },
  render: renderLaunchpad,
}

export const EmptyStart: Story = {
  args: {
    summary: {
      ...summary,
      total_repositories: 0,
      local_repositories: 0,
      ssh_repositories: 0,
      active_schedules: 0,
      total_schedules: 0,
      active_backup_plans: 0,
      total_backup_plans: 0,
      active_automations: 0,
      total_automations: 0,
    },
    repositories: [],
    cloudRemoteCount: 0,
    remoteClientCount: 0,
    ...handlers,
  },
  render: renderLaunchpad,
}
