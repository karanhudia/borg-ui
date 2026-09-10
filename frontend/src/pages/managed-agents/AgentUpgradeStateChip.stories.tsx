import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import AgentUpgradeStateChip from './AgentUpgradeStateChip'

const meta: Meta<typeof AgentUpgradeStateChip> = {
  title: 'Managed Agents/AgentUpgradeStateChip',
  component: AgentUpgradeStateChip,
}
export default meta

type Story = StoryObj<typeof AgentUpgradeStateChip>

export const AllStates: Story = {
  render: () => (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <AgentUpgradeStateChip state="queued" targetVersion="0.1.3" />
      <AgentUpgradeStateChip state="requested" targetVersion="0.1.3" />
      <AgentUpgradeStateChip state="failed" error="The endpoint did not come back." />
    </Stack>
  ),
}

export const Queued: Story = {
  args: { state: 'queued', targetVersion: '0.1.3' },
}

export const Upgrading: Story = {
  args: { state: 'requested', targetVersion: '0.1.3' },
}

export const Failed: Story = {
  args: {
    state: 'failed',
    error: 'The endpoint did not come back on the target version in time.',
  },
}
