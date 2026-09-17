import type { Meta, StoryObj } from '@storybook/react-vite'
import { ThemeProvider } from '@mui/material/styles'
import { Box, CssBaseline } from '@mui/material'
import ArchiveGrowthChart from './ArchiveGrowthChart'
import { getTheme } from '../../theme'
import type { GrowthPoint, GrowthResponse } from '../../types/archives'

// Ninety nightly archives: a slowly growing source, two large days, three
// stale measurements near the end, as in the spec mockup (screen 2).
function nightly(): GrowthPoint[] {
  const points: GrowthPoint[] = []
  let total = 197_000_000_000
  let seed = 7
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  for (let i = 0; i < 90; i += 1) {
    const day = new Date(Date.UTC(2026, 5, 19 + i, 2))
    const spike = i === 30 || i === 67 ? 4.5 : 1
    const added = Math.round((0.3 + rnd() * 0.9 * spike) * 1_000_000_000)
    total += added
    points.push({
      archive_id: i + 1,
      name: `nas-${day.toISOString().slice(0, 10)}T02:00:00`,
      series: 'nightly',
      start: day.toISOString().replace('Z', ''),
      deduplicated_size: added,
      original_size: Math.round((371 + i * 0.46) * 1_000_000_000),
      running_total: total,
      stale: i === 85 || i === 87 || i === 88,
    })
  }
  return points
}

const data: GrowthResponse = {
  points: nightly(),
  series: ['nightly', 'docs'],
  stale_count: 3,
  unmeasured_count: 1,
}

const meta = {
  title: 'Components/Archives/ArchiveGrowthChart',
  component: ArchiveGrowthChart,
  args: {
    data,
    series: '',
    onSeriesChange: () => {},
    onSelectArchive: () => {},
  },
} satisfies Meta<typeof ArchiveGrowthChart>

export default meta
type Story = StoryObj<typeof meta>

export const Repository: Story = {}

export const OneSeries: Story = {
  args: { data: { ...data, series: ['nightly'], stale_count: 0, unmeasured_count: 0 } },
}

export const Empty: Story = {
  args: {
    data: {
      points: data.points.slice(0, 1),
      series: ['nightly'],
      stale_count: 0,
      unmeasured_count: 3,
    },
  },
}

export const Dark: Story = {
  decorators: [
    (Story) => (
      <ThemeProvider theme={getTheme('dark')}>
        <CssBaseline />
        <Box sx={{ p: 2, bgcolor: 'background.paper' }}>
          <Story />
        </Box>
      </ThemeProvider>
    ),
  ],
}
