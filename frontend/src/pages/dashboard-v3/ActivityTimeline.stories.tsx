import { Box } from '@mui/material'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { ActivityTimeline } from './ActivityTimeline'
import { makeT, TokenContext } from './tokens'
import type { DashboardOverview } from './types'

const T = makeT(true)
type Activity = DashboardOverview['activity_feed'][number]

function todayAt(hour: number) {
  const timestamp = new Date()
  timestamp.setHours(hour, 0, 0, 0)
  return timestamp.toISOString()
}

const activities: Activity[] = [
  {
    id: 3,
    type: 'backup',
    status: 'completed',
    repository: 'Latest backup',
    timestamp: todayAt(14),
    message: 'Latest backup completed',
    error: null,
  },
  {
    id: 2,
    type: 'backup',
    status: 'failed',
    repository: 'Earlier failed backup',
    timestamp: todayAt(12),
    message: 'Earlier backup failed',
    error: 'Connection refused',
  },
  {
    id: 1,
    type: 'backup',
    status: 'completed',
    repository: 'Oldest backup',
    timestamp: todayAt(10),
    message: 'Oldest backup completed',
    error: null,
  },
]

const meta = {
  title: 'Pages/DashboardV3/ActivityTimeline',
  component: ActivityTimeline,
  parameters: {
    layout: 'padded',
    backgrounds: {
      default: 'Dashboard dark',
      values: [{ name: 'Dashboard dark', value: '#111827' }],
    },
  },
} satisfies Meta<typeof ActivityTimeline>

export default meta
type Story = StoryObj<typeof meta>

export const SameDayChronologicalOrder: Story = {
  args: { activities },
  render: (args) => (
    <TokenContext.Provider value={T}>
      <Box sx={{ width: 680, maxWidth: '100%', color: T.textPrimary }}>
        <ActivityTimeline {...args} />
      </Box>
    </TokenContext.Provider>
  ),
}
