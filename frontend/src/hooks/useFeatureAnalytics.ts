import { useCallback } from 'react'
import { Feature, FEATURES } from '../core/features'
import { EventAction, EventCategory, trackEvent } from '../utils/analytics'
import { usePlan } from './usePlan'

export interface FeatureAnalyticsContext {
  surface: string
  operation: string
  [key: string]: unknown
}

export function useFeatureAnalytics() {
  const { plan } = usePlan()

  const trackFeatureEvent = useCallback(
    (action: string, feature: Feature, allowed: boolean, context: FeatureAnalyticsContext) => {
      trackEvent(EventCategory.PLAN, action, {
        feature,
        current_plan: plan,
        required_plan: FEATURES[feature],
        allowed,
        ...context,
      })
    },
    [plan]
  )

  const trackFeatureUsed = useCallback(
    (feature: Feature, context: FeatureAnalyticsContext) => {
      trackFeatureEvent(EventAction.FEATURE_USED, feature, true, context)
    },
    [trackFeatureEvent]
  )

  const trackFeatureBlocked = useCallback(
    (feature: Feature, context: FeatureAnalyticsContext) => {
      trackFeatureEvent(EventAction.FEATURE_BLOCKED, feature, false, context)
    },
    [trackFeatureEvent]
  )

  return { trackFeatureUsed, trackFeatureBlocked }
}
