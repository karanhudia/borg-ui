import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import StatusBadge from './StatusBadge'

const meta = {
  title: 'Components/StatusBadge',
  component: StatusBadge,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Skipped: Story = {
  args: {
    status: 'skipped',
    tooltip: 'The source was unavailable, so this availability check was skipped.',
  },
  render: (args) => (
    <Box sx={{ p: 3 }}>
      <StatusBadge {...args} />
    </Box>
  ),
}
