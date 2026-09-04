import { useEffect, useRef } from 'react'
import { BASE_PATH } from '../utils/basePath'
import { getAccessToken } from '../services/authHeaders'
import type { OperationItem, OperationProgressEvent } from '../types/operations'

type RawEvent = {
  type: string
  data: unknown
  timestamp: string
}

/**
 * Subscribes to the shared SSE stream (spec 9.4) and routes
 * `operation.updated` / `operation.progress` events to the caller. Opens
 * one connection per mounted consumer; callers should mount this once per
 * page (the pipeline board, the status strip), not globally.
 */
export function useOperationEvents(
  onUpdated: (op: OperationItem) => void,
  onProgress: (progress: OperationProgressEvent['data']) => void
): void {
  const onUpdatedRef = useRef(onUpdated)
  const onProgressRef = useRef(onProgress)
  onUpdatedRef.current = onUpdated
  onProgressRef.current = onProgress

  useEffect(() => {
    const token = getAccessToken()
    const url = `${BASE_PATH}/api/events/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const source = new EventSource(url)

    source.onmessage = (event: MessageEvent) => {
      let parsed: RawEvent
      try {
        parsed = JSON.parse(event.data)
      } catch {
        return
      }
      if (parsed.type === 'operation.updated') {
        onUpdatedRef.current(parsed.data as OperationItem)
      } else if (parsed.type === 'operation.progress') {
        onProgressRef.current(parsed.data as OperationProgressEvent['data'])
      }
    }

    return () => {
      source.close()
    }
  }, [])
}
