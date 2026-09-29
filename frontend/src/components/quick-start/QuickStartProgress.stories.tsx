import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import QuickStartProgress from './QuickStartProgress'

const meta = {
  title: 'Quick Start/Progress',
  component: QuickStartProgress,
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <Box sx={{ width: { xs: '100%', sm: 560 }, p: 2 }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof QuickStartProgress>

export default meta
type Story = StoryObj<typeof meta>

const actions = ['create_repository', 'create_plan'] as const

export const Running: Story = {
  args: {
    actions: [...actions],
    statuses: { create_repository: 'done', create_plan: 'running' },
    error: null,
    finished: false,
  },
}

export const Failed: Story = {
  args: {
    actions: [...actions],
    statuses: { create_repository: 'done', create_plan: 'failed' },
    error: 'A backup plan with this name already exists.',
    finished: false,
  },
}

export const Done: Story = {
  args: {
    actions: [...actions],
    statuses: { create_repository: 'done', create_plan: 'done' },
    error: null,
    finished: true,
  },
}
