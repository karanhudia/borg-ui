import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentBulkUpgradeBar from './AgentBulkUpgradeBar'

const meta: Meta<typeof AgentBulkUpgradeBar> = {
  title: 'Managed Agents/AgentBulkUpgradeBar',
  component: AgentBulkUpgradeBar,
}
export default meta

type Story = StoryObj<typeof AgentBulkUpgradeBar>

export const OneSelected: Story = {
  args: { count: 1, onUpgrade: () => {}, onClear: () => {} },
}

export const ManySelected: Story = {
  args: { count: 7, onUpgrade: () => {}, onClear: () => {} },
}

export const Busy: Story = {
  args: { count: 7, busy: true, onUpgrade: () => {}, onClear: () => {} },
}
