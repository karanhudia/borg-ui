import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Plan, Feature, canAccess } from '../core/features'

interface SystemInfo {
  app_version: string
  borg_version: string | null
  borg2_version: string | null
  plan: Plan
}

async function fetchSystemInfo(): Promise<SystemInfo> {
  const res = await api.get<SystemInfo>('/system/info')
  return res.data
}

export function usePlan() {
  const { data, isLoading } = useQuery<SystemInfo>({
    queryKey: ['system-info'],
    queryFn: fetchSystemInfo,
    staleTime: 5 * 60 * 1000,
  })

  const plan: Plan = data?.plan ?? 'community'

  return {
    plan,
    isLoading,
    can: (feature: Feature) => canAccess(plan, feature),
  }
}
