import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import McpAccessSection from './McpAccessSection'
import { McpStoryProviders } from '../mcp/storyProviders'
import { mcpConfig } from '../mcp/storyFixtures'

const meta = {
  title: 'Components/SystemSettings/McpAccessSection',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof McpAccessSection>
export default meta
type Story = StoryObj<typeof meta>

export const On: Story = {
  render: () => (
    <McpStoryProviders config={mcpConfig} connections={[]}>
      <Box sx={{ p: 3 }}>
        <McpAccessSection />
      </Box>
    </McpStoryProviders>
  ),
}
export const OffAndCapped: Story = {
  render: () => (
    <McpStoryProviders
      config={{ ...mcpConfig, enabled: false, max_access_level: 'read' }}
      connections={[]}
    >
      <Box sx={{ p: 3 }}>
        <McpAccessSection />
      </Box>
    </McpStoryProviders>
  ),
}
