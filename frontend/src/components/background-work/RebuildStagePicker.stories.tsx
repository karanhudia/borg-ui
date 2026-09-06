import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RebuildStagePicker from './RebuildStagePicker'
import type { RebuildStage } from '../../types/operations'

function Picker({ historyLocked, initial }: { historyLocked: boolean; initial: RebuildStage }) {
  const [value, setValue] = useState<RebuildStage>(initial)
  return <RebuildStagePicker value={value} onChange={setValue} historyLocked={historyLocked} />
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
