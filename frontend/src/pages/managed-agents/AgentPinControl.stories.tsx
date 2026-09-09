import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentPinControl from './AgentPinControl'
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

const meta: Meta<typeof AgentPinControl> = {
  title: 'Managed Agents/AgentPinControl',
  component: AgentPinControl,
  parameters: { layout: 'fullscreen' },
}
export default meta

type Story = StoryObj<typeof AgentPinControl>

export const Unpinned: Story = {
  args: { open: true, agent, onSave: () => {}, onCancel: () => {} },
}

export const Pinned: Story = {
  args: {
    open: true,
    agent: {
      ...agent,
      desired_agent_version: '0.1.3',
      desired_borg_version: '2',
    } as AgentMachineResponse,
    onSave: () => {},
    onCancel: () => {},
  },
}
