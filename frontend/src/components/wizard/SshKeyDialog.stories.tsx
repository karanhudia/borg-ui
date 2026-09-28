import type { Meta, StoryObj } from '@storybook/react-vite'
import SshKeyDialog from './SshKeyDialog'

const meta = {
  title: 'Components/Wizard/SSH Key Dialog',
  component: SshKeyDialog,
  args: {
    open: true,
    onClose: () => {},
    onCreate: () => {},
  },
} satisfies Meta<typeof SshKeyDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Empty: Story = {}

export const WithError: Story = {
  args: { error: 'Invalid private key format' },
}

export const Creating: Story = {
  args: { isCreating: true },
}
