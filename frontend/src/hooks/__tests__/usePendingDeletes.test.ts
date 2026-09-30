import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { usePendingDeletes } from '../usePendingDeletes'

describe('usePendingDeletes', () => {
  it('ignores a second delete of the same id while the first is out', async () => {
    const { result } = renderHook(() => usePendingDeletes())
    let finish!: () => void
    const request = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))

    let first!: Promise<boolean>
    let second!: Promise<boolean>
    act(() => {
      first = result.current.run(7, request)
      second = result.current.run(7, request)
    })
    expect(request).toHaveBeenCalledTimes(1)
    expect(result.current.isDeleting(7)).toBe(true)
    expect(result.current.isDeleting(8)).toBe(false)
    await expect(second).resolves.toBe(false)

    await act(async () => {
      finish()
      await first
    })
    expect(result.current.isDeleting(7)).toBe(false)
  })

  it('releases the id when the request fails, and rethrows', async () => {
    const { result } = renderHook(() => usePendingDeletes<string>())
    await act(async () => {
      await expect(
        result.current.run('a', () => Promise.reject(new Error('nope')))
      ).rejects.toThrow('nope')
    })
    expect(result.current.isDeleting('a')).toBe(false)
  })
})
