import type { Meta, StoryObj } from '@storybook/react'
import AgentManualUpgradeChip from './AgentManualUpgradeChip'

const meta: Meta<typeof AgentManualUpgradeChip> = {
  title: 'Managed Agents/AgentManualUpgradeChip',
  component: AgentManualUpgradeChip,
}

export default meta
type Story = StoryObj<typeof AgentManualUpgradeChip>

export const ManualOnly: Story = {}

export const Mobile: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
