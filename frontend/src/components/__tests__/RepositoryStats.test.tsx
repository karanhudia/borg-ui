import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RepositoryStats from '../RepositoryStats'
import RepositoryStatsGrid from '../RepositoryStatsGrid'

describe('RepositoryStats', () => {
  it('names and formats a measured Borg 2 repository size', () => {
    render(
      <RepositoryStats
        borgVersion={2}
        storage={{
          size_bytes: 1024 ** 3,
          size_source: 'borg2_index',
          measured_at: '2026-09-14T10:00:00Z',
          last_modified: null,
          archives_consistent: true,
          original_size: 2 * 1024 ** 3,
          compressed_size: null,
          deduplicated_size: null,
          latest_archive_files: 4,
          compact: null,
          compact_at: null,
        }}
      />
    )
    expect(screen.getByText('Repository size')).toBeInTheDocument()
    expect(screen.getByText('1.00 GB')).toBeInTheDocument()
    expect(screen.getByText('not reported by this Borg version')).toBeInTheDocument()
  })

  it('shows unknown rather than a zero fallback for unmeasured values', () => {
    render(<RepositoryStats storage={null} />)
    expect(screen.getAllByText('unknown').length).toBeGreaterThan(0)
    expect(screen.queryByText('0 B')).not.toBeInTheDocument()
  })

  it('keeps the archive count in a loading state until archives finish loading', () => {
    const { container } = render(
      <RepositoryStats archiveCount={35} archivesLoading storage={null} />
    )
    expect(screen.queryByText('35')).not.toBeInTheDocument()
    expect(container.querySelector('.MuiSkeleton-root')).toBeInTheDocument()
  })

  it('keeps the Borg 2 header to the four summary values from the issue', () => {
    render(
      <RepositoryStatsGrid
        borgVersion={2}
        archivesCount={35}
        storage={{
          size_bytes: 1024 ** 3,
          size_source: 'borg2_index',
          measured_at: null,
          last_modified: null,
          archives_consistent: true,
          original_size: 2 * 1024 ** 3,
          compressed_size: null,
          deduplicated_size: null,
          latest_archive_files: 881,
          compact: null,
          compact_at: null,
        }}
      />
    )

    expect(screen.getByText('Number of Files')).toBeInTheDocument()
    expect(screen.getByText('881')).toBeInTheDocument()
    expect(screen.queryByText('Compressed size')).not.toBeInTheDocument()
    expect(screen.queryByText('Deduplicated size')).not.toBeInTheDocument()
  })

  it('does not duplicate Borg 1 deduplicated size in the dialog', () => {
    render(
      <RepositoryStats
        borgVersion={1}
        storage={{
          size_bytes: 1024 ** 3,
          size_source: 'borg1_cache_stats',
          measured_at: null,
          last_modified: null,
          archives_consistent: true,
          original_size: 2 * 1024 ** 3,
          compressed_size: 512 * 1024 ** 2,
          deduplicated_size: 1024 ** 3,
          latest_archive_files: 881,
          compact: null,
          compact_at: null,
        }}
      />
    )

    expect(screen.getAllByText('Deduplicated size')).toHaveLength(1)
  })
})
