// Mirrors the response shapes in app/api/archive_index.py (spec 9.2).

// Mirrors what the index executors write: an archive starts `pending`,
// becomes `indexed`, is `skipped` when its repository cannot be diffed (an
// agent executes it; the archive listing marks it, since no history run
// ever reaches such a repository), and turns `failed` once its attempts
// run out.
export type HistoryState = 'pending' | 'indexed' | 'skipped' | 'failed'
// Whether the history stage exists for a repository, and if not, why:
// the plan lacks the feature, or a managed agent executes the repository
// and the server cannot diff it. Derived by the backend from the plan and
// the executor, so it is the same for every archive of the repository.
export type HistoryCapability = 'available' | 'plan_locked' | 'agent_unsupported'
export type SyncState = 'fresh' | 'syncing' | 'stale' | 'never'
export type ChangeType = 'added' | 'removed' | 'modified' | 'summary'

export interface ArchiveRow {
  id: number
  repository_id: number
  borg_id: string
  name: string
  series: string
  start: string
  end: string | null
  duration_seconds: number | null
  nfiles: number | null
  original_size: number | null
  compressed_size: number | null
  deduplicated_size: number | null
  // When the four Borg figures above were last measured. null is never
  // measured (sizes null too) or stale (sizes set, being re-measured).
  stats_measured_at: string | null
  hostname: string | null
  username: string | null
  comment: string | null
  backup_operation_id: number | null
  history_state: HistoryState
  history_indexed_at: string | null
  history_rows: number | null
  history_truncated: boolean
  first_seen_at: string | null
  last_seen_at: string | null
}

export interface ArchiveListResponse {
  archives: ArchiveRow[]
  series: string[]
  sync_state: SyncState
  last_synced_at: string | null
  history_available: boolean
  history_capability?: HistoryCapability
}

export interface HeatmapDay {
  date: string
  count: number
  deduplicated_size: number
  duration_seconds: number
  archive_ids: number[]
  anomalies: string[]
}

export interface HeatmapBand {
  days: HeatmapDay[]
  first: string | null
  last: string | null
  count: number
}

export interface HeatmapSeries extends HeatmapBand {
  series: string
}

export interface HeatmapResponse {
  since: string | null
  until: string | null
  // Every archive the index holds, the same set the list shows. Series are a
  // grouping of these, never a filter on them.
  repository: HeatmapBand & { missed_days: string[] }
  series: HeatmapSeries[]
  cadence_known: boolean
  retention_since: string | null
  flags_available: {
    missed_run: boolean
    size_outlier: boolean
    duration_outlier: boolean
  }
}

// Mirrors GET /repositories/{id}/archives/growth (spec 4.3). Points are the
// measured archives oldest first; running_total is the footprint after each
// one, restarted per series when the request was filtered.
export interface GrowthPoint {
  archive_id: number
  name: string
  series: string
  start: string
  deduplicated_size: number
  original_size: number | null
  running_total: number
  // Sizes present but the measurement date was cleared by a listing that saw
  // removed archives (spec 4.1). Drawn lighter.
  stale: boolean
}

export interface GrowthResponse {
  points: GrowthPoint[]
  series: string[]
  stale_count: number
  unmeasured_count: number
}

export interface ArchiveDetailResponse extends ArchiveRow {
  predecessor_id: number | null
  successor_id: number | null
  predecessor_stats: {
    id: number
    nfiles: number | null
    original_size: number | null
    deduplicated_size: number | null
    duration_seconds: number | null
  } | null
  history_available: boolean
  history_capability?: HistoryCapability
}

export interface ChangeRow {
  path: string
  change: ChangeType
  size_before: number | null
  size_after: number | null
  mode_changed: boolean
  owner_changed: boolean
  summary_count: number | null
}

export interface ChangeTotals {
  added: number
  removed: number
  modified: number
  summary: number
}

export interface ChangesResponse {
  archive_id: number
  compare_to_id: number | null
  changes: ChangeRow[]
  totals: ChangeTotals
  next_cursor: string | null
  incomplete: boolean
  unindexed_archive_ids: number[]
  history_state?: HistoryState
  history_truncated?: boolean
  history_capability?: HistoryCapability
}

export interface HistoryEntry {
  archive_id: number
  archive_name: string
  series: string
  start: string
  change: ChangeType
  size_before: number | null
  size_after: number | null
  mode_changed: boolean
  owner_changed: boolean
}

export interface PresentRange {
  series: string
  from_archive_id: number
  to_archive_id: number | null
}

// What a path's history is based on: with nothing indexed the entries say
// nothing about the path; with a partial index they cover the indexed
// archives only.
// `total` counts every archive, `skipped` ones included: they are uncovered
// like `pending` ones, and `capability` says whether an index run will ever
// reach them; `exhausted` are the failures the executor gave up on.
export interface HistoryCoverage {
  indexed: number
  exhausted: number
  total: number
  capability: HistoryCapability
}

export interface PathHistoryResponse {
  path: string
  entries: HistoryEntry[]
  present: PresentRange[]
  present_in_latest: boolean
  coverage?: HistoryCoverage
}

export interface SearchResult {
  path: string
  first_seen_archive_id: number
  first_seen: string
  last_seen_archive_id: number
  last_seen: string
  archive_count: number
  series: string
  last_change: ChangeType
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  truncated: boolean
}

// Mirrors POST /repositories/{id}/prune/preview and the retention fields
// shared with the prune dialog (spec 4.4).
export interface PruneRetention {
  keep_within: string
  keep_hourly: number
  keep_daily: number
  keep_weekly: number
  keep_monthly: number
  keep_quarterly: number
  keep_yearly: number
}

export interface PrunePreviewArchive {
  id: number | null
  borg_id: string
  name: string
  series: string | null
  start: string | null
  verdict: 'kept' | 'deleted'
  rule: string | null
  deduplicated_size: number | null
  stats_measured_at: string | null
  stale: boolean
}

export interface PruneLostFile {
  path: string
  size: number | null
  series: string
  last_held_archive_id: number | null
  last_held_archive_name: string | null
}

export interface PruneLostFiles {
  available: boolean
  capability: string
  incomplete?: boolean
  unindexed_archive_ids?: number[]
  total_count?: number
  total_size?: number
  top?: PruneLostFile[]
  by_folder?: { folder: string; count: number; size: number }[]
}

export interface PrunePreviewResponse {
  operation_id: number
  archives: PrunePreviewArchive[]
  deleted_count: number
  kept_count: number
  freed_at_least: number
  partial_measure: boolean
  footprint_before: number | null
  footprint_after_at_most: number | null
  lost_files: PruneLostFiles
  log: string
}

export interface PruneRetentionDefaults extends Omit<PruneRetention, 'keep_within'> {
  source: 'plan' | 'last_prune' | 'default'
  plan_name: string | null
  keep_within: string | null
}
