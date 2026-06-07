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
  managed_agents: 'pro',
  remote_clients: 'pro',
  database_discovery: 'pro',
  container_backups: 'pro',
  backup_reports: 'pro',
  alerting_monitoring: 'pro',
  multi_user: 'community',
  extra_users: 'pro',
  rbac: 'enterprise',
} as const satisfies Record<string, Plan>

export type Feature = keyof typeof FEATURES

export const PLAN_LABEL: Record<Plan, string> = {
  community: 'Community',
  pro: 'Pro',
  enterprise: 'Enterprise',
}

export const PLAN_COLOR: Record<Plan, string> = {
  community: '#64748b',
  pro: '#6366f1',
  enterprise: '#f59e0b',
}

export function planIncludes(current: Plan, required: Plan): boolean {
  return PLAN_RANK[current] >= PLAN_RANK[required]
}

export function canAccess(plan: Plan, feature: Feature): boolean {
  return planIncludes(plan, FEATURES[feature])
}
