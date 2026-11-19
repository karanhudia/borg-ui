import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { Box } from '@mui/material'
import McpConnectionsList from './McpConnectionsList'
import { connections } from './storyFixtures'

const meta: Meta<typeof McpConnectionsList> = {
  title: 'MCP/McpConnectionsList',
  component: McpConnectionsList,
  args: { connections, showOwner: false, onEdit: fn(), onRevoke: fn(), onOpenActivity: fn() },
  decorators: [
    (Story) => (
      <Box sx={{ maxWidth: 900 }}>
        <Story />
      </Box>
    ),
  ],
}
export default meta
type Story = StoryObj<typeof McpConnectionsList>

export const Rows: Story = {}
export const Empty: Story = { args: { connections: [] } }
export const AdminWithOwners: Story = { args: { showOwner: true } }
export const TurnedOff: Story = { args: { editDisabled: true } }
