import type { SystemInfo } from '../../hooks/useSystemInfo'

export const storyFeatureMap = {
  borg_v2: 'pro',
  backup_plan_multi_repository: 'pro',
  backup_plan_mixed_sources: 'pro',
  database_discovery: 'pro',
  container_backups: 'pro',
  backup_reports: 'pro',
  alerting_monitoring: 'pro',
  rclone: 'pro',
  managed_agents: 'pro',
  remote_clients: 'pro',
  multi_user: 'community',
  extra_users: 'pro',
  rbac: 'enterprise',
} as const

export const proSystemInfo: SystemInfo = {
  app_version: '2.2.2',
  borg_version: 'borg 1.4.1',
  borg2_version: 'borg2 2.0.0b19',
  plan: 'pro',
  features: storyFeatureMap,
  feature_access: { remote_clients: true },
}

export const communitySystemInfo: SystemInfo = {
  ...proSystemInfo,
  plan: 'community',
  feature_access: { remote_clients: false },
}

// A Community install whose release-bundle trial has run out: the locked
// panels say the trial ended and the purchase carries the row alone.
export const trialEndedSystemInfo: SystemInfo = {
  ...communitySystemInfo,
  entitlement: {
    status: 'expired',
    access_level: 'community',
    is_full_access: false,
    full_access_consumed: false,
    expires_at: '2026-09-15T00:00:00Z',
    starts_at: '2026-09-01T00:00:00Z',
    instance_id: 'inst_story',
    ui_state: 'community',
    trial_features: [],
    expired_trial_features: ['archive_history'],
    last_refresh_at: null,
    last_refresh_error: null,
  },
}
