import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from 'i18next'
import RepositoryStats from '../RepositoryStats'
import { repositoryStatItems, sizeLabelKey, stateText } from '../../utils/repositoryStats'
import type { RepositoryStorage } from '../../types'

const borg1: RepositoryStorage = {
  size_bytes: 2_638_827_906_662,
  size_source: 'borg1_cache_stats',
  measured_at: '2026-09-09T02:15:00.000Z',
  last_modified: '2026-09-09T02:02:11.000Z',
  archives_consistent: true,
  archives_listed: true,
  original_size: 20_540_000_000_000,
  compressed_size: 17_790_000_000_000,
  deduplicated_size: 2_638_827_906_662,
  latest_archive_files: 566_220,
  compact: null,
  compact_at: null,
}

const borg2: RepositoryStorage = {
  size_bytes: 2_523_456_789,
  size_source: 'borg2_index',
  measured_at: '2026-09-14T05:49:02.000Z',
  last_modified: '2026-09-14T05:46:44.000Z',
  archives_consistent: true,
  archives_listed: true,
  original_size: 11_460_000_000,
  compressed_size: null,
  deduplicated_size: 2_300_000_000,
  latest_archive_files: 3157,
  compact: {
    repository_size: 2_523_456_789,
    deduplicated_size: 2_300_000_000,
    source_size: 11_460_000_000,
    compression_factor: 1.42,
    deduplication_factor: 4.98,
    compaction_saved: 184_000_000,
    size_precision: 'rounded',
  },
  compact_at: '2026-09-14T04:48:36.000Z',
}

const unknown: RepositoryStorage = {
  size_bytes: null,
  size_source: null,
  measured_at: null,
  last_modified: null,
  archives_consistent: false,
  archives_listed: false,
  original_size: null,
  compressed_size: null,
  deduplicated_size: null,
  latest_archive_files: null,
  compact: null,
  compact_at: null,
}

const t = i18n.t.bind(i18n)

function stat(key: string) {
  return screen.getByTestId(`repository-stat-${key}`)
}

describe('RepositoryStats', () => {
  describe('the stored size is named by its source', () => {
    it('calls the Borg 1 cache figure the deduplicated size', () => {
      expect(sizeLabelKey('borg1_cache_stats')).toBe('repositoryStats.deduplicatedSize')
    })

    it('calls the index sum and the compact figure the repository size', () => {
      expect(sizeLabelKey('borg2_index')).toBe('repositoryStats.repositorySize')
      expect(sizeLabelKey('compact_stats')).toBe('repositoryStats.repositorySize')
    })

    it('calls a store measurement the storage used', () => {
      expect(sizeLabelKey('storage_used')).toBe('repositoryStats.storageUsed')
    })

    it('falls back to the repository size for an unknown source', () => {
      expect(sizeLabelKey(null)).toBe('repositoryStats.repositorySize')
      expect(sizeLabelKey(undefined)).toBe('repositoryStats.repositorySize')
    })
  })

  describe('grid variant (archive header)', () => {
    it('shows the Borg 1 figures with the compressed size as fourth tile', () => {
      render(<RepositoryStats storage={borg1} borgVersion={1} archiveCount={21} />)

      expect(stat('archives')).toHaveTextContent('21')
      expect(stat('size')).toHaveTextContent('Deduplicated Size')
      expect(stat('size')).toHaveTextContent('2.40 TB')
      expect(stat('originalSize')).toHaveTextContent('18.68 TB')
      expect(stat('compressedSize')).toHaveTextContent('16.18 TB')
      expect(screen.queryByTestId('repository-stat-latestArchiveFiles')).not.toBeInTheDocument()
    })

    it('shows the Borg 2 figures with the newest archive files as fourth tile', () => {
      render(<RepositoryStats storage={borg2} borgVersion={2} archiveCount={35} />)

      expect(stat('size')).toHaveTextContent('Repository Size')
      expect(stat('size')).toHaveTextContent('2.35 GB')
      expect(stat('originalSize')).toHaveTextContent('10.67 GB')
      expect(stat('latestArchiveFiles')).toHaveTextContent('3,157')
      expect(screen.queryByTestId('repository-stat-compressedSize')).not.toBeInTheDocument()
    })

    it('never renders 0 B for a size that was not measured', () => {
      render(<RepositoryStats storage={unknown} borgVersion={2} archiveCount={0} />)

      expect(stat('size')).toHaveAttribute('data-state', 'unknown')
      expect(stat('size')).toHaveTextContent('Unknown')
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
    })

    it('renders a measured 0 as 0 B', () => {
      render(
        <RepositoryStats
          storage={{ ...borg1, size_bytes: 0, original_size: 0, compressed_size: 0 }}
          borgVersion={1}
          archiveCount={0}
        />
      )

      expect(stat('size')).toHaveAttribute('data-state', 'value')
      expect(stat('size')).toHaveTextContent('0 B')
    })

    it('treats a missing payload as unknown, not as zero', () => {
      render(<RepositoryStats storage={undefined} borgVersion={1} archiveCount={3} />)

      expect(stat('archives')).toHaveTextContent('3')
      expect(stat('size')).toHaveAttribute('data-state', 'unknown')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'unknown')
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
    })

    it('withholds the archive figures while the rows and the count disagree', () => {
      render(
        <RepositoryStats
          storage={{ ...borg2, archives_consistent: false, original_size: null }}
          borgVersion={2}
          archiveCount={36}
        />
      )

      expect(stat('size')).toHaveTextContent('2.35 GB')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'withheld')
      expect(stat('originalSize')).toHaveTextContent('Pending')
    })

    it('shows unknown, not pending, for a repository no listing has ever reached', () => {
      render(
        <RepositoryStats
          storage={{
            ...borg2,
            archives_consistent: false,
            archives_listed: false,
            original_size: null,
          }}
          borgVersion={2}
          archiveCount={0}
        />
      )

      expect(stat('originalSize')).toHaveAttribute('data-state', 'unknown')
      expect(stat('originalSize')).toHaveTextContent('Unknown')
    })

    it('says indexing while the post-import chain has produced nothing yet', () => {
      render(
        <RepositoryStats
          storage={unknown}
          borgVersion={2}
          archiveCount={0}
          indexPendingKinds={['stats', 'archive_sync']}
        />
      )

      expect(stat('archives')).toHaveAttribute('data-state', 'indexing')
      expect(stat('archives')).toHaveTextContent('Indexing…')
      expect(stat('size')).toHaveAttribute('data-state', 'indexing')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'indexing')
    })

    it('keeps a settled repository at unknown, not indexing, for sums the list omits', () => {
      // the list's stand-in columns carry no sums; a queued routine listing
      // must not turn that into a promise
      render(
        <RepositoryStats
          storage={{ ...borg2, original_size: null, latest_archive_files: null }}
          borgVersion={2}
          archiveCount={35}
          indexPendingKinds={['archive_sync']}
        />
      )

      expect(stat('originalSize')).toHaveAttribute('data-state', 'unknown')
      expect(stat('latestArchiveFiles')).toHaveAttribute('data-state', 'unknown')
    })

    it('keeps a settled empty repository at 0 while a routine listing waits', () => {
      render(
        <RepositoryStats
          storage={{ ...borg1, archives_listed: true, original_size: 0, compressed_size: 0 }}
          borgVersion={1}
          archiveCount={0}
          indexPendingKinds={['archive_sync', 'stats']}
        />
      )

      expect(stat('archives')).toHaveAttribute('data-state', 'value')
      expect(stat('archives')).toHaveTextContent('0')
    })

    it('tells a pending size from archives that are already listed', () => {
      render(
        <RepositoryStats
          storage={{ ...borg2, size_bytes: null, size_source: null, measured_at: null }}
          borgVersion={2}
          archiveCount={35}
          indexPendingKinds={['stats']}
        />
      )

      expect(stat('archives')).toHaveTextContent('35')
      expect(stat('size')).toHaveAttribute('data-state', 'indexing')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'value')
    })

    it('shows the archive count as unknown when the stored list could not be read', () => {
      render(<RepositoryStats storage={borg1} borgVersion={1} archiveCount={null} />)

      expect(stat('archives')).toHaveAttribute('data-state', 'unknown')
      expect(stat('archives')).not.toHaveTextContent('0')
    })

    it('does not show a zero archive count while the archives are loading', () => {
      render(<RepositoryStats storage={borg1} borgVersion={1} archiveCount={0} archivesLoading />)

      expect(stat('archives')).not.toHaveTextContent('0')
    })
  })

  describe('detail variant (info dialog)', () => {
    it('shows the same rows on Borg 2 with the compressed size as not reported', () => {
      render(<RepositoryStats variant="detail" storage={borg2} borgVersion={2} />)

      expect(screen.getByText('Storage Statistics')).toBeInTheDocument()
      expect(stat('compressedSize')).toHaveAttribute('data-state', 'not_reported')
      expect(stat('compressedSize')).toHaveTextContent('Not reported by Borg 2')
      expect(stat('deduplicatedSize')).toHaveTextContent('2.14 GB')
      expect(stat('latestArchiveFiles')).toHaveTextContent('3,157')
    })

    it('does not promise a Borg 2 deduplicated size from a listing', () => {
      render(
        <RepositoryStats
          variant="detail"
          storage={{ ...borg2, deduplicated_size: null, compact: null, compact_at: null }}
          borgVersion={2}
          indexPendingKinds={['archive_sync']}
        />
      )

      expect(stat('deduplicatedSize')).toHaveAttribute('data-state', 'unknown')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'value')
    })

    it('shows a stored compressed size on Borg 2 rather than calling it not reported', () => {
      render(
        <RepositoryStats
          variant="detail"
          storage={{ ...borg2, compressed_size: 1_000_000 }}
          borgVersion={2}
        />
      )

      expect(stat('compressedSize')).toHaveAttribute('data-state', 'value')
      expect(stat('compressedSize')).toHaveTextContent('976.56 KB')
    })

    it('shows the Borg 1 deduplicated size once, as the stored size', () => {
      render(<RepositoryStats variant="detail" storage={borg1} borgVersion={1} />)

      expect(stat('size')).toHaveTextContent('Deduplicated Size')
      expect(screen.queryByTestId('repository-stat-deduplicatedSize')).not.toBeInTheDocument()
      expect(stat('compressedSize')).toHaveTextContent('16.18 TB')
    })

    it('shows the newest compact statistics with their time and rounding', () => {
      render(<RepositoryStats variant="detail" storage={borg2} borgVersion={2} />)

      const block = screen.getByTestId('repository-stats-compact')
      expect(block).toHaveTextContent('Last Compact')
      expect(screen.getByTestId('repository-stat-compact-sourceSize')).toHaveTextContent('10.67 GB')
      expect(screen.getByTestId('repository-stat-compact-compressionFactor')).toHaveTextContent(
        '1.42×'
      )
      expect(screen.getByTestId('repository-stat-compact-saved')).toHaveTextContent('175.48 MB')
      expect(block).toHaveTextContent(/rounded/i)
    })

    it('renders no empty caption when the compact carries neither a time nor a rounding', () => {
      render(
        <RepositoryStats
          variant="detail"
          storage={{
            ...borg2,
            compact_at: null,
            compact: { ...borg2.compact, size_precision: 'exact' },
          }}
          borgVersion={2}
        />
      )

      const block = screen.getByTestId('repository-stats-compact')
      expect(block).toHaveTextContent('Last Compact')
      expect(block).not.toHaveTextContent(/rounded|Compacted/i)
    })

    it('shows no compact block without compact statistics', () => {
      render(<RepositoryStats variant="detail" storage={borg1} borgVersion={1} />)

      expect(screen.queryByTestId('repository-stats-compact')).not.toBeInTheDocument()
    })
  })

  describe('repositoryStatItems', () => {
    it('carries provenance and measurement time in the size hint', () => {
      const size = repositoryStatItems(t, { storage: borg2, borgVersion: 2 }).find(
        (item) => item.key === 'size'
      )!
      expect(size.hint).toContain('chunk index')
      expect(size.hint).toMatch(/Measured /)
    })

    it('says the measurement time is unknown for a backfilled size', () => {
      const size = repositoryStatItems(t, {
        storage: { ...borg1, measured_at: null },
        borgVersion: 1,
      }).find((item) => item.key === 'size')!
      expect(size.state).toBe('value')
      expect(size.hint).toContain('Measurement time unknown')
    })

    it('renders each non-value state as its own text', () => {
      const item = { key: 'x', label: 'x', value: null }
      expect(stateText(t, { ...item, state: 'unknown' }, 1)).toBe('Unknown')
      expect(stateText(t, { ...item, state: 'not_reported' }, 2)).toBe('Not reported by Borg 2')
      expect(stateText(t, { ...item, state: 'withheld' }, 1)).toBe('Pending')
      expect(stateText(t, { ...item, state: 'indexing' }, 1)).toBe('Indexing…')
    })
  })
})
