import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useOperationEvents } from '../useOperationEvents'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }
}

vi.mock('../../services/authHeaders', () => ({
  getAccessToken: () => 'test-token',
}))

describe('useOperationEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens a stream carrying the auth token', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toContain('token=test-token')
  })

  it('routes operation.updated events to onUpdated', () => {
    const onUpdated = vi.fn()
    renderHook(() => useOperationEvents(onUpdated, vi.fn()))
    const op = { id: 1, status: 'running' }
    FakeEventSource.instances[0].emit({ type: 'operation.updated', data: op, timestamp: 't' })
    expect(onUpdated).toHaveBeenCalledWith(op)
  })

  it('routes operation.progress events to onProgress', () => {
    const onProgress = vi.fn()
    renderHook(() => useOperationEvents(vi.fn(), onProgress))
    const progress = {
      id: 1,
      progress_percent: 50,
      progress_current: 5,
      progress_total: 10,
      progress_message: null,
    }
    FakeEventSource.instances[0].emit({
      type: 'operation.progress',
      data: progress,
      timestamp: 't',
    })
    expect(onProgress).toHaveBeenCalledWith(progress)
  })

  it('ignores unrelated event types', () => {
    const onUpdated = vi.fn()
    const onProgress = vi.fn()
    renderHook(() => useOperationEvents(onUpdated, onProgress))
    FakeEventSource.instances[0].emit({ type: 'connection_established', data: {}, timestamp: 't' })
    expect(onUpdated).not.toHaveBeenCalled()
    expect(onProgress).not.toHaveBeenCalled()
  })

  it('closes the stream on unmount', () => {
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    unmount()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })
})
