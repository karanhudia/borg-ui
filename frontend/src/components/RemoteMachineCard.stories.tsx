import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { ComponentProps } from 'react'
import RemoteMachineCard from './RemoteMachineCard'

type RemoteMachine = ComponentProps<typeof RemoteMachineCard>['machine']

const machine: RemoteMachine = {
  id: 7,
  ssh_key_id: 3,
  ssh_key_name: 'System Backup Key',
  host: 'backup-host.internal',
  username: 'borg',
  port: 2222,
  use_sftp_mode: false,
  use_sudo: false,
  default_path: '/srv/backups',
  mount_point: 'backup-host',
  status: 'connected',
  last_test: '2026-06-03T16:52:00.000Z',
  last_success: '2026-06-03T16:52:00.000Z',
  storage: {
    total: 536870912000,
    total_formatted: '500 GB',
    used: 190589173760,
    used_formatted: '177.5 GB',
    available: 346281738240,
    available_formatted: '322.5 GB',
    percent_used: 35.5,
    last_check: '2026-06-03T17:00:00.000Z',
  },
  created_at: '2026-06-01T10:00:00.000Z',
}

const noop = () => {}

const meta = {
  title: 'Remote Machines/RemoteMachineCard',
  component: RemoteMachineCard,
  render: (args) => (
    <Box sx={{ width: 360, p: 2, bgcolor: 'background.default' }}>
      <RemoteMachineCard {...args} />
    </Box>
  ),
} satisfies Meta<typeof RemoteMachineCard>

export default meta

type Story = StoryObj<typeof meta>

export const WithRunDiagnostics: Story = {
  args: {
    machine,
    onEdit: noop,
    onDelete: noop,
    onRefreshStorage: noop,
    onTestConnection: noop,
    onDeployKey: noop,
    onRunDiagnostics: noop,
  },
}
