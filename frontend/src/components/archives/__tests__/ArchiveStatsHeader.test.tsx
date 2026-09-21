import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveStatsHeader from '../ArchiveStatsHeader'
import type { ArchiveDetailResponse } from '../../../types/archives'

const base: ArchiveDetailResponse = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc',
  name: 'nas-2026-09-02',
  series: 'nas',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  stats_measured_at: '2026-09-02T02:20:00Z',
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: null,
  history_rows: 0,
  history_truncated: false,
  first_seen_at: null,
  last_seen_at: null,
  predecessor_id: 11,
  successor_id: null,
  predecessor_stats: {
    id: 11,
    nfiles: 11000,
    original_size: 80_000_000_000,
    deduplicated_size: 30_000_000_000,
    duration_seconds: 900,
  },
  history_available: true,
}

describe('ArchiveStatsHeader', () => {
  it('leads with what the archive added and shows deltas against the predecessor', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={base}
        totals={{ added: 5, removed: 2, modified: 9 }}
        totalsState="ready"
      />
    )
    expect(screen.getByText('Added to the repository')).toBeInTheDocument()
    expect(screen.getByText('38.37 GB')).toBeInTheDocument()
    expect(screen.getByText('+5')).toBeInTheDocument()
    expect(screen.getByText('−2')).toBeInTheDocument()
    expect(screen.getByText('~9')).toBeInTheDocument()
    // 12000 files vs 11000
    expect(screen.getByText('+1,000 vs previous')).toBeInTheDocument()
    // 90 GB vs 80 GB (formatBytes is binary, two decimals)
    expect(screen.getByText('+9.31 GB vs previous')).toBeInTheDocument()
    // 840 s vs 900 s
    expect(screen.getByText('−1 min vs previous')).toBeInTheDocument()
    expect(screen.getByText('1.5:1')).toBeInTheDocument()
    expect(screen.queryByText(/^Measured /)).not.toBeInTheDocument()
  })

  it('says why the file changes are absent instead of showing zeros', () => {
    renderWithProviders(<ArchiveStatsHeader archive={base} totalsState="not_indexed" />)
    expect(screen.getByText('Not indexed yet')).toBeInTheDocument()
    expect(screen.queryByText('+0')).not.toBeInTheDocument()
  })

  it('names the stale state', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{ ...base, stats_measured_at: null }}
        totalsState="ready"
        totals={{ added: 0, removed: 0, modified: 0 }}
      />
    )
    expect(screen.getByText('Re-measuring after archives were removed')).toBeInTheDocument()
  })

  it('names the never-measured state', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{
          ...base,
          stats_measured_at: null,
          original_size: null,
          deduplicated_size: null,
          compressed_size: null,
          nfiles: null,
        }}
        totalsState="ready"
      />
    )
    expect(screen.getByText('Not measured yet')).toBeInTheDocument()
  })

  it('does not render a missing dedup size as 0 B', () => {
    renderWithProviders(
      <ArchiveStatsHeader archive={{ ...base, deduplicated_size: null }} totalsState="ready" />
    )
    expect(screen.queryByText('0 B')).not.toBeInTheDocument()
  })

  it('shows no delta when the predecessor lacks the figure, and no ratio on Borg 2', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{ ...base, compressed_size: null, predecessor_stats: null }}
        totalsState="ready"
      />
    )
    expect(screen.queryByText(/vs previous/)).not.toBeInTheDocument()
    expect(screen.getByText('Not reported by this Borg version')).toBeInTheDocument()
  })
})
