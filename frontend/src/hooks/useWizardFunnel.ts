import { useCallback, useEffect, useRef } from 'react'
import { EventAction, trackEvent } from '../utils/analytics'

interface WizardFunnelOptions {
  /** Event category, e.g. 'Quick Start' or 'Wizard'. */
  category: string
  open: boolean
  /** The step on screen; null sends nothing for it. */
  step: string | null
  /** Sent with every event. Read when an event is sent, so it may change per render. */
  props?: Record<string, unknown>
  /** Sent with the Start event instead of props. */
  startProps?: Record<string, unknown>
}

/**
 * A wizard's funnel: `Start` when it opens, `View` the first time each step is
 * reached (going back and forth counts a step once), and `Cancel` with the last
 * step when the user closes it through the wizard's own close or cancel. Closing
 * because the work succeeded is the caller's business and never passes through
 * `cancel`.
 */
export function useWizardFunnel({ category, open, step, props, startProps }: WizardFunnelOptions) {
  const reached = useRef(new Set<string>())
  const lastStep = useRef<string | null>(null)
  // Off until a tick after opening: wizards reset their step in an effect on
  // open, so the first frame can still show the step the last session ended on.
  const ready = useRef(false)
  const started = useRef(false)
  const latest = useRef({ step, props, startProps })
  // Declared first, so it runs before the effects below read it.
  useEffect(() => {
    latest.current = { step, props, startProps }
  })

  const reach = useCallback(() => {
    const current = latest.current
    if (current.step === null) return
    lastStep.current = current.step
    if (reached.current.has(current.step)) return
    reached.current.add(current.step)
    trackEvent(category, EventAction.VIEW, { ...current.props, step: current.step })
  }, [category])

  useEffect(() => {
    if (!open) {
      ready.current = false
      started.current = false
      reached.current.clear()
      lastStep.current = null
      return
    }
    // Start goes out now, so a wizard closed before its first step settles is
    // still an abandon that started.
    if (!started.current) {
      started.current = true
      trackEvent(category, EventAction.START, latest.current.startProps ?? latest.current.props)
    }
    const timer = setTimeout(() => {
      ready.current = true
      reach()
    }, 0)
    return () => clearTimeout(timer)
  }, [category, open, reach])

  useEffect(() => {
    if (ready.current) reach()
  }, [step, reach])

  const cancel = useCallback(() => {
    trackEvent(category, EventAction.CANCEL, {
      ...latest.current.props,
      ...(lastStep.current ? { step: lastStep.current } : {}),
    })
  }, [category])

  return { cancel }
}
