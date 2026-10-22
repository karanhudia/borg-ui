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
  const latest = useRef({ props, startProps })
  latest.current = { props, startProps }

  useEffect(() => {
    if (!open) {
      reached.current.clear()
      lastStep.current = null
      return
    }
    if (step === null) return
    lastStep.current = step
    if (reached.current.has(step)) return
    if (reached.current.size === 0) {
      trackEvent(category, EventAction.START, latest.current.startProps ?? latest.current.props)
    }
    reached.current.add(step)
    trackEvent(category, EventAction.VIEW, { step, ...latest.current.props })
  }, [category, open, step])

  const cancel = useCallback(() => {
    trackEvent(category, EventAction.CANCEL, {
      ...(lastStep.current ? { step: lastStep.current } : {}),
      ...latest.current.props,
    })
  }, [category])

  return { cancel }
}
