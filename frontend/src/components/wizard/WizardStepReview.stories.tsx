import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepReview, { type WizardReviewData } from './WizardStepReview'

const agentMachines = [
  {
    id: 7,
    name: 'Workstation',
    hostname: 'workstation.local',
    status: 'online',
  },
]

const managedAgentPlanSourcesData: WizardReviewData = {
  name: 'Pi Media Repository',
  borgVersion: 2,
  repositoryMode: 'full',
  repositoryLocation: 'ssh',
  executionTarget: 'agent',
  agentMachineId: 7,
  path: '/srv/borg/media',
  repoSshConnectionId: 1,
  dataSource: 'local',
  sourceSshConnectionId: '',
  sourceDirs: [],
  encryption: 'repokey-aes-ocb',
  passphrase: 'correct horse battery staple',
  compression: 'zstd,3',
  excludePatterns: [],
  customFlags: '',
  remotePath: '/usr/local/bin/borg2',
}

const meta = {
  title: 'Components/Wizard/Repository Review',
  component: WizardStepReview,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof WizardStepReview>

export default meta

type Story = StoryObj<typeof meta>

export const ManagedAgentPlanSources: Story = {
  args: {
    mode: 'create',
    data: managedAgentPlanSourcesData,
    sshConnections: [
      {
        id: 1,
        host: 'pi.local',
        username: 'backup',
        port: 22,
        ssh_key_id: 10,
        default_path: '/srv/borg',
      },
    ],
    agentMachines,
  },
  render: (args) => (
    <Box sx={{ width: 760, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepReview {...args} />
    </Box>
  ),
}
