import { useCallback } from 'react'
import { Feature } from '../core/features'
import { openUpgradeDialog } from '../utils/upgradeDialog'
import { useFeatureAnalytics } from './useFeatureAnalytics'

interface LockedClickContext {
  surface: string
  /** The control's own operation name (what the render event calls it). */
  control: string
  message?: string
}

/**
 * A click on a locked control: one `locked_click` event per click, kept apart
 * from the render impression (gate_mode 'disabled'), then the upgrade card.
 */
export function useLockedClick() {
  const { trackFeatureBlocked } = useFeatureAnalytics()
  return useCallback(
    (feature: Feature, { surface, control, message }: LockedClickContext) => {
      trackFeatureBlocked(feature, {
        surface,
        operation: 'locked_click',
        gate_mode: 'locked_click',
        control,
      })
      openUpgradeDialog({ feature, surface, message })
    },
    [trackFeatureBlocked]
  )
}
