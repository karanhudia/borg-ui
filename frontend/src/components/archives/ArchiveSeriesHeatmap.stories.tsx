import type { Meta, StoryObj } from '@storybook/react-vite'
import { ToggleButton, ToggleButtonGroup } from '@mui/material'
import ArchiveSeriesHeatmap from './ArchiveSeriesHeatmap'
import type { HeatmapDay, HeatmapResponse } from '../../types/archives'

const day = (date: string, overrides: Partial<HeatmapDay> = {}): HeatmapDay => ({
  date,
  count: 1,
  deduplicated_size: 41_200_000_000,
  duration_seconds: 7860,
  archive_ids: [12],
  anomalies: [] as string[],
  ...overrides,
})

const band = (days: HeatmapDay[], missed: string[] = []) => ({
  days,
  missed_days: missed,
  first: days[0]?.date ?? null,
  last: days[days.length - 1]?.date ?? null,
  count: days.reduce((sum, d) => sum + d.count, 0),
})

const series = (name: string, days: HeatmapDay[]) => {
  const { days: bandDays, first, last, count } = band(days)
  return { days: bandDays, first, last, count, series: name }
}

const response = (
  days: HeatmapDay[],
  options: Partial<HeatmapResponse> & { missed?: string[] } = {}
): HeatmapResponse => {
  const { missed = [], ...overrides } = options
  return {
    since: null,
    until: null,
    repository: band(days, missed),
    series: [series('nightly', days)],
    cadence_known: true,
    retention_since: null,
    flags_available: { missed_run: true, size_outlier: true, duration_outlier: true },
    ...overrides,
  }
}

const meta = {
  title: 'Components/Archives/ArchiveSeriesHeatmap',
  component: ArchiveSeriesHeatmap,
  args: {
    onSelectDay: () => {},
  },
} satisfies Meta<typeof ArchiveSeriesHeatmap>

export default meta

type Story = StoryObj<typeof meta>

const recent = [
  day('2026-08-30'),
  day('2026-09-01', { anomalies: ['size_outlier'] }),
  day('2026-09-02', { count: 2, archive_ids: [12, 13] }),
]

export const Default: Story = {
  args: {
    data: response(recent, {
      missed: ['2026-08-31'],
      series: [series('nightly', recent), series('weekly-offsite', [day('2026-08-30')])],
    }),
  },
}

export const NoScheduleKnown: Story = {
  args: {
    data: response(recent, { cadence_known: false }),
  },
}

export const Empty: Story = {
  args: {
    data: response([], { series: [] }),
  },
}

const nightlyYear = (() => {
  const days: HeatmapDay[] = []
  const start = new Date()
  start.setDate(start.getDate() - 364)
  for (let i = 0; i < 365; i++) {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    // Skip a few days so the calendar shows gaps, and flag a slow run.
    if (i % 23 === 0) continue
    const iso = date.toISOString().slice(0, 10)
    days.push(
      day(iso, { count: i % 9 === 0 ? 2 : 1, anomalies: i % 61 === 0 ? ['duration_outlier'] : [] })
    )
  }
  return days
})()

export const FullYear: Story = {
  args: {
    data: response(nightlyYear, {
      missed: nightlyYear.length > 30 ? [nightlyYear[30].date] : [],
      series: [
        series('nightly', nightlyYear),
        series(
          'weekly-offsite',
          nightlyYear.filter((_d, i) => i % 7 === 0)
        ),
        series('old-prefix-2026-04-30-1777586400', nightlyYear.slice(0, 1)),
      ],
    }),
  },
}

export const WithHeader: Story = {
  ...FullYear,
  args: {
    ...FullYear.args,
    header: {
      toolbar: (
        <ToggleButtonGroup value="days" exclusive size="small">
          <ToggleButton value="days">Days</ToggleButton>
          <ToggleButton value="hours">Hours</ToggleButton>
        </ToggleButtonGroup>
      ),
    },
  },
}
