import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentUninstallDialog from './AgentUninstallDialog'
import type { AgentMachineResponse } from '../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
  agent_version: '0.1.5',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-13T08:00:00.000Z',
} as AgentMachineResponse

const meta: Meta<typeof AgentUninstallDialog> = {
  title: 'Managed Agents/AgentUninstallDialog',
  component: AgentUninstallDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    agent,
    open: true,
    serverUrl: 'https://borg-ui.example.com',
    onCopy: () => {},
    onCancel: () => {},
  },
}
export default meta

type Story = StoryObj<typeof AgentUninstallDialog>

export const Default: Story = {}

export const Mobile: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
