import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ArchiveInfoTab from '../ArchiveInfoTab'
import type { ArchiveDetailResponse } from '../../../types/archives'

const archive = (overrides: Partial<ArchiveDetailResponse> = {}): ArchiveDetailResponse => ({
  id: 12,
  repository_id: 7,
  borg_id: 'abc123',
  name: 'nas-2026-09-02T02:00',
  series: 'nightly',
  start: '2026-09-02T02:00:00',
  end: '2026-09-02T02:14:00',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 1000 * 1024,
  compressed_size: 600 * 1024,
  deduplicated_size: 250 * 1024,
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: null,
  history_rows: 40,
  history_truncated: false,
  first_seen_at: null,
  last_seen_at: null,
  predecessor_id: null,
  successor_id: null,
  history_available: true,
  ...overrides,
})

describe('ArchiveInfoTab', () => {
  it('shows the three sizes as storage tiles', () => {
    render(<ArchiveInfoTab archive={archive()} />)
    expect(screen.getByText('1000.00 KB')).toBeInTheDocument()
    expect(screen.getByText('600.00 KB')).toBeInTheDocument()
    expect(screen.getByText('250.00 KB')).toBeInTheDocument()
  })

  it('says what share of the original is actually stored and how much was saved', () => {
    render(<ArchiveInfoTab archive={archive()} />)
    expect(screen.getByText(/25% of the original/i)).toBeInTheDocument()
    expect(screen.getByText(/saved 750\.00 KB/i)).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '25')
  })

  it('leaves the storage bar out when the sizes are unknown', () => {
    render(<ArchiveInfoTab archive={archive({ original_size: null, deduplicated_size: null })} />)
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
  })

  it('lists the facts with the series, host, and user', () => {
    render(<ArchiveInfoTab archive={archive()} />)
    expect(screen.getByText('nightly')).toBeInTheDocument()
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByText('root')).toBeInTheDocument()
    expect(screen.getByText('12,000')).toBeInTheDocument()
  })

  it('shows the comment as a quote only when there is one', () => {
    const { rerender } = render(<ArchiveInfoTab archive={archive()} />)
    expect(screen.queryByText(/comment/i)).not.toBeInTheDocument()
    rerender(<ArchiveInfoTab archive={archive({ comment: 'Before the migration' })} />)
    expect(screen.getByText('Before the migration')).toBeInTheDocument()
  })
})
