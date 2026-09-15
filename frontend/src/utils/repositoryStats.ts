import type { TFunction } from 'i18next'
import type { RepositoryStorage } from '../types'
import { formatBytes, formatDateTimeFull } from './dateUtils'

/**
 * One reading of a repository's stored size figures (#981), shared by the
 * card, the archive header and the info dialog so they never disagree
 * about a number or about the absence of one.
 *
 * Every figure has one of these states:
 *
 * - `value`: a measurement, `0` included (an emptied repository measures 0).
 * - `unknown`: not measured yet; never rendered as `0 B`.
 * - `not_reported`: this Borg version does not produce the figure (the
 *   compressed size on Borg 2). The row stays, so both versions show the
 *   same rows.
 * - `withheld`: the archive sums are held back while the archive rows and
 *   the archive count disagree (a listing is catching up).
 * - `indexing`: the post-import chain (#1063) has not produced the figure
 *   yet; the placeholder says so instead of looking like an empty repository.
 */
export type RepositoryStatState = 'value' | 'unknown' | 'not_reported' | 'withheld' | 'indexing'

export interface RepositoryStatItem {
  key: string
  label: string
  state: RepositoryStatState
  /** The rendered value; set for `value` only. */
  value: string | null
  /** Tooltip text: provenance and time for a value, the reason otherwise. */
  hint?: string
}

export type RepositoryStatsVariant = 'grid' | 'detail'

export interface RepositoryStatsInput {
  /** The `storage` object of a repository response; `null` when the server
   * could not compute it, `undefined` while it has not been loaded. */
  storage: RepositoryStorage | null | undefined
  borgVersion?: number
  /** The card's archive count (grid variant only). */
  archiveCount?: number | null
  /** Index work queued or running for the repository (#1063). */
  indexPendingKinds?: string[] | null
  variant?: RepositoryStatsVariant
}

type SizeSource = RepositoryStorage['size_source']

const SOURCE_LABEL_KEY: Record<string, string> = {
  borg1_cache_stats: 'repositoryStats.deduplicatedSize',
  borg2_index: 'repositoryStats.repositorySize',
  compact_stats: 'repositoryStats.repositorySize',
  storage_used: 'repositoryStats.storageUsed',
}

/** The quantity a stored size is, named by its source: Borg 1's cache
 * statistics measure the deduplicated size, the Borg 2 index and the
 * compact statistics the repository size, a store tool the bytes used. */
export function sizeLabelKey(source: SizeSource | undefined): string {
  return (source && SOURCE_LABEL_KEY[source]) || 'repositoryStats.repositorySize'
}

function sourceHint(t: TFunction, source: SizeSource | undefined): string | undefined {
  if (!source) return undefined
  const key = `repositoryStats.source.${source}`
  const text = t(key)
  return text === key ? undefined : text
}

function measuredHint(t: TFunction, storage: RepositoryStorage): string {
  return storage.measured_at
    ? t('repositoryStats.measuredAt', { time: formatDateTimeFull(storage.measured_at) })
    : t('repositoryStats.measuredTimeUnknown')
}

function joinHints(...parts: Array<string | undefined>): string | undefined {
  const text = parts.filter(Boolean).join('. ')
  return text || undefined
}

interface ItemContext {
  t: TFunction
  storage: RepositoryStorage | null | undefined
  borgVersion: number
  pending: Set<string>
}

/** The stored size, as the card, the header and the dialog all show it. */
function sizeStatItem(ctx: ItemContext): RepositoryStatItem {
  const { t, storage, pending } = ctx
  const label = t(sizeLabelKey(storage?.size_source))
  if (storage && storage.size_bytes !== null && storage.size_bytes !== undefined) {
    return {
      key: 'size',
      label,
      state: 'value',
      value: formatBytes(storage.size_bytes),
      hint: joinHints(sourceHint(t, storage.size_source), measuredHint(t, storage)),
    }
  }
  if (pending.has('stats')) {
    return {
      key: 'size',
      label,
      state: 'indexing',
      value: null,
      hint: t('repositoryStats.indexingSizeHint'),
    }
  }
  return {
    key: 'size',
    label,
    state: 'unknown',
    value: null,
    hint: t('repositoryStats.unknownHint'),
  }
}

/** A figure summed over the archive rows: a value, or the reason it is
 * missing (withheld while the rows catch up, indexing after an import,
 * not reported by this Borg version, else not measured). */
function archiveFigureItem(
  ctx: ItemContext,
  key: string,
  labelKey: string,
  raw: number | null | undefined,
  hintKey: string,
  options: {
    notReportedOnBorg2?: boolean
    format?: (value: number) => string
    /** false for a figure no listing produces (the Borg 2 deduplicated
     * size comes from a compact): pending or withheld archive rows say
     * nothing about it, so it is unknown until it exists. */
    fromArchives?: boolean
  } = {}
): RepositoryStatItem {
  const { t, storage, borgVersion, pending } = ctx
  const label = t(labelKey)
  // a stored figure is shown whatever the version: the "not reported"
  // state names the absence of one, not the version
  if (raw !== null && raw !== undefined) {
    const format = options.format ?? formatBytes
    return { key, label, state: 'value', value: format(raw), hint: t(hintKey) }
  }
  if (options.notReportedOnBorg2 && borgVersion === 2) {
    return {
      key,
      label,
      state: 'not_reported',
      value: null,
      hint: t('repositoryStats.notReportedHint', { version: 2 }),
    }
  }
  if (options.fromArchives === false) {
    return { key, label, state: 'unknown', value: null, hint: t('repositoryStats.unknownHint') }
  }
  // A listing under way is the more specific reason than rows and count
  // disagreeing: after an import both hold, and "indexing" is what is
  // happening. Only for a repository no listing has reached, though: a
  // settled one keeps what it has (the list's stand-in columns carry no
  // sums) while a routine listing waits.
  if (archivesMayArrive(storage, pending)) {
    return {
      key,
      label,
      state: 'indexing',
      value: null,
      hint: t('repositoryStats.indexingArchivesHint'),
    }
  }
  // "pending" promises a catch-up, so it is said only for a repository a
  // listing has reached; one no listing has ever produced rows for is
  // unknown, however the rows and the count compare
  if (storage?.archives_consistent === false && storage.archives_listed === true) {
    return { key, label, state: 'withheld', value: null, hint: t('repositoryStats.pendingHint') }
  }
  return { key, label, state: 'unknown', value: null, hint: t('repositoryStats.unknownHint') }
}

/** Whether a listing under way may still produce a count or a last
 * backup: a repository a listing has already reached and found empty is
 * settled, and its 0 or "never" stands while a routine listing waits. */
export function archivesMayArrive(
  storage: RepositoryStorage | null | undefined,
  pending: Set<string>
): boolean {
  return pending.has('archive_sync') && storage?.archives_listed !== true
}

function archivesStatItem(
  ctx: ItemContext,
  archiveCount: number | null | undefined
): RepositoryStatItem {
  const { t, storage, pending } = ctx
  const label = t('repositoryStats.archives')
  if (!archiveCount && archivesMayArrive(storage, pending)) {
    return {
      key: 'archives',
      label,
      state: 'indexing',
      value: null,
      hint: t('repositoryStats.indexingArchivesHint'),
    }
  }
  // no count at all (the stored list could not be read) is not zero
  if (archiveCount === null || archiveCount === undefined) {
    return {
      key: 'archives',
      label,
      state: 'unknown',
      value: null,
      hint: t('repositoryStats.unknownHint'),
    }
  }
  return {
    key: 'archives',
    label,
    state: 'value',
    value: String(archiveCount),
  }
}

/**
 * The rows of one variant. The grid (archive header) shows four tiles:
 * archives, the stored size, the archive data and, per version, the
 * compressed size (Borg 1) or the newest archive's files (Borg 2). The
 * detail (info dialog) shows every figure, with the same rows on both
 * versions.
 */
export function repositoryStatItems(
  t: TFunction,
  input: RepositoryStatsInput
): RepositoryStatItem[] {
  const borgVersion = input.borgVersion === 2 ? 2 : 1
  const pending = new Set(input.indexPendingKinds ?? [])
  const ctx: ItemContext = { t, storage: input.storage, borgVersion, pending }
  const storage = input.storage
  const size = sizeStatItem(ctx)
  const original = archiveFigureItem(
    ctx,
    'originalSize',
    'repositoryStats.originalSize',
    storage?.original_size,
    'repositoryStats.originalSizeHint'
  )
  const compressed = archiveFigureItem(
    ctx,
    'compressedSize',
    'repositoryStats.compressedSize',
    storage?.compressed_size,
    'repositoryStats.compressedSizeHint',
    { notReportedOnBorg2: true }
  )
  const deduplicated = archiveFigureItem(
    ctx,
    'deduplicatedSize',
    'repositoryStats.deduplicatedSize',
    storage?.deduplicated_size,
    'repositoryStats.deduplicatedSizeHint',
    // neither version's deduplicated size comes from a listing: Borg 1's is
    // the stored cache figure, Borg 2's the newest compact's
    { fromArchives: false }
  )
  const files = archiveFigureItem(
    ctx,
    'latestArchiveFiles',
    'repositoryStats.latestArchiveFiles',
    storage?.latest_archive_files,
    'repositoryStats.latestArchiveFilesHint',
    { format: (value) => value.toLocaleString() }
  )
  if (input.variant === 'detail') {
    // Borg 1's deduplicated size is the stored size itself; the dialog
    // shows it once, under the name the source gives it.
    const rows = [size, original, compressed]
    // A Borg 1 payload almost always names the stored size deduplicated, so
    // the separate row is left out while the payload is still loading or
    // absent too: otherwise the dialog opens with five rows and drops to four.
    const deduplicatedIsTheSize =
      storage?.size_source === 'borg1_cache_stats' || (borgVersion === 1 && storage == null)
    if (!deduplicatedIsTheSize) rows.push(deduplicated)
    rows.push(files)
    return rows
  }
  return [
    archivesStatItem(ctx, input.archiveCount),
    size,
    original,
    borgVersion === 2 ? files : compressed,
  ]
}

/** The text a stat renders: its value, or the name of its state. */
export function stateText(t: TFunction, item: RepositoryStatItem, borgVersion: number): string {
  switch (item.state) {
    case 'value':
      return item.value ?? ''
    case 'unknown':
      return t('repositoryStats.unknown')
    case 'not_reported':
      return t('repositoryStats.notReported', { version: borgVersion })
    case 'withheld':
      return t('repositoryStats.pending')
    case 'indexing':
      return t('repositoryStats.indexing')
  }
}
