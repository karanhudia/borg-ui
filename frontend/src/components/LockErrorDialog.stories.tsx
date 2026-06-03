import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import LockErrorDialog from './LockErrorDialog'

const noop = () => {}

const meta = {
  title: 'Components/LockErrorDialog',
  component: LockErrorDialog,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    open: true,
    repositoryId: 42,
    repositoryName: 'Production Archive',
    borgVersion: 2,
    onClose: noop,
    onLockBroken: noop,
  },
  render: (args) => (
    <Box sx={{ minHeight: 620 }}>
      <LockErrorDialog {...args} />
    </Box>
  ),
} satisfies Meta<typeof LockErrorDialog>

export default meta

type Story = StoryObj<typeof meta>

export const BreakLockAvailable: Story = {
  args: {
    canBreakLock: true,
    lockBreakingEnabled: true,
  },
}

export const LockBreakingDisabled: Story = {
  args: {
    canBreakLock: true,
    lockBreakingEnabled: false,
  },
}

export const MaintenanceRequired: Story = {
  args: {
    canBreakLock: false,
    lockBreakingEnabled: true,
  },
}
