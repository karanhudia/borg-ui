import type { RepositoryStorage } from '../types'

/**
 * Stored `storage` payloads for stories and tests. Kept out of the story
 * files: Storybook reads every named export of a CSF module as a story.
 */

/** A Borg 1 repository after a `stats` run: cache statistics give the
 * deduplicated size, the archive rows give the sums. */
export const borg1Storage: RepositoryStorage = {
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

/** A Borg 2 repository on a store URL: the chunk index gives the size,
 * the newest compact its statistics; no compressed size exists. */
export const borg2Storage: RepositoryStorage = {
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
    source_files: 3157,
    compression_factor: 1.42,
    deduplication_factor: 4.98,
    compaction_saved: 184_000_000,
    size_precision: 'rounded',
  },
  compact_at: '2026-09-14T04:48:36.000Z',
}

/** Nothing measured yet: a repository whose first `stats` run has not
 * completed and whose archive rows have not been listed. */
export const unknownStorage: RepositoryStorage = {
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

/** The size came back from the upgrade's backfill of the formatted string:
 * a value, but no measurement time. */
export const backfilledStorage: RepositoryStorage = {
  ...borg1Storage,
  measured_at: null,
}

/** The archive rows and the archive count disagree between a backup and
 * its `archive_sync`: the sums are withheld, the size stands. */
export const withheldStorage: RepositoryStorage = {
  ...borg2Storage,
  archives_consistent: false,
  original_size: null,
  latest_archive_files: null,
}
