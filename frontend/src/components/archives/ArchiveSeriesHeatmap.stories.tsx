import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveSeriesHeatmap from './ArchiveSeriesHeatmap'
import type { HeatmapResponse } from '../../types/archives'

const day = (
  date: string,
  overrides: Partial<HeatmapResponse['series'][number]['days'][number]> = {}
) => ({
  date,
  count: 1,
  deduplicated_size: 41_200_000_000,
  duration_seconds: 7860,
  archive_ids: [12],
  anomalies: [] as string[],
  ...overrides,
})

const meta = {
  title: 'Components/Archives/ArchiveSeriesHeatmap',
  component: ArchiveSeriesHeatmap,
  args: {
    onSelectDay: () => {},
  },
} satisfies Meta<typeof ArchiveSeriesHeatmap>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    data: {
      since: '2026-08-01',
      until: '2026-09-04',
      series: [
        {
          series: 'nightly',
          days: [
            day('2026-08-30'),
            day('2026-08-31', { count: 0, archive_ids: [] }),
            day('2026-09-01', { anomalies: ['size_outlier'] }),
            day('2026-09-02'),
          ],
          missed_days: ['2026-08-31'],
          first: '2026-08-01T02:00:00Z',
          last: '2026-09-02T02:00:00Z',
        },
        {
          series: 'weekly-offsite',
          days: [day('2026-08-30', { count: 2 })],
          missed_days: [],
          first: '2026-08-30T02:00:00Z',
          last: '2026-08-30T02:00:00Z',
        },
      ],
      flags_available: { missed_run: true, size_outlier: true, duration_outlier: true },
    },
  },
}

export const SingleSeries: Story = {
  args: {
    data: {
      since: null,
      until: null,
      series: [
        {
          series: 'nightly',
          days: [day('2026-09-01'), day('2026-09-02'), day('2026-09-03')],
          missed_days: [],
          first: '2026-09-01T02:00:00Z',
          last: '2026-09-03T02:00:00Z',
        },
      ],
      flags_available: { missed_run: true, size_outlier: false, duration_outlier: false },
    },
  },
}

export const Empty: Story = {
  args: {
    data: {
      since: null,
      until: null,
      series: [
        {
          series: 'nightly',
          days: [],
          missed_days: [],
          first: null,
          last: null,
        },
      ],
      flags_available: { missed_run: false, size_outlier: false, duration_outlier: false },
    },
  },
}

const nightlyYear = (() => {
  const days = []
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
    data: {
      since: null,
      until: null,
      series: [
        {
          series: 'nightly',
          days: nightlyYear,
          missed_days: nightlyYear.length > 30 ? [nightlyYear[30].date] : [],
          first: nightlyYear[0]?.date ?? null,
          last: nightlyYear[nightlyYear.length - 1]?.date ?? null,
        },
        {
          series: 'weekly-offsite',
          days: nightlyYear.filter((_d, i) => i % 7 === 0),
          missed_days: [],
          first: nightlyYear[0]?.date ?? null,
          last: nightlyYear[nightlyYear.length - 1]?.date ?? null,
        },
        {
          series: 'Downloads-backup',
          days: nightlyYear.slice(0, 2),
          missed_days: [],
          first: nightlyYear[0]?.date ?? null,
          last: nightlyYear[1]?.date ?? null,
        },
      ],
      flags_available: { missed_run: true, size_outlier: true, duration_outlier: true },
    },
  },
}
