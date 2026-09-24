import { hashKey, type QueryClient, type QueryKey } from '@tanstack/react-query'

// The lists that show deletable job rows, by query-key prefix. Each page
// keys its query by its own filters, so these match every variant.
export const JOB_LIST_QUERY_KEYS = [
  ['activity'],
  ['backup-status-manual'],
  ['backup-jobs-all'],
  ['scheduled-check-history'],
] as const

export interface JobRef {
  id: string | number
  type?: string
}

// A row's identity for a pending delete. The delete call reads a missing
// type as backup.
export const jobKey = (job: JobRef) => `${job.type || 'backup'}-${job.id}`

// Keyed by type and id together: a script execution and an operation can
// share an id. Rows without a type come from single-type lists of backups.
const isSameJob = (row: Record<string, unknown>, job: JobRef) =>
  String(row.id) === String(job.id) && (row.type || 'backup') === (job.type || 'backup')

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

/**
 * Return cached list data without the given job, in whichever shape the list
 * caches: a plain array, `{ jobs }`, an axios response around either, or an
 * infinite query's `{ pages }`. Follow-up steps nested under a row are
 * filtered too. Data of any other shape comes back unchanged.
 */
export function withoutJob(data: unknown, job: JobRef): unknown {
  if (Array.isArray(data)) {
    return data
      .filter((row) => !(isObject(row) && isSameJob(row, job)))
      .map((row) =>
        isObject(row) && Array.isArray(row.followups)
          ? { ...row, followups: withoutJob(row.followups, job) }
          : row
      )
  }
  if (!isObject(data)) return data
  if (Array.isArray(data.pages)) {
    return { ...data, pages: data.pages.map((page) => withoutJob(page, job)) }
  }
  if (Array.isArray(data.jobs)) {
    return { ...data, jobs: withoutJob(data.jobs, job) }
  }
  if (isObject(data.data)) {
    return { ...data, data: withoutJob(data.data, job) }
  }
  return data
}

// Deletes waiting for the server, kept per query client rather than per
// table: every table using it shares one cache, and a page left and opened
// again while a delete is out mounts a new table.
interface DeleteSeries {
  pending: Set<string>
  // Deletes overlap, so one rollback must not undo another's removal. Each
  // list as it was before the series first touched it, by query hash, and
  // the rows of every delete in the series that has not failed.
  base: Map<string, [QueryKey, unknown]>
  removed: Map<string, JobRef>
}

interface DeleteStore {
  series: DeleteSeries
  // The rendered view of the pending deletes, replaced on every change.
  snapshot: ReadonlySet<string>
  listeners: Set<() => void>
}

const newSeries = (): DeleteSeries => ({ pending: new Set(), base: new Map(), removed: new Map() })

const stores = new WeakMap<QueryClient, DeleteStore>()

function storeFor(queryClient: QueryClient): DeleteStore {
  let store = stores.get(queryClient)
  if (!store) {
    store = { series: newSeries(), snapshot: new Set(), listeners: new Set() }
    stores.set(queryClient, store)
  }
  return store
}

function publish(store: DeleteStore) {
  store.snapshot = new Set(store.series.pending)
  store.listeners.forEach((listener) => listener())
}

export function subscribeToPendingDeletes(queryClient: QueryClient, listener: () => void) {
  const { listeners } = storeFor(queryClient)
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export const pendingDeletes = (queryClient: QueryClient): ReadonlySet<string> =>
  storeFor(queryClient).snapshot

/**
 * Drop every pending delete from view, for a cache about to be cleared for
 * another backend: its rows are not this backend's, and a delete still out
 * there must not write its rollback or refetch into the new cache.
 */
export function forgetPendingDeletes(queryClient: QueryClient) {
  const store = storeFor(queryClient)
  store.series = newSeries()
  publish(store)
}

/**
 * Delete a job and drop its row from every cached list at once. A fetch
 * already under way is cancelled, since it would bring the row back. On
 * failure the row is put back, and only that row, and the error is thrown
 * again. Once no delete is pending the lists are refetched: the server stays
 * the source of truth, and a delete sends no operation event. Returns false,
 * without a request, while a delete of the same row is still out: a second
 * request could only answer "job not found".
 */
export async function deleteJobFromLists(
  queryClient: QueryClient,
  job: JobRef,
  request: () => Promise<unknown>
): Promise<boolean> {
  const store = storeFor(queryClient)
  const series = store.series
  const key = jobKey(job)
  if (series.pending.has(key)) return false
  // False once the cache was cleared for another backend.
  const current = () => store.series === series

  series.pending.add(key)
  publish(store)
  try {
    // Sent before anything is awaited: the client addresses whichever
    // backend is active when a request leaves, and the user may switch.
    const sent = request()
    sent.catch(() => {})
    await Promise.all(
      JOB_LIST_QUERY_KEYS.map((queryKey) => queryClient.cancelQueries({ queryKey }))
    )
    if (current()) {
      JOB_LIST_QUERY_KEYS.forEach((queryKey) =>
        queryClient.getQueriesData({ queryKey }).forEach(([listKey, data]) => {
          const hash = hashKey(listKey)
          if (!series.base.has(hash)) series.base.set(hash, [listKey, data])
        })
      )
      series.removed.set(key, job)
      JOB_LIST_QUERY_KEYS.forEach((queryKey) =>
        queryClient.setQueriesData({ queryKey }, (old: unknown) => withoutJob(old, job))
      )
    }
    await sent
    // A refresh while the delete was out may have listed the row again; the
    // refetch may wait for other deletes, so drop it before the guard goes.
    if (current()) {
      JOB_LIST_QUERY_KEYS.forEach((queryKey) =>
        queryClient.setQueriesData({ queryKey }, (old: unknown) => withoutJob(old, job))
      )
    }
    return true
  } catch (error) {
    if (current()) {
      series.removed.delete(key)
      const stillRemoved = [...series.removed.values()]
      series.base.forEach(([queryKey, data]) => {
        queryClient.setQueryData(
          queryKey,
          stillRemoved.reduce((rows, removed) => withoutJob(rows, removed), data)
        )
      })
    }
    throw error
  } finally {
    series.pending.delete(key)
    if (current()) {
      publish(store)
      if (series.pending.size === 0) {
        series.base.clear()
        series.removed.clear()
        JOB_LIST_QUERY_KEYS.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }))
      }
    }
  }
}
