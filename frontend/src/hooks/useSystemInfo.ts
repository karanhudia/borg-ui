import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import type { Plan } from '../core/features'

export interface EntitlementInfo {
  status: 'none' | 'active' | 'expired' | 'invalid'
  access_level: 'community' | 'full_access' | Plan
  is_full_access: boolean
  full_access_consumed: boolean
  expires_at: string | null
  starts_at: string | null
  refresh_after?: string | null
  instance_id: string | null
  entitlement_id?: string | null
  key_id?: string | null
  license_id?: string | null
  customer_id?: string | null
  /** The tier as sold. Lite is gated as Pro but named for the reader. */
  license_plan?: 'lite' | Plan | null
  ui_state?: 'full_access_active' | 'full_access_expired' | 'paid_active' | 'community'
  /** Features a per-feature trial grants right now, and the ones whose
   *  trial has run out (spec 2026-09-21, section 3). */
  trial_features?: { feature: string; expires_at: string | null }[]
  expired_trial_features?: string[]
  last_refresh_at: string | null
  last_refresh_error: string | null
}

export interface SystemInfo {
  app_version: string
  borg_version: string | null
  borg2_version: string | null
  plan: Plan
  features: Record<string, Plan>
  feature_access?: Record<string, boolean>
  entitlement?: EntitlementInfo
}

async function fetchSystemInfo(): Promise<SystemInfo> {
  const res = await api.get<SystemInfo>('/system/info')
  return res.data
}

export function useSystemInfo() {
  return useQuery<SystemInfo>({
    queryKey: ['system-info'],
    queryFn: fetchSystemInfo,
    staleTime: 5 * 60 * 1000,
  })
}
