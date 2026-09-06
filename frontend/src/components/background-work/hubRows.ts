import type { RepositoryTrack } from './repositoryTrack'
import type { HubRepository } from '../../types/operations'

// One table row: a repository from the hub merged with its queue track when
// it has one. The system lane (package installs and other work with no
// repository) has a track but no repository.
export interface HubRow {
  key: string
  repository: HubRepository | null
  track: RepositoryTrack | null
}

// Why a row deserves a look, in the order the toolbar lists them. `all`
// shows everything and `attention` is the union of the other four.
export type AttentionFilter = 'all' | 'attention' | 'stale' | 'never' | 'history' | 'running'
export type AttentionReason = Exclude<AttentionFilter, 'all' | 'attention'>

export const ATTENTION_FILTERS: AttentionFilter[] = [
  'all',
  'attention',
  'stale',
  'never',
  'history',
  'running',
]

export type HubSort = 'name' | 'rows' | 'synced'
export const HUB_SORTS: HubSort[] = ['name', 'rows', 'synced']

export interface HubToolbarState {
  query: string
  attention: AttentionFilter
  sort: HubSort
}

export const DEFAULT_TOOLBAR: HubToolbarState = { query: '', attention: 'all', sort: 'name' }

export type AttentionCounts = Record<AttentionReason, number> & { total: number }

export function trackIsActive(track: RepositoryTrack | null): boolean {
  return (
    track != null && (track.foreground != null || track.stages.some((s) => s.status !== 'idle'))
  )
}

function reasonsFor(row: HubRow): AttentionReason[] {
  const { repository, track } = row
  if (!repository) return []
  const reasons: AttentionReason[] = []
  if (repository.sync_state === 'stale') reasons.push('stale')
  if (repository.sync_state === 'never') reasons.push('never')
  if (repository.history.failed > 0 || repository.history.truncated > 0) reasons.push('history')
  if (trackIsActive(track)) reasons.push('running')
  return reasons
}

// How many rows need a look, per reason and in total. A row with several
// reasons counts once in the total so the number matches what the
// attention view shows.
export function attentionCounts(rows: HubRow[]): AttentionCounts {
  const counts: AttentionCounts = { stale: 0, never: 0, history: 0, running: 0, total: 0 }
  for (const row of rows) {
    const reasons = reasonsFor(row)
    for (const reason of reasons) counts[reason] += 1
    if (reasons.length > 0) counts.total += 1
  }
  return counts
}

function matchesAttention(row: HubRow, attention: AttentionFilter): boolean {
  if (attention === 'all') return true
  const reasons = reasonsFor(row)
  if (attention === 'attention') return reasons.length > 0
  return reasons.includes(attention)
}

function syncedAt(row: HubRow): number {
  const value = row.repository?.last_synced_at
  return value ? Date.parse(value) : Number.NEGATIVE_INFINITY
}

const COMPARE: Record<HubSort, (a: HubRow, b: HubRow) => number> = {
  name: (a, b) =>
    (a.repository?.repository_name ?? '').localeCompare(b.repository?.repository_name ?? ''),
  rows: (a, b) => (b.repository?.history.rows ?? 0) - (a.repository?.history.rows ?? 0),
  synced: (a, b) => syncedAt(b) - syncedAt(a),
}

// The rows the table shows for a toolbar state. A row keeps its place when
// work starts on it: moving it to the top made a rebuild look like the list
// had reshuffled. The track under the row and the running count in the
// summary say what is live. The system lane comes last and only when
// nothing is filtered by name, since it has no name to match.
export function applyToolbar(rows: HubRow[], state: HubToolbarState): HubRow[] {
  const query = state.query.trim().toLowerCase()
  const compare = COMPARE[state.sort]
  const tie = (a: HubRow, b: HubRow) => compare(a, b) || COMPARE.name(a, b)
  const repositories = rows.filter(
    (row) =>
      row.repository != null &&
      (query === '' || row.repository.repository_name.toLowerCase().includes(query)) &&
      matchesAttention(row, state.attention)
  )
  repositories.sort(tie)
  const system =
    query === ''
      ? rows.filter((row) => row.repository == null && matchesAttention(row, state.attention))
      : []
  return [...repositories, ...system]
}

// One row per repository from the hub, in the hub's order, merged with its
// queue track when it has one. Work with no repository goes last.
export function mergeRows(repositories: HubRepository[], tracks: RepositoryTrack[]): HubRow[] {
  const byRepository = new Map<number, RepositoryTrack>()
  const system: RepositoryTrack[] = []
  for (const track of tracks) {
    if (track.repositoryId == null) system.push(track)
    else byRepository.set(track.repositoryId, track)
  }
  return [
    ...repositories.map<HubRow>((repository) => ({
      key: `repo-${repository.repository_id}`,
      repository,
      track: byRepository.get(repository.repository_id) ?? null,
    })),
    ...system.map<HubRow>((track) => ({
      key: `system-${track.repositoryName}`,
      repository: null,
      track,
    })),
  ]
}
