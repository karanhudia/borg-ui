import type { AuthEventRecord } from '../../services/api'

export interface CacheStats {
  browse_max_items?: number
  browse_max_memory_mb?: number
  cache_ttl_minutes?: number
  cache_max_size_mb?: number
  redis_url?: string
}

export type AuthEventFilter = 'all' | 'failed' | 'oidc' | 'pending'

export interface SectionTabConfig {
  label: string
  description: string
}

export interface AuthEventStats {
  total: number
  success: number
  failed: number
  pending: number
  oidc: number
}

export type AuthEventFormatter = (value: string) => string
export type AuthEventRefetch = () => unknown
export type AuthEvents = AuthEventRecord[] | undefined
