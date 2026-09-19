import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import i18n from 'i18next'
import RepositoryStats from '../RepositoryStats'
import { repositoryStatItems, stateText, statsUpdatedAt } from '../../utils/repositoryStats'
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
  first_backup_at: '2026-03-12T02:00:14.000Z',
  last_backup_at: '2026-09-09T02:00:11.000Z',
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
  first_backup_at: '2026-08-19T18:03:15.000Z',
  last_backup_at: '2026-09-14T05:46:44.000Z',
  compact: null,
  compact_at: null,
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
  first_backup_at: null,
  last_backup_at: null,
  compact: null,
  compact_at: null,
}

const t = i18n.t.bind(i18n)

function stat(key: string) {
  return screen.getByTestId(`repository-stat-${key}`)
}

function keys(items: { key: string }[]) {
  return items.map((item) => item.key)
}

describe('RepositoryStats', () => {
  describe('the field set', () => {
    it('shows the same four tiles in the header on both versions', () => {
      const one = repositoryStatItems(t, { storage: borg1, archiveCount: 21 })
      const two = repositoryStatItems(t, { storage: borg2, archiveCount: 36 })
      expect(keys(one)).toEqual(['archives', 'originalSize', 'usedOnDisk', 'spaceSaved'])
      expect(keys(two)).toEqual(keys(one))
    })

    it('shows the same six cards in the dialog on both versions', () => {
      const one = repositoryStatItems(t, { storage: borg1, archiveCount: 21, variant: 'detail' })
      const two = repositoryStatItems(t, { storage: borg2, archiveCount: 36, variant: 'detail' })
      expect(keys(one)).toEqual([
        'originalSize',
        'usedOnDisk',
        'spaceSaved',
        'archives',
        'backupSpan',
        'latestArchiveFiles',
      ])
      expect(keys(two)).toEqual(keys(one))
    })

    it('labels the stored size used on disk whatever its source', () => {
      for (const storage of [borg1, borg2, { ...borg2, size_source: 'storage_used' }]) {
        const [, used] = repositoryStatItems(t, { storage, variant: 'detail' })
        expect(used.label).toBe('Used on Disk')
      }
    })
  })

  describe('the free space action', () => {
    it('sits in the used-on-disk tile and links to the prune preview', () => {
      renderWithProviders(
        <RepositoryStats
          storage={borg1}
          archiveCount={21}
          freeSpaceHref="/repositories/1/prune-preview"
        />
      )
      const link = screen.getByRole('link', { name: /free space/i })
      expect(link).toHaveAttribute('href', '/repositories/1/prune-preview')
      expect(stat('usedOnDisk')).toContainElement(link)
    })

    it('is absent without a target', () => {
      renderWithProviders(<RepositoryStats storage={borg1} archiveCount={21} />)
      expect(screen.queryByRole('link', { name: /free space/i })).not.toBeInTheDocument()
    })
  })

  describe('the values', () => {
    it('renders the Borg 1 figures', () => {
      render(<RepositoryStats storage={borg1} archiveCount={21} variant="detail" />)
      expect(stat('originalSize')).toHaveTextContent('18.68 TB')
      expect(stat('usedOnDisk')).toHaveTextContent('2.40 TB')
      expect(stat('spaceSaved')).toHaveTextContent('7.78×')
      expect(stat('archives')).toHaveTextContent('21')
      expect(stat('backupSpan')).toHaveTextContent('to')
      expect(stat('latestArchiveFiles')).toHaveTextContent('566,220')
    })

    it('renders the Borg 2 figures the same way', () => {
      render(<RepositoryStats storage={borg2} archiveCount={36} variant="detail" />)
      expect(stat('usedOnDisk')).toHaveTextContent('2.35 GB')
      expect(stat('spaceSaved')).toHaveTextContent('4.54×')
      expect(screen.queryByText(/not reported/i)).not.toBeInTheDocument()
    })

    it('shows a single date when the span is one archive', () => {
      const [, , , , span] = repositoryStatItems(t, {
        storage: { ...borg2, first_backup_at: borg2.last_backup_at },
        variant: 'detail',
      })
      expect(span.state).toBe('value')
      expect(span.value).not.toContain(' to ')
    })

    it('shows no ratio for 0 B of source data over what is still on disk', () => {
      const [, , saved] = repositoryStatItems(t, {
        storage: { ...borg1, original_size: 0 },
        variant: 'detail',
      })
      expect(saved.state).toBe('unknown')
    })

    it('renders a measured 0 as 0 B and no ratio for an emptied repository', () => {
      render(
        <RepositoryStats
          storage={{ ...borg1, size_bytes: 0, original_size: 0, latest_archive_files: 0 }}
          archiveCount={0}
          variant="detail"
        />
      )
      expect(stat('originalSize')).toHaveTextContent('0 B')
      expect(stat('usedOnDisk')).toHaveTextContent('0 B')
      expect(stat('spaceSaved')).toHaveAttribute('data-state', 'unknown')
    })
  })

  describe('the states', () => {
    it('never renders 0 B for a size that was not measured', () => {
      render(<RepositoryStats storage={unknown} archiveCount={0} />)
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
      expect(stat('usedOnDisk')).toHaveAttribute('data-state', 'unknown')
      expect(stat('originalSize')).toHaveAttribute('data-state', 'unknown')
      expect(stat('spaceSaved')).toHaveAttribute('data-state', 'unknown')
      expect(stat('archives')).toHaveTextContent('0')
    })

    it('treats a missing payload as unknown, not as zero', () => {
      render(<RepositoryStats storage={undefined} variant="detail" />)
      expect(screen.getAllByText('Unknown')).toHaveLength(6)
      expect(screen.queryByText('0 B')).not.toBeInTheDocument()
    })

    it('withholds the archive figures while the rows and the count disagree', () => {
      render(
        <RepositoryStats
          storage={{
            ...borg2,
            archives_consistent: false,
            original_size: null,
            latest_archive_files: null,
            first_backup_at: null,
            last_backup_at: null,
          }}
          archiveCount={37}
          variant="detail"
        />
      )
      expect(stat('originalSize')).toHaveAttribute('data-state', 'withheld')
      expect(stat('originalSize')).toHaveTextContent('Pending')
      expect(stat('spaceSaved')).toHaveAttribute('data-state', 'withheld')
      expect(stat('backupSpan')).toHaveAttribute('data-state', 'withheld')
      // the stored size stands: it is not an archive figure
      expect(stat('usedOnDisk')).toHaveTextContent('2.35 GB')
    })

    it('shows unknown, not pending, for a repository no listing has ever reached', () => {
      render(<RepositoryStats storage={unknown} archiveCount={0} variant="detail" />)
      expect(stat('originalSize')).toHaveAttribute('data-state', 'unknown')
      expect(screen.queryByText('Pending')).not.toBeInTheDocument()
    })

    it('says indexing while the post-import chain has produced nothing yet', () => {
      render(
        <RepositoryStats
          storage={unknown}
          archiveCount={0}
          indexPendingKinds={['stats', 'archive_sync', 'history_index']}
          variant="detail"
        />
      )
      for (const key of [
        'originalSize',
        'usedOnDisk',
        'spaceSaved',
        'archives',
        'backupSpan',
        'latestArchiveFiles',
      ]) {
        expect(stat(key)).toHaveAttribute('data-state', 'indexing')
      }
      expect(screen.getAllByText('Indexing…')).toHaveLength(6)
    })

    it('keeps a settled empty repository at 0 while a routine listing waits', () => {
      render(
        <RepositoryStats
          storage={{ ...borg2, archives_listed: true }}
          archiveCount={0}
          indexPendingKinds={['archive_sync']}
        />
      )
      expect(stat('archives')).toHaveTextContent('0')
      expect(screen.queryByText('Indexing…')).not.toBeInTheDocument()
    })

    it('tells a pending size from archives that are already listed', () => {
      render(
        <RepositoryStats
          storage={{ ...borg2, size_bytes: null, size_source: null, measured_at: null }}
          archiveCount={36}
          indexPendingKinds={['stats']}
        />
      )
      expect(stat('usedOnDisk')).toHaveAttribute('data-state', 'indexing')
      expect(stat('originalSize')).toHaveTextContent('10.67 GB')
      // the ratio waits for the size
      expect(stat('spaceSaved')).toHaveAttribute('data-state', 'indexing')
    })

    it('shows the archive count as unknown when the stored list could not be read', () => {
      render(<RepositoryStats storage={borg2} archiveCount={null} />)
      expect(stat('archives')).toHaveAttribute('data-state', 'unknown')
    })

    it('does not show a zero archive count while the archives are loading', () => {
      render(<RepositoryStats storage={borg2} archiveCount={0} archivesLoading />)
      expect(stat('archives')).not.toHaveTextContent('0')
    })

    it('renders each non-value state as its own text', () => {
      const item = { key: 'x', label: 'x', value: null, tone: 'neutral' as const }
      expect(stateText(t, { ...item, state: 'unknown' })).toBe('Unknown')
      expect(stateText(t, { ...item, state: 'withheld' })).toBe('Pending')
      expect(stateText(t, { ...item, state: 'indexing' })).toBe('Indexing…')
      expect(stateText(t, { ...item, state: 'value', value: '1 B' })).toBe('1 B')
    })
  })

  describe('statsUpdatedAt', () => {
    it('takes the older stamp and reads a naive one as UTC', () => {
      const storage = { ...borg1, measured_at: '2026-09-18T12:32:24' }
      expect(statsUpdatedAt(storage, '2026-09-18T12:30:36.750342')).toBe('2026-09-18T12:30:36.750Z')
      expect(statsUpdatedAt(storage, null)).toBe('2026-09-18T12:32:24.000Z')
      expect(statsUpdatedAt({ ...borg1, measured_at: null }, null)).toBeNull()
    })
  })

  describe('the hints', () => {
    it('carries the provenance in the size hint and no time of its own', () => {
      const [, used] = repositoryStatItems(t, { storage: borg2, variant: 'detail' })
      expect(used.hint).toContain('chunk index')
      expect(used.subtitle).toBeUndefined()
    })

    it('names the ratio as both factors together', () => {
      const [, , saved] = repositoryStatItems(t, { storage: borg2, variant: 'detail' })
      expect(saved.hint).toMatch(/deduplication and compression/i)
    })
  })
})
