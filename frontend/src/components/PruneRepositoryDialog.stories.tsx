import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import PruneRepositoryDialog from './PruneRepositoryDialog'

const meta = {
  title: 'Components/PruneRepositoryDialog',
  component: PruneRepositoryDialog,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof PruneRepositoryDialog>

export default meta

type Story = StoryObj<typeof meta>

const repository = {
  id: 42,
  name: 'Production Archive',
  path: '/mnt/borg/production',
}

export const RetentionPreview: Story = {
  args: {
    open: true,
    repository,
    initialForm: {
      keep_daily: 14,
      keep_weekly: 2,
      keep_monthly: 6,
      keep_yearly: 1,
    },
    isLoading: false,
    results: null,
    onClose: () => {},
    onDryRun: async () => {},
    onConfirmPrune: async () => {},
  },
  render: (args) => (
    <Box sx={{ width: 560, minHeight: 520 }}>
      <PruneRepositoryDialog {...args} />
    </Box>
  ),
}
