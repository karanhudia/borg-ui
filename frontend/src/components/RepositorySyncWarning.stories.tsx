import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { userEvent, within } from 'storybook/test'
import RepositorySyncWarning from './RepositorySyncWarning'

const meta = {
  title: 'Components/RepositorySyncWarning',
  component: RepositorySyncWarning,
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <Box sx={{ width: 588, maxWidth: 'calc(100vw - 48px)' }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    warning: {
      operation_id: 72,
      last_success_at: '2026-05-15T16:35:00Z',
      error_message:
        'Saved SSH private key (ID 42) cannot be decrypted. Restore the original app SECRET_KEY (or /data/.secret_key) or re-import this SSH key.',
    },
  },
} satisfies Meta<typeof RepositorySyncWarning>

export default meta
type Story = StoryObj<typeof meta>

export const PersistentFailure: Story = {}

export const NeverSynced: Story = {
  args: { warning: { ...meta.args.warning, last_success_at: null } },
}

export const RecoveryDetails: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole('button', { name: 'Archive sync failed: View details' })
    )
  },
}

export const Dark: Story = { globals: { theme: 'dark' } }
