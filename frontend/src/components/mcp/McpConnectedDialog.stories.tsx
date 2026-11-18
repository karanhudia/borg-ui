import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import McpConnectedDialog from './McpConnectedDialog'

const meta: Meta<typeof McpConnectedDialog> = {
  title: 'MCP/McpConnectedDialog',
  component: McpConnectedDialog,
  args: {
    open: true,
    token: 'borgui_EXAMPLEtokenEXAMPLEtokenEXAMPLEtoken',
    endpointUrl: 'https://backups.example.com/mcp',
    onClose: fn(),
  },
}
export default meta
type Story = StoryObj<typeof McpConnectedDialog>

export const Default: Story = {}
export const UnderBasePath: Story = { args: { endpointUrl: 'https://example.com/borg/mcp' } }
