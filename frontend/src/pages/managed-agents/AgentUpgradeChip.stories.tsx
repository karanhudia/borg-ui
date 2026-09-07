import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import AgentUpgradeChip from './AgentUpgradeChip'

const meta: Meta<typeof AgentUpgradeChip> = {
  title: 'Managed Agents/AgentUpgradeChip',
  component: AgentUpgradeChip,
}
export default meta

type Story = StoryObj<typeof AgentUpgradeChip>

export const AllStates: Story = {
  render: () => (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <AgentUpgradeChip status="up_to_date" targetVersion="0.1.3" />
      <AgentUpgradeChip status="outdated" targetVersion="0.1.3" />
      <AgentUpgradeChip status="ahead" targetVersion="0.1.3" />
      <AgentUpgradeChip status="pinned" pinnedVersion="0.1.2" />
      <AgentUpgradeChip status="unknown" />
    </Stack>
  ),
}

export const UpToDate: Story = {
  args: { status: 'up_to_date', targetVersion: '0.1.3' },
}

export const Outdated: Story = {
  args: { status: 'outdated', targetVersion: '0.1.3' },
}

export const Ahead: Story = {
  args: { status: 'ahead', targetVersion: '0.1.3' },
}

export const Pinned: Story = {
  args: { status: 'pinned', pinnedVersion: '0.1.2' },
}

export const Unknown: Story = {
  args: { status: 'unknown' },
}
