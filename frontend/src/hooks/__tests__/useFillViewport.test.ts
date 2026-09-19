/**
 * The pane height that reaches the bottom of the window: the space below
 * the element is what the page actually keeps there, not the empty room
 * under a short page.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useFillViewport from '../useFillViewport'

function setup(elementTop: number, elementBottom: number, bodyBottom: number) {
  const el = document.createElement('div')
  el.getBoundingClientRect = () => ({ top: elementTop, bottom: elementBottom }) as DOMRect
  vi.spyOn(document.body, 'getBoundingClientRect').mockReturnValue({
    bottom: bodyBottom,
  } as DOMRect)
  window.innerHeight = 800
  return renderHook(() => useFillViewport({ current: el }, 240))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useFillViewport', () => {
  it('fills the window, minus the content the page keeps below', () => {
    // 120px of footer under the element: 800 - 200 (top) - 120 = 480
    const { result } = setup(200, 400, 520)
    expect(result.current).toBe(480)
  })

  it('grows into the empty space under a page that already fits', () => {
    // nothing below the element at all: it runs to the bottom of the window
    const { result } = setup(200, 400, 400)
    expect(result.current).toBe(600)
  })

  it('never goes below the minimum', () => {
    const { result } = setup(700, 780, 1600)
    expect(result.current).toBe(240)
  })

  it('cancels a pending correction when it measures again', () => {
    const cancel = vi.spyOn(window, 'cancelAnimationFrame')
    setup(200, 400, 520)
    act(() => {
      window.dispatchEvent(new Event('resize'))
    })
    expect(cancel).toHaveBeenCalled()
  })
})
