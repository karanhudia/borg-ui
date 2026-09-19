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
      repository_size: Math.round(total * 0.35),
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

// Four archives months apart: the shape the chart takes on a repository
// that is pruned hard, every mark labelled.
export const Sparse: Story = {
  args: {
    data: {
      points: [
        {
          archive_id: 1,
          name: 'manual-backup-2025-12-31',
          series: 'manual-backup',
          start: '2025-12-31T10:40:56',
          deduplicated_size: 520_000,
          original_size: 600_000_000,
          repository_size: 600_000_000,
          running_total: 520_000,
          stale: false,
        },
        {
          archive_id: 2,
          name: 'Downloads-Backup-2026-08-31T14:00:47',
          series: 'Downloads-Backup',
          start: '2026-08-31T08:30:49',
          deduplicated_size: 0,
          original_size: 22_350_000_000,
          repository_size: 22_900_000_000,
          running_total: 520_000,
          stale: false,
        },
        {
          archive_id: 3,
          name: 'Downloads-Backup-2026-09-13T20:46:27',
          series: 'Downloads-Backup',
          start: '2026-09-13T15:16:30',
          deduplicated_size: 120_000,
          original_size: 22_300_000_000,
          repository_size: 22_950_000_000,
          running_total: 640_000,
          stale: false,
        },
        {
          archive_id: 4,
          name: 'Downloads-Backup-2026-09-18T20:52:01',
          series: 'Downloads-Backup',
          start: '2026-09-18T15:22:40',
          deduplicated_size: 9_910_000,
          original_size: 4_500_000_000,
          repository_size: 19_440_000_000,
          running_total: 10_550_000,
          stale: false,
        },
      ],
      series: ['manual-backup', 'Downloads-Backup'],
      stale_count: 0,
      unmeasured_count: 0,
    },
  },
}
