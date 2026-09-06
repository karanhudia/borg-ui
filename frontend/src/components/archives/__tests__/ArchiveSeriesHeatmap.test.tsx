import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ArchiveSeriesHeatmap from '../ArchiveSeriesHeatmap'
import type { HeatmapResponse, HeatmapSeries } from '../../../types/archives'

const day = (date: string, overrides = {}) => ({
  date,
  count: 1,
  deduplicated_size: 41_200_000_000,
  duration_seconds: 7860,
  archive_ids: [12],
  anomalies: [],
  ...overrides,
})

const series = (name: string, days: HeatmapSeries['days'], missed: string[] = []) => ({
  series: name,
  days,
  missed_days: missed,
  first: days[0]?.date ?? null,
  last: days[days.length - 1]?.date ?? null,
})

const data: HeatmapResponse = {
  since: '2026-08-01',
  until: '2026-09-04',
  series: [
    series(
      'nightly',
      [day('2026-09-01'), day('2026-09-02', { count: 0, archive_ids: [] })],
      ['2026-09-02']
    ),
  ],
  flags_available: { missed_run: true, size_outlier: false, duration_outlier: false },
}

describe('ArchiveSeriesHeatmap', () => {
  it('renders one band per series', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText('nightly')).toBeInTheDocument()
  })

  it('opens the archive for a day that has one', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-01'))
    expect(onSelectDay).toHaveBeenCalledWith(expect.objectContaining({ archive_ids: [12] }))
  })

  it('does not select an empty day', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-02'))
    expect(onSelectDay).not.toHaveBeenCalled()
  })

  it('marks a missed day so it reads as a gap rather than an empty cell', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByTestId('heatmap-day-nightly-2026-09-02')).toHaveAttribute(
      'data-missed',
      'true'
    )
  })

  it('draws one shared month axis above the bands', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    const axis = screen.getByTestId('heatmap-month-axis')
    expect(axis).toHaveTextContent(/Sep/)
    expect(axis).toHaveTextContent(/Aug/)
  })

  it('keys cells by local date so a day never shifts across midnight', () => {
    // 2026-09-01 in UTC is still 2026-09-01 wherever the browser sits; the
    // cell must exist under that date and no cell may claim 2026-08-31.
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByTestId('heatmap-day-nightly-2026-09-01')).toHaveAttribute('data-count', '1')
    expect(screen.getByTestId('heatmap-day-nightly-2026-08-31')).toHaveAttribute('data-count', '0')
  })

  it('folds series with only a few archives behind a disclosure', () => {
    const tiny: HeatmapResponse = {
      ...data,
      series: [
        series(
          'nightly',
          [1, 2, 3, 4, 5, 6].map((n) => day(`2026-09-0${n}`))
        ),
        series('Downloads-backup', [day('2026-08-20')]),
        series('downloads backup', [day('2026-08-21')]),
      ],
    }
    render(<ArchiveSeriesHeatmap data={tiny} onSelectDay={vi.fn()} />)
    expect(screen.queryByText('Downloads-backup')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /show 2 smaller series/i }))
    expect(screen.getByText('Downloads-backup')).toBeInTheDocument()
    expect(screen.getByText('downloads backup')).toBeInTheDocument()
  })

  it('places the legend under the bands', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText('Less')).toBeInTheDocument()
    expect(screen.getByText(/missed run/i)).toBeInTheDocument()
  })
})

describe('ArchiveSeriesHeatmap days with several archives', () => {
  const multi: HeatmapResponse = {
    ...data,
    series: [
      series('nightly', [
        day('2026-09-01', { count: 2, archive_ids: [12, 13] }),
        day('2026-09-02'),
      ]),
    ],
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
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-01'))
    expect(onSelectDay).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('menuitem', { name: /14:00/ }))
    expect(onSelectArchive).toHaveBeenCalledWith(13)
  })

  it('still opens a single-archive day directly', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={multi} onSelectDay={onSelectDay} archiveLookup={lookup} />)
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-02'))
    expect(onSelectDay).toHaveBeenCalled()
  })

  it('totals the missed days in the legend', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText(/1 missed day/)).toBeInTheDocument()
  })
})
