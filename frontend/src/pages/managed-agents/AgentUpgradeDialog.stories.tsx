import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentUpgradeDialog from './AgentUpgradeDialog'
import type { AgentMachineResponse } from '../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'online',
  agent_version: '0.1.2',
  available_agent_version: '0.1.3',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-09T08:00:00.000Z',
} as AgentMachineResponse

const meta: Meta<typeof AgentUpgradeDialog> = {
  title: 'Managed Agents/AgentUpgradeDialog',
  component: AgentUpgradeDialog,
  parameters: { layout: 'fullscreen' },
}
export default meta

type Story = StoryObj<typeof AgentUpgradeDialog>

export const Confirm: Story = {
  args: { open: true, agents: [agent], onConfirm: () => {}, onCancel: () => {} },
}

export const Pinned: Story = {
  args: {
    open: true,
    agents: [{ ...agent, desired_agent_version: '0.1.1' } as AgentMachineResponse],
    onConfirm: () => {},
    onCancel: () => {},
  },
}

export const Busy: Story = {
  args: { open: true, busy: true, agents: [agent], onConfirm: () => {}, onCancel: () => {} },
}

const fleet = [
  agent,
  { ...agent, id: 2, name: 'web-01', hostname: 'web-01.internal' },
  { ...agent, id: 3, name: 'mail-01', hostname: 'mail-01.internal' },
] as AgentMachineResponse[]

export const ManyEndpoints: Story = {
  args: { open: true, agents: fleet, onConfirm: () => {}, onCancel: () => {} },
}

export const MixedTargets: Story = {
  args: {
    open: true,
    agents: [
      agent,
      { ...agent, id: 2, name: 'web-01', desired_agent_version: '0.1.2' },
    ] as AgentMachineResponse[],
    onConfirm: () => {},
    onCancel: () => {},
  },
}
