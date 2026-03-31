/**
 * borgApi — single import surface.
 *
 * Everything consumers need comes from here:
 *
 *   import { BorgApiProvider, useBorgApi } from '@/services/borgApi'
 *   import type { BorgApiClient, Repository } from '@/services/borgApi'
 */

export { BorgApiProvider, useBorgApi } from './context'
export { BorgApiClient } from './client'
export type { Repository, BackupOptions, PruneOptions } from './client'
