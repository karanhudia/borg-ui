import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import AgentBorgVersionChip from './AgentBorgVersionChip'

const meta: Meta<typeof AgentBorgVersionChip> = {
  title: 'Managed Agents/AgentBorgVersionChip',
  component: AgentBorgVersionChip,
}
export default meta

type Story = StoryObj<typeof AgentBorgVersionChip>

export const BothStates: Story = {
  render: () => (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: 1 }]} />
      <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: 1 }, { major: 2 }]} />
    </Stack>
  ),
}

export const Pending: Story = {
  args: { desiredBorgVersion: '2', borgVersions: [{ major: 1, version: '1.4.0' }] },
}

export const Active: Story = {
  args: {
    desiredBorgVersion: '2',
    borgVersions: [{ major: 2, version: '2.0.0b14' }],
  },
}
