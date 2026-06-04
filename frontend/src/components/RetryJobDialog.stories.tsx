import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RetryJobDialog from './RetryJobDialog'

const meta = {
  title: 'Components/RetryJobDialog',
  component: RetryJobDialog,
  parameters: {
    layout: 'centered',
  },
  args: {
    open: true,
    title: 'Retry backup job #201?',
    confirmLabel: 'Retry Job',
    onClose: () => {},
    onConfirm: () => {},
  },
  render: (args) => (
    <Box sx={{ width: 420, minHeight: 180 }}>
      <RetryJobDialog {...args} />
    </Box>
  ),
} satisfies Meta<typeof RetryJobDialog>

export default meta

type Story = StoryObj<typeof meta>

export const BackupJobRetry: Story = {}

export const BackupPlanRunRetry: Story = {
  args: {
    title: 'Retry backup plan run #340?',
    confirmLabel: 'Retry Run',
  },
}
