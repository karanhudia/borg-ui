import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ComponentProps } from 'react'
import { Box } from '@mui/material'
import RcloneRemoteDialog from './RcloneRemoteDialog'

const meta = {
  title: 'Components/Wizard/Rclone Remote Dialog',
  component: RcloneRemoteDialog,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RcloneRemoteDialog>

export default meta

type Story = StoryObj<typeof meta>

const renderDialog = (args: ComponentProps<typeof RcloneRemoteDialog>) => (
  <Box sx={{ width: 720, minHeight: 620 }}>
    <RcloneRemoteDialog {...args} disablePortal />
  </Box>
)

export const CreateManagedRemote: Story = {
  args: {
    open: true,
    isCreating: false,
    error: null,
    onClose: () => {},
    onCreate: () => {},
  },
  render: renderDialog,
}

export const CreateError: Story = {
  args: {
    ...CreateManagedRemote.args,
    error: 'Remote name already exists.',
  },
  render: renderDialog,
}
