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

const borgV1DryRunOutput = [
  '[stderr] {"type": "log_message", "message": "Keeping archive (rule: daily #1):            production-2026-06-09      Tue, 2026-06-09 04:00:42 [abcdef0123456789]", "levelname": "INFO", "name": "borg.output.list"}',
  '[stderr] {"type": "log_message", "message": "Would prune:                                 production-2026-06-08      Mon, 2026-06-08 22:24:37 [1234567890abcdef]", "levelname": "INFO", "name": "borg.output.list"}',
  '[stderr] {"type": "log_message", "message": "Keeping archive (rule: weekly #1):           production-2026-06-07      Sun, 2026-06-07 22:16:20 [fedcba0987654321]", "levelname": "INFO", "name": "borg.output.list"}',
  '[stderr] {"type": "log_message", "message": "Would prune:                                 production-2026-06-06      Sat, 2026-06-06 04:00:19 [0011223344556677]", "levelname": "INFO", "name": "borg.output.list"}',
].join('\n')

export const RetentionPreview: Story = {
  args: {
    open: true,
    repository,
    initialForm: {
      keep_within: '1d',
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

export const DryRunLogMessages: Story = {
  args: {
    open: true,
    repository,
    initialForm: {
      keep_within: '12H',
      keep_daily: 1,
      keep_weekly: 1,
      keep_monthly: 1,
      keep_yearly: 0,
    },
    isLoading: false,
    results: {
      dry_run: true,
      prune_result: {
        success: true,
        stdout: borgV1DryRunOutput,
      },
    },
    onClose: () => {},
    onDryRun: async () => {},
    onConfirmPrune: async () => {},
  },
  render: (args) => (
    <Box sx={{ width: 760, minHeight: 620 }}>
      <PruneRepositoryDialog {...args} />
    </Box>
  ),
}
