import type { PruneRetention } from '../../types/archives'

export const DEFAULT_RETENTION: PruneRetention = {
  keep_within: '',
  keep_hourly: 0,
  keep_daily: 7,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
}
