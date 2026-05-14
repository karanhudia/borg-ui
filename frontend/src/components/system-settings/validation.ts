import type { TFunction } from 'i18next'

import type { SystemSettings } from '../../services/api'
import {
  MAX_FILES,
  MAX_MEMORY,
  MAX_SCHEDULE_CONCURRENCY,
  MAX_STATS_REFRESH,
  MAX_TIMEOUT,
  MIN_FILES,
  MIN_MEMORY,
  MIN_TIMEOUT,
} from './constants'

interface SystemSettingsValidationParams {
  browseMaxItems: number
  browseMaxMemoryMb: number
  mountTimeout: number
  infoTimeout: number
  listTimeout: number
  initTimeout: number
  backupTimeout: number
  sourceSizeTimeout: number
  statsRefreshInterval: number
  maxConcurrentScheduledBackups: number
  maxConcurrentScheduledChecks: number
  oidcEnabled: boolean
  oidcDiscoveryUrl: string
  oidcClientId: string
  oidcClientSecret: string
  oidcNewUserMode: string
  oidcTemplateUsername: string
  oidcDisableLocalAuth: boolean
  hasOidcActiveAdminSignal: boolean
  hasActiveOidcAdmin: boolean
  systemSettings?: SystemSettings
  t: TFunction
}

export const getSystemSettingsValidationError = ({
  browseMaxItems,
  browseMaxMemoryMb,
  mountTimeout,
  infoTimeout,
  listTimeout,
  initTimeout,
  backupTimeout,
  sourceSizeTimeout,
  statsRefreshInterval,
  maxConcurrentScheduledBackups,
  maxConcurrentScheduledChecks,
  oidcEnabled,
  oidcDiscoveryUrl,
  oidcClientId,
  oidcClientSecret,
  oidcNewUserMode,
  oidcTemplateUsername,
  oidcDisableLocalAuth,
  hasOidcActiveAdminSignal,
  hasActiveOidcAdmin,
  systemSettings,
  t,
}: SystemSettingsValidationParams): string | null => {
  if (browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES) {
    return `Max files must be between ${MIN_FILES.toLocaleString()} and ${MAX_FILES.toLocaleString()}`
  }
  if (browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY) {
    return `Max memory must be between ${MIN_MEMORY} MB and ${MAX_MEMORY} MB`
  }
  const timeouts = [
    mountTimeout,
    infoTimeout,
    listTimeout,
    initTimeout,
    backupTimeout,
    sourceSizeTimeout,
  ]
  if (timeouts.some((timeout) => timeout < MIN_TIMEOUT || timeout > MAX_TIMEOUT)) {
    return `Timeouts must be between ${MIN_TIMEOUT} seconds and ${MAX_TIMEOUT} seconds (24 hours)`
  }
  if (statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH) {
    return `Stats refresh interval must be between 0 and ${MAX_STATS_REFRESH} minutes (0 = disabled)`
  }
  if (
    maxConcurrentScheduledBackups < 0 ||
    maxConcurrentScheduledBackups > MAX_SCHEDULE_CONCURRENCY ||
    maxConcurrentScheduledChecks < 0 ||
    maxConcurrentScheduledChecks > MAX_SCHEDULE_CONCURRENCY
  ) {
    return `Scheduler concurrency limits must be between 0 and ${MAX_SCHEDULE_CONCURRENCY}`
  }

  const hasExistingOidcSecret = Boolean(systemSettings?.oidc_client_secret_set)
  if (!oidcEnabled) {
    return null
  }
  if (!oidcDiscoveryUrl.trim() || !oidcClientId.trim()) {
    return t('systemSettings.oidcRequiredFieldsError')
  }
  if (!hasExistingOidcSecret && !oidcClientSecret.trim()) {
    return t('systemSettings.oidcClientSecretRequired')
  }
  if (oidcNewUserMode === 'template' && !oidcTemplateUsername.trim()) {
    return t('systemSettings.oidcTemplateUserRequired')
  }
  if (oidcDisableLocalAuth && hasOidcActiveAdminSignal && !hasActiveOidcAdmin) {
    return t('systemSettings.oidcActiveAdminRequired')
  }
  return null
}
