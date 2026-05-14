import React, { useEffect, useMemo, useState } from 'react'
import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material'
import { Save } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { authAPI, authAPIAdmin, settingsAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { translateBackendKey } from '../utils/translateBackendKey'
import ArchiveBrowsingLimitsSection from './system-settings/ArchiveBrowsingLimitsSection'
import { buildProxyAuthHeaderRows, buildSectionTabs } from './system-settings/config'
import MetricsAccessSection from './system-settings/MetricsAccessSection'
import OidcSection from './system-settings/OidcSection'
import {
  hasActiveOidcAdmin as getHasActiveOidcAdmin,
  hasOidcActiveAdminSignal as getHasOidcActiveAdminSignal,
} from './system-settings/oidcAdminSignal'
import OperationTimeoutsSection from './system-settings/OperationTimeoutsSection'
import ProxyAuthSection from './system-settings/ProxyAuthSection'
import RepositoryMonitoringSection from './system-settings/RepositoryMonitoringSection'
import SettingsSectionsCard from './system-settings/SettingsSectionsCard'
import { formatAuthEventType, formatAuthSource } from './system-settings/authFormatters'
import type { AuthEventFilter, CacheStats } from './system-settings/types'
import { getSystemSettingsValidationError } from './system-settings/validation'

const SystemSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSystem, EventAction } = useAnalytics()

  const [browseMaxItems, setBrowseMaxItems] = useState(1_000_000)
  const [browseMaxMemoryMb, setBrowseMaxMemoryMb] = useState(1024)
  const [mountTimeout, setMountTimeout] = useState(120)
  const [infoTimeout, setInfoTimeout] = useState(600)
  const [listTimeout, setListTimeout] = useState(600)
  const [initTimeout, setInitTimeout] = useState(300)
  const [backupTimeout, setBackupTimeout] = useState(3600)
  const [sourceSizeTimeout, setSourceSizeTimeout] = useState(3600)
  const [maxConcurrentScheduledBackups, setMaxConcurrentScheduledBackups] = useState(2)
  const [maxConcurrentScheduledChecks, setMaxConcurrentScheduledChecks] = useState(4)
  const [statsRefreshInterval, setStatsRefreshInterval] = useState(60)
  const [isRefreshingStats, setIsRefreshingStats] = useState(false)
  const [metricsEnabled, setMetricsEnabled] = useState(false)
  const [metricsRequireAuth, setMetricsRequireAuth] = useState(false)
  const [rotateMetricsToken, setRotateMetricsToken] = useState(false)
  const [newMetricsToken, setNewMetricsToken] = useState<string | null>(null)
  const [metricsTokenCopied, setMetricsTokenCopied] = useState(false)
  const [oidcEnabled, setOidcEnabled] = useState(false)
  const [oidcDisableLocalAuth, setOidcDisableLocalAuth] = useState(false)
  const [oidcProviderName, setOidcProviderName] = useState('Single sign-on')
  const [oidcTokenAuthMethod, setOidcTokenAuthMethod] = useState('client_secret_post')
  const [oidcDiscoveryUrl, setOidcDiscoveryUrl] = useState('')
  const [oidcClientId, setOidcClientId] = useState('')
  const [oidcClientSecret, setOidcClientSecret] = useState('')
  const [clearOidcClientSecret, setClearOidcClientSecret] = useState(false)
  const [oidcScopes, setOidcScopes] = useState('openid profile email')
  const [oidcRedirectUriOverride, setOidcRedirectUriOverride] = useState('')
  const [oidcEndSessionEndpointOverride, setOidcEndSessionEndpointOverride] = useState('')
  const [oidcClaimUsername, setOidcClaimUsername] = useState('preferred_username')
  const [oidcClaimEmail, setOidcClaimEmail] = useState('email')
  const [oidcClaimFullName, setOidcClaimFullName] = useState('name')
  const [oidcGroupClaim, setOidcGroupClaim] = useState('')
  const [oidcRoleClaim, setOidcRoleClaim] = useState('')
  const [oidcAdminGroups, setOidcAdminGroups] = useState('')
  const [oidcAllRepositoriesRoleClaim, setOidcAllRepositoriesRoleClaim] = useState('')
  const [oidcNewUserMode, setOidcNewUserMode] = useState('viewer')
  const [oidcTemplateUsername, setOidcTemplateUsername] = useState('')
  const [oidcDefaultRole, setOidcDefaultRole] = useState('viewer')
  const [oidcDefaultAllRepositoriesRole, setOidcDefaultAllRepositoriesRole] = useState('viewer')
  const [hasChanges, setHasChanges] = useState(false)
  const [browseChanged, setBrowseChanged] = useState(false)
  const [systemChanged, setSystemChanged] = useState(false)
  const [activeSection, setActiveSection] = useState(0)
  const [authEventFilter, setAuthEventFilter] = useState<AuthEventFilter>('all')

  const { data: cacheData, isLoading: cacheLoading } = useQuery({
    queryKey: ['cache-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getCacheStats()
      return response.data as CacheStats
    },
  })

  const { data: systemData, isLoading: systemLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  const { data: authConfigData } = useQuery({
    queryKey: ['authConfig'],
    queryFn: async () => {
      const response = await authAPI.getAuthConfig()
      return response.data
    },
  })

  const {
    data: authEventsData,
    isLoading: authEventsLoading,
    refetch: refetchAuthEvents,
  } = useQuery({
    queryKey: ['authEvents'],
    queryFn: async () => {
      const response = await authAPIAdmin.listEvents(20)
      return response.data
    },
    enabled: activeSection === 5,
  })

  const cacheStats = cacheData
  const systemSettings = systemData?.settings
  const timeoutSources = systemSettings?.timeout_sources as
    | Record<string, string | null>
    | undefined
  const proxyAuthConfig = authConfigData

  useEffect(() => {
    if (cacheStats) {
      setBrowseMaxItems(cacheStats.browse_max_items || 1_000_000)
      setBrowseMaxMemoryMb(cacheStats.browse_max_memory_mb || 1024)
    }
  }, [cacheStats])

  useEffect(() => {
    if (systemSettings) {
      setMountTimeout(systemSettings.mount_timeout || 120)
      setInfoTimeout(systemSettings.info_timeout || 600)
      setListTimeout(systemSettings.list_timeout || 600)
      setInitTimeout(systemSettings.init_timeout || 300)
      setBackupTimeout(systemSettings.backup_timeout || 3600)
      setSourceSizeTimeout(systemSettings.source_size_timeout || 3600)
      setMaxConcurrentScheduledBackups(systemSettings.max_concurrent_scheduled_backups ?? 2)
      setMaxConcurrentScheduledChecks(systemSettings.max_concurrent_scheduled_checks ?? 4)
      setStatsRefreshInterval(systemSettings.stats_refresh_interval_minutes ?? 60)
      setMetricsEnabled(systemSettings.metrics_enabled ?? false)
      setMetricsRequireAuth(systemSettings.metrics_require_auth ?? false)
      setRotateMetricsToken(false)
      setOidcEnabled(systemSettings.oidc_enabled ?? false)
      setOidcDisableLocalAuth(systemSettings.oidc_disable_local_auth ?? false)
      setOidcProviderName(systemSettings.oidc_provider_name ?? 'Single sign-on')
      setOidcTokenAuthMethod(systemSettings.oidc_token_auth_method ?? 'client_secret_post')
      setOidcDiscoveryUrl(systemSettings.oidc_discovery_url ?? '')
      setOidcClientId(systemSettings.oidc_client_id ?? '')
      setOidcClientSecret('')
      setClearOidcClientSecret(false)
      setOidcScopes(systemSettings.oidc_scopes ?? 'openid profile email')
      setOidcRedirectUriOverride(systemSettings.oidc_redirect_uri_override ?? '')
      setOidcEndSessionEndpointOverride(systemSettings.oidc_end_session_endpoint_override ?? '')
      setOidcClaimUsername(systemSettings.oidc_claim_username ?? 'preferred_username')
      setOidcClaimEmail(systemSettings.oidc_claim_email ?? 'email')
      setOidcClaimFullName(systemSettings.oidc_claim_full_name ?? 'name')
      setOidcGroupClaim(systemSettings.oidc_group_claim ?? '')
      setOidcRoleClaim(systemSettings.oidc_role_claim ?? '')
      setOidcAdminGroups(systemSettings.oidc_admin_groups ?? '')
      setOidcAllRepositoriesRoleClaim(systemSettings.oidc_all_repositories_role_claim ?? '')
      setOidcNewUserMode(systemSettings.oidc_new_user_mode ?? 'viewer')
      setOidcTemplateUsername(systemSettings.oidc_new_user_template_username ?? '')
      setOidcDefaultRole(systemSettings.oidc_default_role ?? 'viewer')
      setOidcDefaultAllRepositoriesRole(
        systemSettings.oidc_default_all_repositories_role ?? 'viewer'
      )
      setHasChanges(false)
    }
  }, [systemSettings])

  useEffect(() => {
    if (cacheStats && systemSettings) {
      const browseDirty =
        browseMaxItems !== (cacheStats.browse_max_items || 1_000_000) ||
        browseMaxMemoryMb !== (cacheStats.browse_max_memory_mb || 1024)
      const timeoutDirty =
        mountTimeout !== (systemSettings.mount_timeout || 120) ||
        infoTimeout !== (systemSettings.info_timeout || 600) ||
        listTimeout !== (systemSettings.list_timeout || 600) ||
        initTimeout !== (systemSettings.init_timeout || 300) ||
        backupTimeout !== (systemSettings.backup_timeout || 3600) ||
        sourceSizeTimeout !== (systemSettings.source_size_timeout || 3600) ||
        maxConcurrentScheduledBackups !== (systemSettings.max_concurrent_scheduled_backups ?? 2) ||
        maxConcurrentScheduledChecks !== (systemSettings.max_concurrent_scheduled_checks ?? 4)
      const statsRefreshDirty =
        statsRefreshInterval !== (systemSettings.stats_refresh_interval_minutes ?? 60)
      const metricsDirty =
        metricsEnabled !== (systemSettings.metrics_enabled ?? false) ||
        metricsRequireAuth !== (systemSettings.metrics_require_auth ?? false) ||
        rotateMetricsToken
      const oidcDirty =
        oidcEnabled !== (systemSettings.oidc_enabled ?? false) ||
        oidcDisableLocalAuth !== (systemSettings.oidc_disable_local_auth ?? false) ||
        oidcProviderName !== (systemSettings.oidc_provider_name ?? 'Single sign-on') ||
        oidcTokenAuthMethod !== (systemSettings.oidc_token_auth_method ?? 'client_secret_post') ||
        oidcDiscoveryUrl !== (systemSettings.oidc_discovery_url ?? '') ||
        oidcClientId !== (systemSettings.oidc_client_id ?? '') ||
        oidcClientSecret !== '' ||
        clearOidcClientSecret ||
        oidcScopes !== (systemSettings.oidc_scopes ?? 'openid profile email') ||
        oidcRedirectUriOverride !== (systemSettings.oidc_redirect_uri_override ?? '') ||
        oidcEndSessionEndpointOverride !==
          (systemSettings.oidc_end_session_endpoint_override ?? '') ||
        oidcClaimUsername !== (systemSettings.oidc_claim_username ?? 'preferred_username') ||
        oidcClaimEmail !== (systemSettings.oidc_claim_email ?? 'email') ||
        oidcClaimFullName !== (systemSettings.oidc_claim_full_name ?? 'name') ||
        oidcGroupClaim !== (systemSettings.oidc_group_claim ?? '') ||
        oidcRoleClaim !== (systemSettings.oidc_role_claim ?? '') ||
        oidcAdminGroups !== (systemSettings.oidc_admin_groups ?? '') ||
        oidcAllRepositoriesRoleClaim !== (systemSettings.oidc_all_repositories_role_claim ?? '') ||
        oidcNewUserMode !== (systemSettings.oidc_new_user_mode ?? 'viewer') ||
        oidcTemplateUsername !== (systemSettings.oidc_new_user_template_username ?? '') ||
        oidcDefaultRole !== (systemSettings.oidc_default_role ?? 'viewer') ||
        oidcDefaultAllRepositoriesRole !==
          (systemSettings.oidc_default_all_repositories_role ?? 'viewer')

      setBrowseChanged(browseDirty)
      setSystemChanged(timeoutDirty || statsRefreshDirty || metricsDirty || oidcDirty)
      setHasChanges(browseDirty || timeoutDirty || statsRefreshDirty || metricsDirty || oidcDirty)
    }
  }, [
    browseMaxItems,
    browseMaxMemoryMb,
    mountTimeout,
    infoTimeout,
    listTimeout,
    initTimeout,
    backupTimeout,
    sourceSizeTimeout,
    maxConcurrentScheduledBackups,
    maxConcurrentScheduledChecks,
    statsRefreshInterval,
    metricsEnabled,
    metricsRequireAuth,
    rotateMetricsToken,
    oidcEnabled,
    oidcDisableLocalAuth,
    oidcProviderName,
    oidcTokenAuthMethod,
    oidcDiscoveryUrl,
    oidcClientId,
    oidcClientSecret,
    clearOidcClientSecret,
    oidcScopes,
    oidcRedirectUriOverride,
    oidcEndSessionEndpointOverride,
    oidcClaimUsername,
    oidcClaimEmail,
    oidcClaimFullName,
    oidcGroupClaim,
    oidcRoleClaim,
    oidcAdminGroups,
    oidcAllRepositoriesRoleClaim,
    oidcNewUserMode,
    oidcTemplateUsername,
    oidcDefaultRole,
    oidcDefaultAllRepositoriesRole,
    cacheStats,
    systemSettings,
  ])

  const hasOidcActiveAdminSignal = getHasOidcActiveAdminSignal(systemSettings)
  const hasActiveOidcAdmin = getHasActiveOidcAdmin(systemSettings)

  const validationError = getSystemSettingsValidationError({
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
  })

  const saveBrowseLimitsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateCacheSettings(
        cacheStats?.cache_ttl_minutes || 120,
        cacheStats?.cache_max_size_mb || 2048,
        cacheStats?.redis_url || '',
        browseMaxItems,
        browseMaxMemoryMb
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = t('systemSettings.failedToSaveBrowseLimits')
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((errorItem: any) => errorItem.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = translateBackendKey(data.detail)
      }
      throw new Error(errorMsg)
    },
  })

  const saveTimeoutsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateSystemSettings({
        mount_timeout: mountTimeout,
        info_timeout: infoTimeout,
        list_timeout: listTimeout,
        init_timeout: initTimeout,
        backup_timeout: backupTimeout,
        source_size_timeout: sourceSizeTimeout,
        max_concurrent_scheduled_backups: maxConcurrentScheduledBackups,
        max_concurrent_scheduled_checks: maxConcurrentScheduledChecks,
        stats_refresh_interval_minutes: statsRefreshInterval,
        metrics_enabled: metricsEnabled,
        metrics_require_auth: metricsRequireAuth,
        rotate_metrics_token: rotateMetricsToken,
        oidc_enabled: oidcEnabled,
        oidc_disable_local_auth: oidcDisableLocalAuth,
        oidc_provider_name: oidcProviderName,
        oidc_token_auth_method: oidcTokenAuthMethod,
        oidc_discovery_url: oidcDiscoveryUrl,
        oidc_client_id: oidcClientId,
        oidc_client_secret: oidcClientSecret || undefined,
        clear_oidc_client_secret: clearOidcClientSecret,
        oidc_scopes: oidcScopes,
        oidc_redirect_uri_override: oidcRedirectUriOverride,
        oidc_end_session_endpoint_override: oidcEndSessionEndpointOverride,
        oidc_claim_username: oidcClaimUsername,
        oidc_claim_email: oidcClaimEmail,
        oidc_claim_full_name: oidcClaimFullName,
        oidc_group_claim: oidcGroupClaim,
        oidc_role_claim: oidcRoleClaim,
        oidc_admin_groups: oidcAdminGroups,
        oidc_all_repositories_role_claim: oidcAllRepositoriesRoleClaim,
        oidc_new_user_mode: oidcNewUserMode,
        oidc_new_user_template_username: oidcTemplateUsername,
        oidc_default_role: oidcDefaultRole,
        oidc_default_all_repositories_role: oidcDefaultAllRepositoriesRole,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = t('systemSettings.failedToSaveTimeoutSettings')
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((errorItem: any) => errorItem.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = translateBackendKey(data.detail)
      }
      throw new Error(errorMsg)
    },
  })

  const handleSaveSettings = async () => {
    if (validationError) {
      toast.error(validationError)
      return
    }

    try {
      const operations: Array<Promise<unknown>> = []
      let generatedMetricsToken: string | undefined

      if (browseChanged) {
        operations.push(saveBrowseLimitsMutation.mutateAsync())
      }
      if (systemChanged) {
        operations.push(
          saveTimeoutsMutation.mutateAsync().then((response) => {
            generatedMetricsToken = response?.data?.generated_metrics_token
            return response
          })
        )
      }

      if (operations.length === 0) {
        return
      }

      await Promise.all(operations)
      toast.success(t('systemSettings.savedSuccessfully'))
      setHasChanges(false)
      setRotateMetricsToken(false)
      setOidcClientSecret('')
      setClearOidcClientSecret(false)
      if (generatedMetricsToken) {
        setNewMetricsToken(generatedMetricsToken)
        setMetricsTokenCopied(false)
      }
      trackSystem(EventAction.EDIT, {
        section: 'system_settings',
        browse_max_items: browseMaxItems,
        browse_max_memory_mb: browseMaxMemoryMb,
        mount_timeout: mountTimeout,
        info_timeout: infoTimeout,
        list_timeout: listTimeout,
        init_timeout: initTimeout,
        backup_timeout: backupTimeout,
        source_size_timeout: sourceSizeTimeout,
        max_concurrent_scheduled_backups: maxConcurrentScheduledBackups,
        max_concurrent_scheduled_checks: maxConcurrentScheduledChecks,
        stats_refresh_interval_minutes: statsRefreshInterval,
        metrics_enabled: metricsEnabled,
        metrics_require_auth: metricsRequireAuth,
        rotate_metrics_token: rotateMetricsToken,
        oidc_enabled: oidcEnabled,
        oidc_disable_local_auth: oidcDisableLocalAuth,
        oidc_token_auth_method: oidcTokenAuthMethod,
        oidc_new_user_mode: oidcNewUserMode,
        oidc_default_role: oidcDefaultRole,
        oidc_default_all_repositories_role: oidcDefaultAllRepositoriesRole,
        oidc_group_claim: oidcGroupClaim,
        oidc_admin_groups: oidcAdminGroups,
        oidc_redirect_uri_override: oidcRedirectUriOverride,
        oidc_end_session_endpoint_override: oidcEndSessionEndpointOverride,
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.message || t('systemSettings.failedToSaveSettings'))
    }
  }

  const handleRefreshStats = async () => {
    setIsRefreshingStats(true)
    try {
      const response = await settingsAPI.refreshAllStats()
      const data = response.data
      toast.success(translateBackendKey(data.message) || t('systemSettings.statsRefreshStarted'))
      trackSystem(EventAction.START, { section: 'system_settings', operation: 'refresh_stats' })

      const startTime = Date.now()
      const maxWaitTime = 5 * 60 * 1000
      const pollInterval = setInterval(async () => {
        if (Date.now() - startTime > maxWaitTime) {
          clearInterval(pollInterval)
          setIsRefreshingStats(false)
          return
        }

        try {
          const settingsResponse = await settingsAPI.getSystemSettings()
          const newLastRefresh = settingsResponse.data?.settings?.last_stats_refresh
          if (newLastRefresh && new Date(newLastRefresh) > new Date(startTime)) {
            clearInterval(pollInterval)
            setIsRefreshingStats(false)
            toast.success(t('systemSettings.statsRefreshCompleted'))
            queryClient.invalidateQueries({ queryKey: ['repositories'] })
            queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
          }
        } catch {
          // Ignore polling errors
        }
      }, 3000)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('systemSettings.failedToStartStatsRefresh')
      )
      setIsRefreshingStats(false)
    }
  }

  const handleCopyMetricsToken = async () => {
    if (!newMetricsToken) return
    await navigator.clipboard.writeText(newMetricsToken)
    setMetricsTokenCopied(true)
    setTimeout(() => setMetricsTokenCopied(false), 2000)
  }

  const proxyAuthHeaderRows = buildProxyAuthHeaderRows(proxyAuthConfig)
  const sectionTabs = buildSectionTabs(t)

  const authEventStats = useMemo(() => {
    const events = authEventsData ?? []
    return {
      total: events.length,
      success: events.filter((event) => event.success).length,
      failed: events.filter((event) => !event.success).length,
      pending: events.filter((event) => event.event_type === 'oidc_user_pending').length,
      oidc: events.filter((event) => event.auth_source === 'oidc').length,
    }
  }, [authEventsData])

  const filteredAuthEvents = useMemo(() => {
    const events = authEventsData ?? []
    return events.filter((event) => {
      if (authEventFilter === 'failed') {
        return !event.success
      }
      if (authEventFilter === 'oidc') {
        return event.auth_source === 'oidc'
      }
      if (authEventFilter === 'pending') {
        return event.event_type === 'oidc_user_pending'
      }
      return true
    })
  }, [authEventFilter, authEventsData])

  const isLoading = cacheLoading || systemLoading
  const isSaving = saveBrowseLimitsMutation.isPending || saveTimeoutsMutation.isPending

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Stack spacing={3}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            gap: 1.5,
            mb: 1,
          }}
        >
          <Box>
            <Typography variant="h5" fontWeight={700} gutterBottom>
              {t('systemSettings.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('systemSettings.subtitle')}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={isSaving ? <CircularProgress size={16} /> : <Save size={16} />}
            onClick={handleSaveSettings}
            disabled={!hasChanges || isSaving || !!validationError}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            {isSaving ? t('systemSettings.saving') : t('systemSettings.save')}
          </Button>
        </Box>

        <SettingsSectionsCard
          activeSection={activeSection}
          sectionTabs={sectionTabs}
          onActiveSectionChange={setActiveSection}
        >
          {activeSection === 0 && (
            <OperationTimeoutsSection
              mountTimeout={mountTimeout}
              infoTimeout={infoTimeout}
              listTimeout={listTimeout}
              initTimeout={initTimeout}
              backupTimeout={backupTimeout}
              sourceSizeTimeout={sourceSizeTimeout}
              timeoutSources={timeoutSources}
              setMountTimeout={setMountTimeout}
              setInfoTimeout={setInfoTimeout}
              setListTimeout={setListTimeout}
              setInitTimeout={setInitTimeout}
              setBackupTimeout={setBackupTimeout}
              setSourceSizeTimeout={setSourceSizeTimeout}
            />
          )}

          {activeSection === 1 && (
            <RepositoryMonitoringSection
              statsRefreshInterval={statsRefreshInterval}
              maxConcurrentScheduledBackups={maxConcurrentScheduledBackups}
              maxConcurrentScheduledChecks={maxConcurrentScheduledChecks}
              isRefreshingStats={isRefreshingStats}
              lastStatsRefresh={systemSettings?.last_stats_refresh}
              setStatsRefreshInterval={setStatsRefreshInterval}
              setMaxConcurrentScheduledBackups={setMaxConcurrentScheduledBackups}
              setMaxConcurrentScheduledChecks={setMaxConcurrentScheduledChecks}
              onRefreshStats={handleRefreshStats}
            />
          )}

          {activeSection === 2 && (
            <MetricsAccessSection
              metricsEnabled={metricsEnabled}
              metricsRequireAuth={metricsRequireAuth}
              rotateMetricsToken={rotateMetricsToken}
              metricsTokenSet={systemSettings?.metrics_token_set}
              newMetricsToken={newMetricsToken}
              metricsTokenCopied={metricsTokenCopied}
              setMetricsEnabled={setMetricsEnabled}
              setMetricsRequireAuth={setMetricsRequireAuth}
              setRotateMetricsToken={setRotateMetricsToken}
              onCopyMetricsToken={handleCopyMetricsToken}
            />
          )}

          {activeSection === 3 && (
            <ArchiveBrowsingLimitsSection
              browseMaxItems={browseMaxItems}
              browseMaxMemoryMb={browseMaxMemoryMb}
              setBrowseMaxItems={setBrowseMaxItems}
              setBrowseMaxMemoryMb={setBrowseMaxMemoryMb}
            />
          )}

          {activeSection === 4 && (
            <ProxyAuthSection
              proxyAuthConfig={proxyAuthConfig}
              proxyAuthHeaderRows={proxyAuthHeaderRows}
            />
          )}

          {activeSection === 5 && (
            <OidcSection
              systemSettings={systemSettings}
              oidcEnabled={oidcEnabled}
              oidcDisableLocalAuth={oidcDisableLocalAuth}
              oidcProviderName={oidcProviderName}
              oidcTokenAuthMethod={oidcTokenAuthMethod}
              oidcDiscoveryUrl={oidcDiscoveryUrl}
              oidcClientId={oidcClientId}
              oidcClientSecret={oidcClientSecret}
              clearOidcClientSecret={clearOidcClientSecret}
              oidcScopes={oidcScopes}
              oidcRedirectUriOverride={oidcRedirectUriOverride}
              oidcEndSessionEndpointOverride={oidcEndSessionEndpointOverride}
              oidcClaimUsername={oidcClaimUsername}
              oidcClaimEmail={oidcClaimEmail}
              oidcClaimFullName={oidcClaimFullName}
              oidcGroupClaim={oidcGroupClaim}
              oidcRoleClaim={oidcRoleClaim}
              oidcAdminGroups={oidcAdminGroups}
              oidcAllRepositoriesRoleClaim={oidcAllRepositoriesRoleClaim}
              oidcNewUserMode={oidcNewUserMode}
              oidcTemplateUsername={oidcTemplateUsername}
              oidcDefaultRole={oidcDefaultRole}
              oidcDefaultAllRepositoriesRole={oidcDefaultAllRepositoriesRole}
              hasOidcActiveAdminSignal={hasOidcActiveAdminSignal}
              hasActiveOidcAdmin={hasActiveOidcAdmin}
              authEventsLoading={authEventsLoading}
              authEventsData={authEventsData}
              authEventStats={authEventStats}
              filteredAuthEvents={filteredAuthEvents}
              authEventFilter={authEventFilter}
              formatAuthEventType={(eventType) => formatAuthEventType(t, eventType)}
              formatAuthSource={(source) => formatAuthSource(t, source)}
              refetchAuthEvents={refetchAuthEvents}
              setOidcEnabled={setOidcEnabled}
              setOidcDisableLocalAuth={setOidcDisableLocalAuth}
              setOidcProviderName={setOidcProviderName}
              setOidcTokenAuthMethod={setOidcTokenAuthMethod}
              setOidcDiscoveryUrl={setOidcDiscoveryUrl}
              setOidcClientId={setOidcClientId}
              setOidcClientSecret={setOidcClientSecret}
              setClearOidcClientSecret={setClearOidcClientSecret}
              setOidcScopes={setOidcScopes}
              setOidcRedirectUriOverride={setOidcRedirectUriOverride}
              setOidcEndSessionEndpointOverride={setOidcEndSessionEndpointOverride}
              setOidcClaimUsername={setOidcClaimUsername}
              setOidcClaimEmail={setOidcClaimEmail}
              setOidcClaimFullName={setOidcClaimFullName}
              setOidcGroupClaim={setOidcGroupClaim}
              setOidcRoleClaim={setOidcRoleClaim}
              setOidcAdminGroups={setOidcAdminGroups}
              setOidcAllRepositoriesRoleClaim={setOidcAllRepositoriesRoleClaim}
              setOidcNewUserMode={setOidcNewUserMode}
              setOidcTemplateUsername={setOidcTemplateUsername}
              setOidcDefaultRole={setOidcDefaultRole}
              setOidcDefaultAllRepositoriesRole={setOidcDefaultAllRepositoriesRole}
              setAuthEventFilter={setAuthEventFilter}
            />
          )}
        </SettingsSectionsCard>
      </Stack>
    </Box>
  )
}

export default SystemSettingsTab
