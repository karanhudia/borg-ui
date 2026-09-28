import type { Meta, StoryObj } from '@storybook/react-vite'
import SshKeyDeleteDialog from './SshKeyDeleteDialog'

const meta = {
  title: 'Components/Wizard/SSH Key Delete Dialog',
  component: SshKeyDeleteDialog,
  args: {
    open: true,
    keyName: 'borgbase-sftp',
    repositoryCount: 0,
    onClose: () => {},
    onConfirm: () => {},
  },
} satisfies Meta<typeof SshKeyDeleteDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Unused: Story = {}

export const SharedByRepositories: Story = {
  args: { repositoryCount: 3 },
}

export const Deleting: Story = {
  args: { repositoryCount: 1, isDeleting: true },
}
