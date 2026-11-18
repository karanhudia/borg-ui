import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import McpTab from './McpTab'
import { McpStoryProviders, type McpStoryState } from './mcp/storyProviders'
import { connections, mcpConfig } from './mcp/storyFixtures'

const render = (state: McpStoryState) => (
  <McpStoryProviders {...state}>
    <Box sx={{ p: 3 }}>
      <McpTab />
    </Box>
  </McpStoryProviders>
)

const meta = {
  title: 'Settings/McpTab',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof McpTab>
export default meta
type Story = StoryObj<typeof meta>

export const WithConnections: Story = { render: () => render({ config: mcpConfig, connections }) }
export const Empty: Story = { render: () => render({ config: mcpConfig, connections: [] }) }
export const TurnedOff: Story = {
  render: () => render({ config: { ...mcpConfig, enabled: false }, connections }),
}
export const Viewer: Story = {
  render: () => render({ config: mcpConfig, connections: connections.slice(0, 1), role: 'viewer' }),
}
export const Community: Story = {
  render: () => render({ config: mcpConfig, connections, plan: 'community' }),
}
