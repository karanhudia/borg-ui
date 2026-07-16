import { Box } from '@mui/material'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { ActivityTimeline } from './ActivityTimeline'
import { makeT, TokenContext } from './tokens'
import type { DashboardOverview } from './types'

const T = makeT(true)
type Activity = DashboardOverview['activity_feed'][number]

const activities: Activity[] = [
  {
    id: 3,
    type: 'backup',
    status: 'completed',
    repository: 'Latest backup',
    timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    message: 'Latest backup completed',
    error: null,
  },
  {
    id: 2,
    type: 'backup',
    status: 'failed',
    repository: 'Earlier failed backup',
    timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    message: 'Earlier backup failed',
    error: 'Connection refused',
  },
  {
    id: 1,
    type: 'backup',
    status: 'completed',
    repository: 'Oldest backup',
    timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
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
