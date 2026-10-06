export type Plan = 'community' | 'pro' | 'enterprise'

const PLAN_RANK: Record<Plan, number> = {
  community: 0,
  pro: 1,
  enterprise: 2,
}

// Mirror of app/core/features.py - keep in sync when adding features
export const FEATURES = {
  borg_v2: 'pro',
  backup_plan_multi_repository: 'pro',
  backup_plan_mixed_sources: 'pro',
  rclone: 'pro',
  remote_clients: 'pro',
  database_discovery: 'pro',
  container_backups: 'pro',
  backup_reports: 'pro',
  alerting_monitoring: 'pro',
  archive_history: 'pro',
  multi_user: 'community',
  extra_users: 'pro',
  rbac: 'enterprise',
} as const satisfies Record<string, Plan>

export type Feature = keyof typeof FEATURES

/**
 * Community features with no plan gate that still report adoption through
 * `Plan - FeatureUsed`. They are not in FEATURES, so nothing can block on them.
 */
export const COMMUNITY_TRACKED_FEATURES = ['managed_agents'] as const

export type TrackedFeature = Feature | (typeof COMMUNITY_TRACKED_FEATURES)[number]

export const PLAN_LABEL: Record<Plan, string> = {
  community: 'Community',
  pro: 'Pro',
  enterprise: 'Enterprise',
}

/** The tier directly above the current plan, or null on the top tier. */
export function nextPlanAbove(plan: Plan): 'pro' | 'enterprise' | null {
  if (plan === 'community') return 'pro'
  if (plan === 'pro') return 'enterprise'
  return null
}

export function planIncludes(current: Plan, required: Plan): boolean {
  return PLAN_RANK[current] >= PLAN_RANK[required]
}

export function canAccess(plan: Plan, feature: Feature): boolean {
  return planIncludes(plan, FEATURES[feature])
}
