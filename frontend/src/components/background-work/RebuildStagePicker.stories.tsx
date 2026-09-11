import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RebuildStagePicker from './RebuildStagePicker'
import type { RebuildStage } from '../../types/operations'

function Picker({
  historyLocked,
  initial,
  reason,
}: {
  historyLocked: boolean
  initial: RebuildStage
  reason?: 'plan' | 'agent'
}) {
  const [value, setValue] = useState<RebuildStage>(initial)
  return (
    <RebuildStagePicker
      value={value}
      onChange={setValue}
      historyLocked={historyLocked}
      historyLockedReason={reason}
    />
  )
}

const meta = {
  title: 'BackgroundWork/RebuildStagePicker',
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3, maxWidth: 960 }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof RebuildStagePicker>

export default meta

type Story = StoryObj<typeof meta>

export const FromStats: Story = {
  render: () => <Picker historyLocked={false} initial="stats" />,
}

export const FromArchives: Story = {
  render: () => <Picker historyLocked={false} initial="archives" />,
}

export const Community: Story = {
  render: () => <Picker historyLocked initial="archives" />,
}

// Locked by the repository, not the plan: an agent's repository cannot be
// diffed, so the history stage is out regardless of the plan.
export const HistoryUnsupportedForAgent: Story = {
  render: () => <Picker historyLocked initial="archives" reason="agent" />,
}
