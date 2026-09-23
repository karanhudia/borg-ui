import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Typography } from '@mui/material'
import StageStrip from './StageStrip'
import { emptyCounts, type StageCounts } from './hubRows'
import { PAUSABLE_STAGES } from '../../types/operations'

// Ten repositories halfway through a wave of backups.
const backupWave: StageCounts = {
  ...emptyCounts(),
  archives: { total: 6, running: 4, waiting: 2, failed: 0 },
  retention: { total: 1, running: 1, waiting: 0, failed: 0 },
  history: { total: 2, running: 1, waiting: 0, failed: 1 },
  stats: { total: 1, running: 1, waiting: 0, failed: 0 },
}

const meta = {
  title: 'BackgroundWork/StageStrip',
  component: StageStrip,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3, maxWidth: 1100 }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    counts: backupWave,
    selected: null,
    onSelect: () => {},
    pausedStages: [],
    canManage: true,
    onTogglePause: () => {},
    historyExtra: (
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        2 workers
      </Typography>
    ),
  },
} satisfies Meta<typeof StageStrip>

export default meta

type Story = StoryObj<typeof meta>

export const BackupWave: Story = {}

export const AllIdle: Story = {
  args: { counts: emptyCounts() },
}

export const Selected: Story = {
  args: { selected: 'archives' },
}

// Pausing file history holds its queued work back: the waiting count grows.
export const OneStagePaused: Story = {
  args: {
    pausedStages: ['history'],
    counts: { ...backupWave, history: { total: 3, running: 0, waiting: 3, failed: 0 } },
  },
}

export const AllPaused: Story = {
  args: { pausedStages: PAUSABLE_STAGES },
}

export const ReadOnly: Story = {
  args: { canManage: false, pausedStages: ['history'] },
}

// Automatic prune previews are off in System settings: nothing queues the
// retention stage on its own, so it reads as off and has no pause control.
export const RetentionOff: Story = {
  args: { retentionOff: true },
}
