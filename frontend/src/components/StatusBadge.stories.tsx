import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack } from '@mui/material'
import StatusBadge from './StatusBadge'

const meta = {
  title: 'Components/StatusBadge',
  component: StatusBadge,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Completed: Story = {
  args: { status: 'completed' },
}

export const CompletedWithWarnings: Story = {
  args: { status: 'completed_with_warnings' },
}

export const Failed: Story = {
  args: {
    status: 'failed',
    tooltip: 'Backup failed while writing archive metadata.',
  },
}

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

export const StatusComparison: Story = {
  args: { status: 'completed' },
  render: () => (
    <Stack spacing={1.5} sx={{ p: 3, minWidth: 260 }} alignItems="flex-start">
      <StatusBadge status="completed" />
      <StatusBadge status="completed_with_warnings" />
      <StatusBadge status="failed" tooltip="Backup failed while writing archive metadata." />
      <StatusBadge
        status="skipped"
        tooltip="The source was unavailable, so this availability check was skipped."
      />
    </Stack>
  ),
}
