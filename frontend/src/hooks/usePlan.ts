import { Plan, Feature, canAccess } from '../core/features'
import { useSystemInfo } from './useSystemInfo'

export function usePlan() {
  const { data, isLoading } = useSystemInfo()

  const plan: Plan = data?.plan ?? 'community'
  const features: Record<string, Plan> = data?.features ?? {}

  return {
    plan,
    features,
    isLoading,
    can: (feature: Feature) => canAccess(plan, feature),
  }
}
