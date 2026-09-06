import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { format } from 'date-fns'
import ArchiveHourlyHeatmap from '../ArchiveHourlyHeatmap'
import { suggestScale } from '../heatmapScale'
import type { ArchiveRow } from '../../../types/archives'

const row = (id: number, start: string, overrides: Partial<ArchiveRow> = {}): ArchiveRow =>
  ({
    id,
    repository_id: 1,
    borg_id: `b${id}`,
    name: `hourly-${id}`,
    series: 'hourly',
    start,
    end: null,
    duration_seconds: 60,
    nfiles: 10,
    original_size: 1000,
    compressed_size: 900,
    deduplicated_size: 100,
    hostname: null,
    username: null,
    comment: null,
    backup_operation_id: null,
    history_state: 'indexed',
    history_indexed_at: null,
    history_rows: 0,
    history_truncated: false,
    first_seen_at: null,
    last_seen_at: null,
    ...overrides,
  }) as ArchiveRow

// Backend timestamps are naive UTC, so build each one from a local hour of
// today and hand over its UTC form; the cells then land on the local hour.
const now = new Date()
const today = format(now, 'yyyy-MM-dd')
const at = (hour: number, minute = 0) =>
  new Date(now.getFullYear(), now.getMonth(), now.getDate(), hour, minute)
    .toISOString()
    .replace('Z', '')

describe('ArchiveHourlyHeatmap', () => {
  it('places each archive in its hour and opens it on click', () => {
    const onSelectArchive = vi.fn()
    render(
      <ArchiveHourlyHeatmap
        archives={[row(1, at(2)), row(2, at(14))]}
        onSelectArchive={onSelectArchive}
      />
    )
    const cell = screen.getByTestId(`hourly-cell-hourly-${today}-14`)
    expect(cell).toHaveAttribute('data-count', '1')
    fireEvent.click(cell)
    expect(onSelectArchive).toHaveBeenCalledWith(2)
  })

  it('offers a chooser when an hour holds several archives', () => {
    const onSelectArchive = vi.fn()
    render(
      <ArchiveHourlyHeatmap
        archives={[row(1, at(9, 5)), row(2, at(9, 40))]}
        onSelectArchive={onSelectArchive}
      />
    )
    fireEvent.click(screen.getByTestId(`hourly-cell-hourly-${today}-9`))
    expect(onSelectArchive).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('menuitem', { name: /hourly-2/ }))
    expect(onSelectArchive).toHaveBeenCalledWith(2)
  })

  it('says so when nothing ran in the window', () => {
    render(<ArchiveHourlyHeatmap archives={[]} onSelectArchive={vi.fn()} />)
    expect(screen.getByText(/no archives in the last 4 weeks/i)).toBeInTheDocument()
  })
})

describe('suggestScale', () => {
  it('prefers hours for a repository that runs several times a day', () => {
    expect(suggestScale([row(1, at(1)), row(2, at(7)), row(3, at(13))])).toBe('hours')
  })

  it('keeps days for a nightly repository', () => {
    expect(suggestScale([row(1, at(2))])).toBe('days')
  })
})
