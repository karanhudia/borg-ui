import { useCallback } from 'react'
import { Feature } from '../core/features'
import { openUpgradeDialog } from '../utils/upgradeDialog'
import { useFeatureAnalytics } from './useFeatureAnalytics'
import { usePlan } from './usePlan'

interface LockedClickContext {
  surface: string
  /** The control's own operation name (what the render event calls it). */
  control: string
  message?: string
}

/**
 * A click on a locked control: one `locked_click` event per click, kept apart
 * from the render impression (gate_mode 'disabled'), then the upgrade card.
 * While the plan is loading it reads as Community, so a click then is ignored
 * rather than reported as a lock the user may not have.
 */
export function useLockedClick() {
  const { trackFeatureBlocked } = useFeatureAnalytics()
  const { isLoading } = usePlan()
  return useCallback(
    (feature: Feature, { surface, control, message }: LockedClickContext) => {
      if (isLoading) return
      trackFeatureBlocked(feature, {
        surface,
        operation: 'locked_click',
        gate_mode: 'locked_click',
        control,
      })
      openUpgradeDialog({ feature, surface, message })
    },
    [isLoading, trackFeatureBlocked]
  )
}
