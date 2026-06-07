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
