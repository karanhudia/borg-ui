import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useTrackedJobOutcomes } from './useTrackedJobOutcomes'

describe('useTrackedJobOutcomes', () => {
  it('tracks only when a seen non-terminal job becomes terminal', () => {
    const onTerminal = vi.fn()

    const { rerender } = renderHook(({ jobs }) => useTrackedJobOutcomes({ jobs, onTerminal }), {
      initialProps: {
        jobs: [{ id: 1, status: 'running' }],
      },
    })

    expect(onTerminal).not.toHaveBeenCalled()

    rerender({
      jobs: [{ id: 1, status: 'completed' }],
    })

    expect(onTerminal).toHaveBeenCalledTimes(1)
    expect(onTerminal).toHaveBeenCalledWith({ id: 1, status: 'completed' }, 'running')

    rerender({
      jobs: [{ id: 1, status: 'completed' }],
    })

    expect(onTerminal).toHaveBeenCalledTimes(1)
  })

  it('does not track a job first seen in a terminal state', () => {
    const onTerminal = vi.fn()

    renderHook(() =>
      useTrackedJobOutcomes({
        jobs: [{ id: 9, status: 'failed' }],
        onTerminal,
      })
    )

    expect(onTerminal).not.toHaveBeenCalled()
  })
})
