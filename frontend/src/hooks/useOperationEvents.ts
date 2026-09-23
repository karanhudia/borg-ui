import { useEffect, useRef } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import {
  getActiveBackendTarget,
  subscribeRemoteBackendStorage,
} from '../services/remoteBackends/storage'
import { buildApiUrl } from '../services/remoteBackends/gateway'
import { getBackendTargetTokenParams } from '../services/authHeaders'
import type { OperationItem, OperationProgressEvent } from '../types/operations'

type RawEvent = {
  type: string
  data: unknown
  timestamp: string
}

type Handlers = {
  onUpdated: (op: OperationItem) => void
  onProgress: (progress: OperationProgressEvent['data']) => void
}

/**
 * One connection is shared by every consumer. Browsers cap concurrent SSE
 * connections per origin at around six on HTTP/1.1, so a connection per
 * consumer would leave later mounts silently stale.
 */
const subscribers = new Set<{ current: Handlers }>()
let source: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let openTargetId: string | null = null
let unsubscribeTargetChanges: (() => void) | null = null
// Set once the stream has failed, cleared when it opens again. The stream has
// no replay, so every event sent in between is lost. It survives an idle
// close: cached queries outlive the consumers (staleTime), so the next
// consumer to mount still has a gap to catch up on.
let connectionLost = false
// The app's one query client, taken from the first consumer. Every page
// that reads from this stream refreshes its queries from the same client.
let queryClient: QueryClient | null = null

const RECONNECT_DELAY_MS = 5000

function handleMessage(event: MessageEvent): void {
  let parsed: RawEvent
  try {
    parsed = JSON.parse(event.data)
  } catch {
    return
  }
  if (parsed.type === 'operation.updated') {
    subscribers.forEach((s) => s.current.onUpdated(parsed.data as OperationItem))
  } else if (parsed.type === 'operation.progress') {
    subscribers.forEach((s) => s.current.onProgress(parsed.data as OperationProgressEvent['data']))
  }
}

/**
 * `EventSource` reconnects on its own after a dropped stream, but not after a
 * non-200 response: an expired token (401) or a restarting backend (502)
 * leaves the socket CLOSED for good. Drop the dead object and retry, so live
 * updates come back once the backend or the token does.
 */
function handleError(): void {
  // Both paths count: a dropped stream the browser retries (CONNECTING) and a
  // non-200 response this module retries below (CLOSED).
  connectionLost = true
  if (!source || source.readyState !== 2 /* CLOSED */) return
  source.close()
  source = null
  if (subscribers.size === 0 || reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    openSource()
  }, RECONNECT_DELAY_MS)
}

/**
 * Nothing says which events the gap swallowed, so every query starts over:
 * the ones on screen refetch now, the cached ones when they are shown
 * again. That also covers a page the user left during the gap and comes
 * back to within its cache's freshness window.
 */
function handleOpen(): void {
  if (!connectionLost) return
  connectionLost = false
  void queryClient?.invalidateQueries()
}

function openSource(): void {
  if (source || typeof EventSource === 'undefined') return
  const target = getActiveBackendTarget()
  // The stream must follow the active backend target, like every axios call
  // does, or the board would merge the local machine's events into a remote
  // machine's queue.
  const url = buildApiUrl('/events/stream', getBackendTargetTokenParams(target.id))
  openTargetId = target.id
  source = new EventSource(url)
  source.onopen = handleOpen
  source.onmessage = handleMessage
  source.onerror = handleError
}

/**
 * Switching the active backend does not remount the consumers, so the shared
 * connection has to be rebound by hand or it would keep streaming the old
 * machine's operations.
 */
function handleTargetChange(): void {
  if (subscribers.size === 0) return
  if (getActiveBackendTarget().id === openTargetId) return
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  // A new target starts from an empty query cache, so there is nothing to
  // catch up on.
  connectionLost = false
  source?.close()
  source = null
  openSource()
}

function closeSourceIfIdle(): void {
  if (subscribers.size > 0) return
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  unsubscribeTargetChanges?.()
  unsubscribeTargetChanges = null
  openTargetId = null
  if (!source) return
  source.close()
  source = null
}

/**
 * Subscribes to the shared SSE stream (spec 9.4) and routes
 * `operation.updated` / `operation.progress` events to the caller. Mounting
 * this in several components is safe: they all read from one connection,
 * which closes when the last consumer unmounts.
 *
 * When the stream opens again after it was lost (not on the first open),
 * every query of the app's client is invalidated, since the events sent
 * during the gap are not replayed.
 */
export function useOperationEvents(
  onUpdated: (op: OperationItem) => void,
  onProgress: (progress: OperationProgressEvent['data']) => void
): void {
  const handlers = useRef<Handlers>({ onUpdated, onProgress })
  const client = useQueryClient()

  useEffect(() => {
    handlers.current = { onUpdated, onProgress }
  })

  useEffect(() => {
    const entry = handlers
    subscribers.add(entry)
    queryClient = client
    unsubscribeTargetChanges ??= subscribeRemoteBackendStorage((reason) => {
      if (reason === 'target') handleTargetChange()
    })
    openSource()
    return () => {
      subscribers.delete(entry)
      closeSourceIfIdle()
    }
  }, [client])
}
