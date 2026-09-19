import { useLayoutEffect, useState, type DependencyList, type RefObject } from 'react'

/**
 * The height that runs an element from its own top edge to the bottom of
 * the window, minus whatever the page keeps below it, so a scrolling list
 * fills the screen without ever moving the page. Measured rather than
 * written in CSS because the header above wraps differently per width.
 * Re-measured on window resize and whenever `deps` change (the element
 * may only mount once its data is in). Undefined until measured.
 */
export default function useFillViewport(
  ref: RefObject<HTMLElement | null>,
  min: number,
  deps: DependencyList = []
): number | undefined {
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    // one pending correction at a time: a resize burst would otherwise
    // subtract the same overflow once per frame and shrink the pane
    let frame = 0
    const measure = () => {
      const el = ref.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      // What the page really keeps under the element, measured from the
      // body box rather than from scrollHeight: scrollHeight never drops
      // below the viewport, so on a page that already fits it counts the
      // empty space below as content and the pane never grows into it.
      const below = Math.max(0, document.body.getBoundingClientRect().bottom - rect.bottom)
      setHeight(Math.max(min, Math.floor(window.innerHeight - rect.top - below)))
      // Sub-pixel edges can still leave the page a pixel too tall; take
      // whatever overflow is left once the new height has laid out.
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const root = document.documentElement
        const overflow = root.scrollHeight - root.clientHeight
        if (overflow > 0) setHeight((h) => Math.max(min, (h ?? 0) - overflow))
      })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', measure)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, min, ...deps])
  return height
}
