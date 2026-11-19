import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import McpConnectionDialog from './McpConnectionDialog'
import { connection, mcpConfig } from './storyFixtures'

const meta: Meta<typeof McpConnectionDialog> = {
  title: 'MCP/McpConnectionDialog',
  component: McpConnectionDialog,
  args: { open: true, config: mcpConfig, onClose: fn(), onSubmit: fn(async () => {}) },
}
export default meta
type Story = StoryObj<typeof McpConnectionDialog>

export const Create: Story = { args: { mode: 'create' } }
export const Edit: Story = { args: { mode: 'edit', connection: connection() } }
export const BackendError: Story = {
  args: {
    mode: 'edit',
    connection: connection(),
    onSubmit: async () => {
      throw new Error('Your administrator allows MCP connections up to read access.')
    },
  },
}
