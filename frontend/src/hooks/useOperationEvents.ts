import { useEffect, useRef } from 'react'
import { getActiveBackendTarget } from '../services/remoteBackends/storage'
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
 * One connection is shared by every consumer. The repositories page mounts a
 * status strip per card, and browsers cap concurrent SSE connections per
 * origin at around six on HTTP/1.1, so a connection per consumer would leave
 * the later cards silently stale.
 */
const subscribers = new Set<{ current: Handlers }>()
let source: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

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
  if (!source || source.readyState !== 2 /* CLOSED */) return
  source.close()
  source = null
  if (subscribers.size === 0 || reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    openSource()
  }, RECONNECT_DELAY_MS)
}

function openSource(): void {
  if (source || typeof EventSource === 'undefined') return
  const target = getActiveBackendTarget()
  // The stream must follow the active backend target, like every axios call
  // does, or the board would merge the local machine's events into a remote
  // machine's queue.
  const url = buildApiUrl('/events/stream', getBackendTargetTokenParams(target.id))
  source = new EventSource(url)
  source.onmessage = handleMessage
  source.onerror = handleError
}

function closeSourceIfIdle(): void {
  if (subscribers.size > 0) return
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (!source) return
  source.close()
  source = null
}

/**
 * Subscribes to the shared SSE stream (spec 9.4) and routes
 * `operation.updated` / `operation.progress` events to the caller. Mounting
 * this in several components is safe: they all read from one connection,
 * which closes when the last consumer unmounts.
 */
export function useOperationEvents(
  onUpdated: (op: OperationItem) => void,
  onProgress: (progress: OperationProgressEvent['data']) => void
): void {
  const handlers = useRef<Handlers>({ onUpdated, onProgress })

  useEffect(() => {
    handlers.current = { onUpdated, onProgress }
  })

  useEffect(() => {
    const entry = handlers
    subscribers.add(entry)
    openSource()
    return () => {
      subscribers.delete(entry)
      closeSourceIfIdle()
    }
  }, [])
}
