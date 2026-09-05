// Mirrors the response shapes in app/api/archive_index.py (spec 9.2).

export type HistoryState = 'pending' | 'indexed' | 'skipped'
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
}

export interface HeatmapDay {
  date: string
  count: number
  deduplicated_size: number
  duration_seconds: number
  archive_ids: number[]
  anomalies: string[]
}

export interface HeatmapSeries {
  series: string
  days: HeatmapDay[]
  missed_days: string[]
  first: string | null
  last: string | null
}

export interface HeatmapResponse {
  since: string | null
  until: string | null
  series: HeatmapSeries[]
  flags_available: {
    missed_run: boolean
    size_outlier: boolean
    duration_outlier: boolean
  }
}

export interface ArchiveDetailResponse extends ArchiveRow {
  predecessor_id: number | null
  successor_id: number | null
  history_available: boolean
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

export interface PathHistoryResponse {
  path: string
  entries: HistoryEntry[]
  present: PresentRange[]
  present_in_latest: boolean
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
