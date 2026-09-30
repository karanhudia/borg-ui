import { useCallback, useRef, useState } from 'react'

/**
 * The ids whose delete is still out, so a row can disable its trigger and a
 * second click cannot send a second DELETE (#1197). `run` holds the id until
 * `request` settles, so a request that awaits the list refetch keeps the row
 * disabled until it is gone. Errors are the request's business and are thrown
 * again; the id is released either way.
 */
export function usePendingDeletes<Id extends string | number = number>() {
  const [pending, setPending] = useState<ReadonlySet<Id>>(() => new Set())
  // The guard reads synchronously: two clicks in one tick share the state.
  const pendingRef = useRef(pending)

  const update = (change: (next: Set<Id>) => void) => {
    const next = new Set(pendingRef.current)
    change(next)
    pendingRef.current = next
    setPending(next)
  }

  /** Returns false, without calling `request`, while a delete of `id` is out. */
  const run = useCallback(async (id: Id, request: () => Promise<unknown>): Promise<boolean> => {
    if (pendingRef.current.has(id)) return false
    update((next) => next.add(id))
    try {
      await request()
      return true
    } finally {
      update((next) => next.delete(id))
    }
  }, [])

  const isDeleting = useCallback((id: Id) => pending.has(id), [pending])

  return { pending, isDeleting, run }
}
