import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ArchiveSeriesHeatmap from '../ArchiveSeriesHeatmap'
import type { HeatmapDay, HeatmapResponse } from '../../../types/archives'

const day = (date: string, overrides = {}) => ({
  date,
  count: 1,
  deduplicated_size: 41_200_000_000,
  duration_seconds: 7860,
  archive_ids: [12],
  anomalies: [],
  ...overrides,
})

const band = (days: HeatmapDay[], missed: string[] = []) => ({
  days,
  missed_days: missed,
  first: days[0]?.date ?? null,
  last: days[days.length - 1]?.date ?? null,
  count: days.reduce((sum, d) => sum + d.count, 0),
})

const series = (name: string, days: HeatmapDay[]) => ({ ...band(days), series: name })

const days = [day('2026-09-01'), day('2026-09-02', { count: 0, archive_ids: [] })]

const data: HeatmapResponse = {
  since: '2026-08-01',
  until: '2026-09-04',
  repository: band(days, ['2026-09-02']),
  series: [series('nightly', days)],
  cadence_known: true,
  retention_since: null,
  flags_available: { missed_run: true, size_outlier: false, duration_outlier: false },
}

describe('ArchiveSeriesHeatmap', () => {
  it('draws the repository band, not one band per inferred series', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText('All archives (1)')).toBeInTheDocument()
    expect(screen.queryByText('nightly')).not.toBeInTheDocument()
  })

  it('opens the archive for a day that has one', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-repository-2026-09-01'))
    expect(onSelectDay).toHaveBeenCalledWith(expect.objectContaining({ archive_ids: [12] }))
  })

  it('does not select an empty day', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-repository-2026-09-02'))
    expect(onSelectDay).not.toHaveBeenCalled()
  })

  it('marks a missed day so it reads as a gap rather than an empty cell', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByTestId('heatmap-day-repository-2026-09-02')).toHaveAttribute(
      'data-missed',
      'true'
    )
  })

  it('draws one shared month axis above the bands', () => {
    const split: HeatmapResponse = {
      ...data,
      series: [series('nightly', days), series('weekly-offsite', [day('2026-08-20')])],
    }
    render(<ArchiveSeriesHeatmap data={split} onSelectDay={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /group by series/i }))
    const axis = screen.getByTestId('heatmap-month-axis')
    expect(axis).toHaveTextContent(/Aug/)
    expect(axis).toHaveTextContent(/Jul/)
  })

  it('keys cells by local date so a day never shifts across midnight', () => {
    // 2026-09-01 in UTC is still 2026-09-01 wherever the browser sits; the
    // cell must exist under that date and no cell may claim 2026-08-31.
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByTestId('heatmap-day-repository-2026-09-01')).toHaveAttribute(
      'data-count',
      '1'
    )
    expect(screen.getByTestId('heatmap-day-repository-2026-08-31')).toHaveAttribute(
      'data-count',
      '0'
    )
  })

  it('keeps every archive visible however the names were split (issue #943)', () => {
    const archives = [day('2026-04-30'), day('2026-05-31'), day('2026-06-30')]
    const split: HeatmapResponse = {
      ...data,
      repository: band([...archives, ...days]),
      series: [
        series('nightly', days),
        ...archives.map((a, i) => series(`old-prefix-${a.date}-17${i}`, [a])),
      ],
    }
    render(<ArchiveSeriesHeatmap data={split} onSelectDay={vi.fn()} />)
    // Four archives in the band, not one: the three singleton series are part
    // of the count and part of the calendar.
    expect(screen.getByText('All archives (4)')).toBeInTheDocument()
    expect(screen.getByTestId('heatmap-day-repository-2026-04-30')).toHaveAttribute(
      'data-count',
      '1'
    )
  })

  it('offers the series split as a grouping below the band', () => {
    const split: HeatmapResponse = {
      ...data,
      series: [series('nightly', days), series('weekly-offsite', [day('2026-08-20')])],
    }
    render(<ArchiveSeriesHeatmap data={split} onSelectDay={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /group by series \(2\)/i }))
    expect(screen.getByText('nightly')).toBeInTheDocument()
    expect(screen.getByText('weekly-offsite')).toBeInTheDocument()
  })

  it('does not offer a split when there is only one series', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /group by series/i })).not.toBeInTheDocument()
  })

  it('places the legend under the bands', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText('Less')).toBeInTheDocument()
    expect(screen.getByText(/missed run/i)).toBeInTheDocument()
  })

  it('says no day is judged when no schedule gives the cadence', () => {
    const unscheduled: HeatmapResponse = {
      ...data,
      repository: band(days),
      cadence_known: false,
    }
    render(<ArchiveSeriesHeatmap data={unscheduled} onSelectDay={vi.fn()} />)
    expect(screen.getByText(/no schedule known/i)).toBeInTheDocument()
    expect(screen.queryByText(/missed day/i)).not.toBeInTheDocument()
  })
})

describe('ArchiveSeriesHeatmap days with several archives', () => {
  const multi: HeatmapResponse = {
    ...data,
    repository: band([day('2026-09-01', { count: 2, archive_ids: [12, 13] }), day('2026-09-02')]),
  }
  const lookup = (id: number) =>
    ({
      12: { name: 'nightly-2026-09-01T02:00', start: '2026-09-01T02:00:00Z', size: 1024 },
      13: { name: 'nightly-2026-09-01T14:00', start: '2026-09-01T14:00:00Z', size: 2048 },
    })[id]

  it('offers a chooser instead of opening the first archive', () => {
    const onSelectDay = vi.fn()
    const onSelectArchive = vi.fn()
    render(
      <ArchiveSeriesHeatmap
        data={multi}
        onSelectDay={onSelectDay}
        onSelectArchive={onSelectArchive}
        archiveLookup={lookup}
      />
    )
    fireEvent.click(screen.getByTestId('heatmap-day-repository-2026-09-01'))
    expect(onSelectDay).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('menuitem', { name: /14:00/ }))
    expect(onSelectArchive).toHaveBeenCalledWith(13)
  })

  it('still opens a single-archive day directly', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={multi} onSelectDay={onSelectDay} archiveLookup={lookup} />)
    fireEvent.click(screen.getByTestId('heatmap-day-repository-2026-09-02'))
    expect(onSelectDay).toHaveBeenCalled()
  })

  it('totals the missed days in the legend', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText(/1 missed day/)).toBeInTheDocument()
  })
})
