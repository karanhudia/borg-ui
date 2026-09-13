import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentSetServerDialog from './AgentSetServerDialog'
import type { AgentMachineResponse } from '../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
  agent_version: '0.1.5',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-12T08:00:00.000Z',
} as AgentMachineResponse

const meta: Meta<typeof AgentSetServerDialog> = {
  title: 'Managed Agents/AgentSetServerDialog',
  component: AgentSetServerDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    open: true,
    defaultServerUrl: 'http://192.168.1.82:8083',
    onCopy: () => {},
    onCancel: () => {},
  },
}
export default meta

type Story = StoryObj<typeof AgentSetServerDialog>

export const CurrentAgent: Story = { args: { agent } }

export const OlderAgent: Story = {
  args: { agent: { ...agent, agent_version: '0.1.4' } as AgentMachineResponse },
}

export const UnknownVersion: Story = {
  args: { agent: { ...agent, agent_version: null } as AgentMachineResponse },
}

export const Mobile: Story = {
  args: { agent },
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
