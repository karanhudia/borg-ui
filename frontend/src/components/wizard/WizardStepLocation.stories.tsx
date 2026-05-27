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
    id: 3,
    name: 'local-test',
    provider: 'local',
    last_test_status: 'success',
  },
  {
    id: 4,
    name: 's3-archive',
    provider: 's3',
    last_test_status: 'success',
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

const rcloneStoryArgs = {
  mode: 'create' as const,
  data: {
    name: 'Cloud Mirror Repository',
    borgVersion: 2 as const,
    repositoryMode: 'full' as const,
    repositoryLocation: 'rclone' as const,
    executionTarget: 'local' as const,
    agentMachineId: '' as const,
    path: 'borg-ui/production',
    repoSshConnectionId: '' as const,
    bypassLock: false,
    rcloneRemoteId: 3,
    rcloneRemotePath: 'borg-ui/production',
    rcloneSyncPolicy: 'after_success' as const,
    rcloneExtraFlags: '--transfers 4',
  },
  sshConnections,
  agentMachines,
  rcloneRemotes,
  rcloneStatus: { available: true, version: 'rclone v1.66.0' },
  dataSource: 'local' as const,
  sourceSshConnectionId: '' as const,
  onChange: () => {},
  onBrowsePath: () => {},
  onAddRcloneRemote: () => {},
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
  args: {
    ...rcloneStoryArgs,
    data: {
      ...rcloneStoryArgs.data,
      name: 'Local Media Repository',
      borgVersion: 1,
      repositoryLocation: 'local',
      path: '/srv/borg/media',
      rcloneRemoteId: '',
      rcloneRemotePath: '',
      rcloneExtraFlags: '',
    },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const RcloneRepository: Story = {
  args: rcloneStoryArgs,
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const RcloneUnavailable: Story = {
  args: {
    ...rcloneStoryArgs,
    rcloneRemotes: [],
    rcloneStatus: { available: false, error: 'rclone binary was not found on PATH' },
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}

export const RcloneEmptyWithAddRemote: Story = {
  args: {
    ...rcloneStoryArgs,
    data: {
      ...rcloneStoryArgs.data,
      rcloneRemoteId: '',
      rcloneRemotePath: '',
    },
    rcloneRemotes: [],
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepLocation {...args} />
    </Box>
  ),
}
