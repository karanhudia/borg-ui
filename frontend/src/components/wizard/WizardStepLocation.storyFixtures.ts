import type { SystemInfo } from '../../hooks/useSystemInfo'

export const fullFeatureSystemInfo = {
  app_version: '2.2.2',
  borg_version: 'borg 1.4.1',
  borg2_version: 'borg2 2.0.0b19',
  plan: 'pro',
  features: {
    borg_v2: 'pro',
    managed_agents: 'pro',
    rclone: 'pro',
  },
  feature_access: {
    borg_v2: true,
    managed_agents: true,
    rclone: true,
  },
} satisfies SystemInfo
