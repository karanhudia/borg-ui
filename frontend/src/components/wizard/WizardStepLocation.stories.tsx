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

const meta = {
  title: 'Components/Wizard/Repository Location',
  component: WizardStepLocation,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof WizardStepLocation>

export default meta

type Story = StoryObj<typeof meta>

export const AgentExecutionWithSshRepository: Story = {
  args: {
    mode: 'create',
    data: {
      name: 'Media Node Repository',
      borgVersion: 2,
      repositoryMode: 'full',
      repositoryLocation: 'ssh',
      executionTarget: 'agent',
      agentMachineId: 7,
      path: '/srv/borg/media',
      repoSshConnectionId: 1,
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
