import { Plan, Feature, canAccess } from '../core/features'
import type { EntitlementInfo } from './useSystemInfo'

interface UsePlanResult {
  plan: Plan
  features: Record<string, Plan>
  entitlement?: EntitlementInfo
  isLoading: boolean
  can: (feature: Feature) => boolean
}
import { useSystemInfo } from './useSystemInfo'

export function usePlan(): UsePlanResult {
  const { data, isLoading } = useSystemInfo()

  const plan: Plan = data?.plan ?? 'community'
  const features: Record<string, Plan> = data?.features ?? {}
  const featureAccess = data?.feature_access ?? {}
  const entitlement = data?.entitlement

  return {
    plan,
    features,
    entitlement,
    isLoading,
    can: (feature: Feature) => featureAccess[feature] ?? canAccess(plan, feature),
  }
}
