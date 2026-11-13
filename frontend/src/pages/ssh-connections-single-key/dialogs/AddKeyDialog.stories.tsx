import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn, screen } from 'storybook/test'
import { AddKeyDialog } from './AddKeyDialog'

const meta = {
  title: 'Remote Machines/AddKeyDialog',
  component: AddKeyDialog,
  parameters: { layout: 'fullscreen' },
  args: { open: true, onClose: fn(), onSubmit: fn() },
} satisfies Meta<typeof AddKeyDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Generate: Story = {}

export const Pending: Story = { args: { pending: true } }

/** Both path fields browse the Borg UI host for a key file. */
export const ImportFromPath: Story = {
  play: async ({ userEvent }) => {
    await userEvent.click(await screen.findByRole('tab', { name: 'Import from path' }))
  },
}
