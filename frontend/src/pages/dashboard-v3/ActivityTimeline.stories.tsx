import { Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { format, subDays } from 'date-fns'
import { ActivityTimeline } from './ActivityTimeline'
import { makeT, TokenContext } from './tokens'
import type { DashboardOverview } from './types'

// Follows the Storybook theme toolbar, so each story renders both modes.
const useStoryT = () => makeT(useTheme().palette.mode === 'dark')
type Timeline = NonNullable<DashboardOverview['activity_timeline']>

function daysAgo(days: number) {
  return format(subDays(new Date(), days), 'yyyy-MM-dd')
}

// A fortnight of a small installation: a backup most days, one check, one
// compact, one failed backup that a later run resolved.
const timeline: Timeline = [
  { date: daysAgo(13), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(12), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(10), type: 'backup', total: 1, failed: 1 },
  { date: daysAgo(9), type: 'backup', total: 2, failed: 0 },
  { date: daysAgo(9), type: 'check', total: 1, failed: 0 },
  { date: daysAgo(6), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(6), type: 'compact', total: 1, failed: 0 },
  { date: daysAgo(3), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(3), type: 'prune', total: 1, failed: 0 },
  { date: daysAgo(1), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(0), type: 'backup', total: 1, failed: 0 },
  { date: daysAgo(0), type: 'restore_check', total: 1, failed: 0 },
]

// Hourly plans on a dozen repositories: every cell is over the dot cap, the
// title carries the counts.
const busy: Timeline = Array.from({ length: 14 }, (_, i) => i).flatMap((day) => [
  { date: daysAgo(day), type: 'backup', total: 160 + day, failed: day % 5 === 0 ? 3 : 0 },
  { date: daysAgo(day), type: 'prune', total: 40, failed: 0 },
  { date: daysAgo(day), type: 'compact', total: 40, failed: day === 2 ? 1 : 0 },
  ...(day % 7 === 0 ? [{ date: daysAgo(day), type: 'check', total: 12, failed: 0 }] : []),
])

const meta = {
  title: 'Pages/DashboardV3/ActivityTimeline',
  component: ActivityTimeline,
  parameters: {
    layout: 'padded',
  },
  render: function Render(args) {
    const T = useStoryT()
    return (
      <TokenContext.Provider value={T}>
        <Box sx={{ width: 680, maxWidth: '100%', color: T.textPrimary }}>
          <ActivityTimeline {...args} />
        </Box>
      </TokenContext.Provider>
    )
  },
} satisfies Meta<typeof ActivityTimeline>

export default meta
type Story = StoryObj<typeof meta>

export const Fortnight: Story = {
  args: { timeline },
}

export const BusyInstallation: Story = {
  args: { timeline: busy },
}

export const Quiet: Story = {
  args: { timeline: [] },
}
