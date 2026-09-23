import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook as renderBare } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// The hook keeps module state (the shared stream and whether it was lost)
// that outlives every consumer, so each test starts from a fresh module.
let useOperationEvents: typeof import('../useOperationEvents').useOperationEvents

// One client per test, shared by every consumer rendered in it, as in the app.
let queryClient: QueryClient
const renderHook = <T,>(callback: () => T) =>
  renderBare(callback, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
const invalidations = () => vi.mocked(queryClient.invalidateQueries).mock.calls.length

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onopen: (() => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  readyState = 1
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  fail() {
    this.readyState = 2
    this.onerror?.()
  }
  // a dropped stream the browser retries on its own
  drop() {
    this.readyState = 0
    this.onerror?.()
  }
}

vi.mock('../../services/authHeaders', () => ({
  getBackendTargetTokenParams: () => ({ token: 'test-token' }),
}))

let activeTargetId = 'local'
let targetListener: ((reason: string) => void) | null = null

vi.mock('../../services/remoteBackends/storage', () => ({
  getActiveBackendTarget: () => ({ id: activeTargetId }),
  subscribeRemoteBackendStorage: (listener: (reason: string) => void) => {
    targetListener = listener
    return () => {
      targetListener = null
    }
  },
}))

describe('useOperationEvents', () => {
  beforeEach(async () => {
    FakeEventSource.instances = []
    activeTargetId = 'local'
    targetListener = null
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.useFakeTimers()
    queryClient = new QueryClient()
    vi.spyOn(queryClient, 'invalidateQueries')
    vi.resetModules()
    ;({ useOperationEvents } = await import('../useOperationEvents'))
  })
  afterEach(() => {
    vi.useRealTimers()
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

  it('shares one connection across consumers and fans events out to each', () => {
    const first = vi.fn()
    const second = vi.fn()
    const a = renderHook(() => useOperationEvents(first, vi.fn()))
    const b = renderHook(() => useOperationEvents(second, vi.fn()))

    expect(FakeEventSource.instances).toHaveLength(1)

    const op = { id: 7, status: 'running' }
    FakeEventSource.instances[0].emit({ type: 'operation.updated', data: op, timestamp: 't' })
    expect(first).toHaveBeenCalledWith(op)
    expect(second).toHaveBeenCalledWith(op)

    a.unmount()
    expect(FakeEventSource.instances[0].closed).toBe(false)
    b.unmount()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('reopens the stream after the connection dies', () => {
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    expect(FakeEventSource.instances).toHaveLength(1)

    FakeEventSource.instances[0].fail()
    expect(FakeEventSource.instances[0].closed).toBe(true)

    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[1].closed).toBe(false)

    unmount()
    expect(FakeEventSource.instances[1].closed).toBe(true)
  })

  it('invalidates nothing on the first open', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[0].open()
    expect(invalidations()).toBe(0)
  })

  it('invalidates every query once the reopened stream opens', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[0].open()

    FakeEventSource.instances[0].fail()
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    // retrying is not being back: events are still lost until it opens
    expect(invalidations()).toBe(0)

    FakeEventSource.instances[1].open()
    // once for the stream, not once per consumer
    expect(invalidations()).toBe(1)
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith()
  })

  it("invalidates after the browser's own retry of a dropped stream", () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    const stream = FakeEventSource.instances[0]
    stream.open()

    stream.drop()
    stream.drop()
    stream.open()
    // an open without a loss in between is not a reconnect
    stream.open()

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(invalidations()).toBe(1)
  })

  it('invalidates nothing when a backend switch replaces a lost stream', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[0].open()
    FakeEventSource.instances[0].fail()

    activeTargetId = 'remote-1'
    act(() => {
      targetListener?.('target')
    })
    FakeEventSource.instances[1].open()

    expect(invalidations()).toBe(0)
  })

  it('still invalidates when the consumer that saw the loss is gone', () => {
    // cached queries outlive the consumers, so the gap is still unrefreshed
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[0].open()
    FakeEventSource.instances[0].drop()
    unmount()

    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[1].open()

    expect(invalidations()).toBe(1)
  })

  it('invalidates nothing for a consumer that mounts after a clean idle close', () => {
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[0].open()
    unmount()

    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    FakeEventSource.instances[1].open()

    expect(invalidations()).toBe(0)
  })

  it('rebinds the stream when the active backend target changes', () => {
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    expect(FakeEventSource.instances).toHaveLength(1)

    activeTargetId = 'remote-1'
    act(() => {
      targetListener?.('target')
    })

    expect(FakeEventSource.instances[0].closed).toBe(true)
    expect(FakeEventSource.instances).toHaveLength(2)

    unmount()
    expect(FakeEventSource.instances[1].closed).toBe(true)
  })

  it('leaves the stream alone when an unrelated storage change fires', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    act(() => {
      targetListener?.('token')
    })
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].closed).toBe(false)
  })
})
