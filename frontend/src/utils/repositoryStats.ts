import type { TFunction } from 'i18next'
import type { RepositoryStorage } from '../types'
import { formatBytes, formatDateShort, parseBackendDate } from './dateUtils'

/**
 * One reading of a repository's stored size figures (#981), shared by the
 * card, the archive header and the info dialog so they never disagree
 * about a number or about the absence of one.
 *
 * Every figure has one of these states:
 *
 * - `value`: a measurement, `0` included (an emptied repository measures 0).
 * - `unknown`: not measured yet; never rendered as `0 B`.
 * - `withheld`: the archive figures are held back while the archive rows
 *   and the archive count disagree (a listing is catching up).
 * - `indexing`: the post-import chain (#1063) has not produced the figure
 *   yet; the placeholder says so instead of looking like an empty repository.
 */
export type RepositoryStatState = 'value' | 'unknown' | 'withheld' | 'indexing'

/** The hue a figure carries: what you have, what it costs, what you gained. */
export type RepositoryStatTone = 'info' | 'warning' | 'success' | 'neutral'

export interface RepositoryStatItem {
  key: string
  label: string
  state: RepositoryStatState
  /** The rendered value; set for `value` only. */
  value: string | null
  /** Tooltip text: provenance for a value, the reason otherwise. */
  hint?: string
  /** A line under the value (the size's measurement time and source). */
  subtitle?: string
  tone: RepositoryStatTone
}

export type RepositoryStatsVariant = 'grid' | 'detail'

export interface RepositoryStatsInput {
  /** The `storage` object of a repository response; `null` when the server
   * could not compute it, `undefined` while it has not been loaded. */
  storage: RepositoryStorage | null | undefined
  /** The archive count the caller knows (the card's column, the list's
   * length); `null` when it could not be read. */
  archiveCount?: number | null
  /** Index work queued or running for the repository (#1063). */
  indexPendingKinds?: string[] | null
  variant?: RepositoryStatsVariant
}

/** A provenance label the backend sends: where a size came from. */
type FigureSource = RepositoryStorage['size_source' | 'original_size_source']

function sourceText(t: TFunction, source: FigureSource | undefined, prefix: string) {
  if (!source) return undefined
  const key = `${prefix}.${source}`
  const text = t(key)
  return text === key ? undefined : text
}

/** The stamp the panel's "Updated" caption shows: the oldest of the
 * stamps behind the figures on screen, so it never overstates. Those are
 * the size measurement, the archive listing, and the run that reported
 * the source data size where Borg reported it for the whole repository
 * (`original_size_at`) — the last compact, or a `stats` run older than
 * the one that wrote the size. Null when none of them has happened.
 * Returned with its zone: the backend sends naive UTC, which `new Date`
 * would read as local time. */
export function statsUpdatedAt(
  storage: RepositoryStorage | null | undefined,
  lastSyncedAt: string | null | undefined
): string | null {
  const stamps = [storage?.measured_at, lastSyncedAt, storage?.original_size_at]
    .filter((s): s is string => !!s)
    .map((s) => parseBackendDate(s))
  if (stamps.length === 0) return null
  return stamps.reduce((a, b) => (a <= b ? a : b)).toISOString()
}

/** Whether the figures are being produced right now: a listing or a size
 * measurement queued or running. */
export function statsUpdating(
  indexPendingKinds: string[] | null | undefined,
  syncState?: string
): boolean {
  const pending = indexPendingKinds ?? []
  return syncState === 'syncing' || pending.includes('stats') || pending.includes('archive_sync')
}

interface ItemContext {
  t: TFunction
  storage: RepositoryStorage | null | undefined
  pending: Set<string>
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

/** The state of a figure summed over the archive rows that is missing:
 * indexing after an import, withheld while the rows catch up, else not
 * measured. */
function archiveFigureState(ctx: ItemContext): RepositoryStatState {
  const { storage, pending } = ctx
  // A listing under way is the more specific reason than rows and count
  // disagreeing: after an import both hold, and "indexing" is what is
  // happening. Only for a repository no listing has reached, though: a
  // settled one keeps what it has while a routine listing waits.
  if (archivesMayArrive(storage, pending)) return 'indexing'
  // "pending" promises a catch-up, so it is said only for a repository a
  // listing has reached; one no listing has ever produced rows for is
  // unknown, however the rows and the count compare
  if (storage?.archives_consistent === false && storage.archives_listed === true) {
    return 'withheld'
  }
  return 'unknown'
}

function placeholderHint(t: TFunction, state: RepositoryStatState, sizeFigure = false) {
  switch (state) {
    case 'indexing':
      return t(
        sizeFigure ? 'repositoryStats.indexingSizeHint' : 'repositoryStats.indexingArchivesHint'
      )
    case 'withheld':
      return t('repositoryStats.pendingHint')
    default:
      return t('repositoryStats.unknownHint')
  }
}

function usedOnDiskItem(ctx: ItemContext): RepositoryStatItem {
  const { t, storage, pending } = ctx
  const label = t('repositoryStats.usedOnDisk')
  const tone: RepositoryStatTone = 'warning'
  if (storage && storage.size_bytes !== null && storage.size_bytes !== undefined) {
    return {
      key: 'usedOnDisk',
      label,
      state: 'value',
      value: formatBytes(storage.size_bytes),
      hint: sourceText(t, storage.size_source, 'repositoryStats.sourceHint'),
      tone,
    }
  }
  const state: RepositoryStatState = pending.has('stats') ? 'indexing' : 'unknown'
  return {
    key: 'usedOnDisk',
    label,
    state,
    value: null,
    hint: placeholderHint(t, state, true),
    tone,
  }
}

function originalSizeItem(ctx: ItemContext): RepositoryStatItem {
  const { t, storage } = ctx
  const label = t('repositoryStats.originalSize')
  const tone: RepositoryStatTone = 'info'
  if (storage?.original_size !== null && storage?.original_size !== undefined) {
    return {
      key: 'originalSize',
      label,
      state: 'value',
      value: formatBytes(storage.original_size),
      // the figure Borg reports for the whole repository, or the sum over
      // the archive rows where it reports none: the tile says which. A
      // payload that names no source predates the distinction, and its
      // figure was the sum; one that names an unknown source says nothing
      // rather than the wrong thing.
      hint: storage.original_size_source
        ? sourceText(t, storage.original_size_source, 'repositoryStats.originalSizeHint')
        : t('repositoryStats.originalSizeHint.archives'),
      tone,
    }
  }
  const state = archiveFigureState(ctx)
  return { key: 'originalSize', label, state, value: null, hint: placeholderHint(t, state), tone }
}

/** Whether the two sides of the ratio describe one state of the
 * repository. The archive index and the stored size are each refreshed
 * after every change this application makes, so dividing one by the other
 * is what the ratio has always been; a payload that names no source
 * predates the distinction and carried that figure. A figure Borg
 * reported for the whole repository is a different matter, and neither
 * the two labels nor the order of the two stamps proves it belongs with
 * the size: a compact can write the size without reporting a source data
 * size, and a `stats` run can report the source data size while the size
 * it measured was unavailable. Nothing in the payload settles it, so the
 * ratio waits for the archive index rather than divide across two states.
 */
function fromOneMeasurement(storage: RepositoryStorage): boolean {
  const source = storage.original_size_source
  return !source || source === 'archives'
}

/** Original size over the space used on disk: the two factors multiplied. */
function spaceSavedItem(
  ctx: ItemContext,
  original: RepositoryStatItem,
  used: RepositoryStatItem
): RepositoryStatItem {
  const { t, storage } = ctx
  const label = t('repositoryStats.spaceSaved')
  const tone: RepositoryStatTone = 'success'
  if (storage && original.state === 'value' && used.state === 'value') {
    if (!fromOneMeasurement(storage)) {
      return {
        key: 'spaceSaved',
        label,
        state: 'unknown',
        value: null,
        hint: t('repositoryStats.spaceSavedMixedHint'),
        tone,
      }
    }
    const bytes = storage.size_bytes ?? 0
    // every archive pruned and nothing compacted yet: 0 B of source data
    // over what is still on disk is no saving either
    if (bytes > 0 && storage.original_size !== null && storage.original_size > 0) {
      return {
        key: 'spaceSaved',
        label,
        state: 'value',
        value: `${(storage.original_size / bytes).toFixed(2)}×`,
        hint: t('repositoryStats.spaceSavedHint'),
        tone,
      }
    }
  }
  // the ratio waits for whichever side is still missing; an emptied
  // repository (0 B used, or 0 B of source data) has nothing to divide
  const state: RepositoryStatState =
    original.state === 'value' && used.state === 'value'
      ? 'unknown'
      : original.state !== 'value'
        ? original.state
        : used.state
  return {
    key: 'spaceSaved',
    label,
    state,
    value: null,
    hint:
      state === 'unknown'
        ? t('repositoryStats.spaceSavedUnknownHint')
        : // the side still missing says what is happening: the size being
          // measured, or the archives being read
          placeholderHint(t, state, original.state === 'value'),
    tone,
  }
}

function archivesItem(
  ctx: ItemContext,
  archiveCount: number | null | undefined
): RepositoryStatItem {
  const { t, storage, pending } = ctx
  const label = t('repositoryStats.archives')
  const tone: RepositoryStatTone = 'neutral'
  if (!archiveCount && archivesMayArrive(storage, pending)) {
    return {
      key: 'archives',
      label,
      state: 'indexing',
      value: null,
      hint: t('repositoryStats.indexingArchivesHint'),
      tone,
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
      tone,
    }
  }
  return { key: 'archives', label, state: 'value', value: String(archiveCount), tone }
}

function backupSpanItem(ctx: ItemContext): RepositoryStatItem {
  const { t, storage } = ctx
  const label = t('repositoryStats.backupSpan')
  const tone: RepositoryStatTone = 'neutral'
  if (storage?.first_backup_at && storage.last_backup_at) {
    const first = formatDateShort(storage.first_backup_at)
    const last = formatDateShort(storage.last_backup_at)
    return {
      key: 'backupSpan',
      label,
      state: 'value',
      value: first === last ? first : t('repositoryStats.backupSpanValue', { first, last }),
      hint: t('repositoryStats.backupSpanHint'),
      tone,
    }
  }
  const state = archiveFigureState(ctx)
  return { key: 'backupSpan', label, state, value: null, hint: placeholderHint(t, state), tone }
}

function latestArchiveFilesItem(ctx: ItemContext): RepositoryStatItem {
  const { t, storage } = ctx
  const label = t('repositoryStats.latestArchiveFiles')
  const tone: RepositoryStatTone = 'neutral'
  if (storage?.latest_archive_files !== null && storage?.latest_archive_files !== undefined) {
    return {
      key: 'latestArchiveFiles',
      label,
      state: 'value',
      value: storage.latest_archive_files.toLocaleString(),
      hint: t('repositoryStats.latestArchiveFilesHint'),
      tone,
    }
  }
  const state = archiveFigureState(ctx)
  return {
    key: 'latestArchiveFiles',
    label,
    state,
    value: null,
    hint: placeholderHint(t, state),
    tone,
  }
}

/**
 * The figures of one variant, in the order they are shown. The grid (the
 * archive header) shows four tiles: archives, original size, used on disk
 * and space saved. The detail (the info dialog) shows the three coloured
 * cards, original size, used on disk and space saved, then the outlined
 * ones: archives, backup span and the newest archive's files. The same
 * figures on Borg 1 and Borg 2: what to show is a product decision, not a
 * version's.
 */
export function repositoryStatItems(
  t: TFunction,
  input: RepositoryStatsInput
): RepositoryStatItem[] {
  const pending = new Set(input.indexPendingKinds ?? [])
  const ctx: ItemContext = { t, storage: input.storage, pending }
  const original = originalSizeItem(ctx)
  const used = usedOnDiskItem(ctx)
  const saved = spaceSavedItem(ctx, original, used)
  const archives = archivesItem(ctx, input.archiveCount)
  if (input.variant === 'detail') {
    return [original, used, saved, archives, backupSpanItem(ctx), latestArchiveFilesItem(ctx)]
  }
  return [archives, original, used, saved]
}

/** The text a stat renders: its value, or the name of its state. */
export function stateText(t: TFunction, item: RepositoryStatItem): string {
  switch (item.state) {
    case 'value':
      return item.value ?? ''
    case 'unknown':
      return t('repositoryStats.unknown')
    case 'withheld':
      return t('repositoryStats.pending')
    case 'indexing':
      return t('repositoryStats.indexing')
  }
}
