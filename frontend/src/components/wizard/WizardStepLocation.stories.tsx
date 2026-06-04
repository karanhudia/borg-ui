import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepLocation from './WizardStepLocation'

const sshConnections = [
  {
    id: 1,
    host: 'media-node.local',
    username: 'backup',
    port: 22,
    ssh_key_id: 10,
    default_path: '/srv/borg/repositories',
    mount_point: '/mnt/media-node',
    status: 'connected',
  },
]

const agentMachines = [
  {
    id: 7,
    name: 'Media Node',
    hostname: 'media-node.local',
    status: 'online',
  },
]

const rcloneRemotes = [
  {
    id: 10,
    name: 'prod-s3',
    provider: 's3',
    last_test_status: 'connected',
  },
]

const meta = {
  title: 'Components/Wizard/Repository Location',
  component: WizardStepLocation,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof WizardStepLocation>

export default meta

type Story = StoryObj<typeof meta>

const baseArgs = {
  mode: 'create' as const,
  data: {
    name: 'Local Media Repository',
    borgVersion: 1 as const,
    repositoryMode: 'full' as const,
    repositoryLocation: 'local' as const,
    executionTarget: 'local' as const,
    agentMachineId: '' as const,
    path: '/srv/borg/media',
    repoSshConnectionId: '' as const,
    bypassLock: false,
  },
  sshConnections,
  agentMachines,
  dataSource: 'local' as const,
  sourceSshConnectionId: '' as const,
  onChange: () => {},
  onBrowsePath: () => {},
}

export const AgentExecutionWithSshRepository: Story = {
  args: {
    mode: 'create',
    data: {
      name: 'Media Node Repository',
      borgVersion: 2,
      repositoryMode: 'full',
      repositoryLocation: 'local',
      executionTarget: 'agent',
      agentMachineId: 7,
      path: '/srv/borg/media',
      repoSshConnectionId: '',
      bypassLock: false,
    },
    sshConnections,
    agentMachines,
    dataSource: 'local',
    sourceSshConnectionId: '',
    onChange: () => {},
    onBrowsePath: () => {},
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const FilesystemDestinations: Story = {
  args: baseArgs,
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const SshDestination: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Remote Repository',
      repositoryLocation: 'ssh',
      repoSshConnectionId: 1,
      path: '/srv/borg/repositories/media',
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const DirectBorg2Rclone: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Direct Cloud Repository',
      borgVersion: 2,
      repositoryLocation: 'rclone',
      rcloneRemoteId: 10,
      rcloneRemotePath: 'borg-ui/direct',
      path: 'rclone://prod-s3/borg-ui/direct',
    },
    rcloneStatus: { available: true, version: 'rclone v1.66.0' },
    rcloneRemotes,
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const CommunityPlanLockedDestinations: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Community Repository',
      borgVersion: 2,
    },
    canUseManagedAgents: false,
    canUseRclone: false,
    rcloneStatus: { available: false, error: 'rclone repositories require Pro.' },
    rcloneRemotes,
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const AgentDestinationEmpty: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Agent Repository',
      executionTarget: 'agent',
      repositoryLocation: 'local',
    },
    agentMachines: [],
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const AgentDestinationMultiple: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Agent Repository',
      executionTarget: 'agent',
      repositoryLocation: 'local',
      agentMachineId: 7,
    },
    agentMachines: [
      { id: 7, name: 'Media Node', hostname: 'media-node.local', status: 'online' },
      { id: 8, name: 'Workstation', hostname: 'workstation.lan', status: 'online' },
      { id: 9, name: 'Laptop', hostname: 'laptop.lan', status: 'offline' },
    ],
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const SshDestinationNoConnections: Story = {
  args: {
    ...baseArgs,
    data: {
      ...baseArgs.data,
      name: 'Remote Repository',
      repositoryLocation: 'ssh',
    },
    sshConnections: [],
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}
