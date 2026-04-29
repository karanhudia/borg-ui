import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  Stack,
  Alert,
  TextField,
  Divider,
  CircularProgress,
  FormControlLabel,
  Switch,
  Chip,
  IconButton,
  Tooltip,
  Tabs,
  Tab,
  MenuItem,
} from '@mui/material'
import {
  Save,
  AlertTriangle,
  Settings,
  Clock,
  RefreshCw,
  Copy,
  Check,
  Key,
  Info,
} from 'lucide-react'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { authAPI, authAPIAdmin, settingsAPI } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'

const SystemSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSystem, EventAction } = useAnalytics()

  // Local state for browse limits
  const [browseMaxItems, setBrowseMaxItems] = useState(1_000_000)
  const [browseMaxMemoryMb, setBrowseMaxMemoryMb] = useState(1024)

  // Local state for operation timeouts (in seconds)
  const [mountTimeout, setMountTimeout] = useState(120)
  const [infoTimeout, setInfoTimeout] = useState(600)
  const [listTimeout, setListTimeout] = useState(600)
  const [initTimeout, setInitTimeout] = useState(300)
  const [backupTimeout, setBackupTimeout] = useState(3600)
  const [sourceSizeTimeout, setSourceSizeTimeout] = useState(3600)
  const [maxConcurrentScheduledBackups, setMaxConcurrentScheduledBackups] = useState(2)
  const [maxConcurrentScheduledChecks, setMaxConcurrentScheduledChecks] = useState(4)

  // Local state for stats refresh
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
  const [authEventFilter, setAuthEventFilter] = useState<'all' | 'failed' | 'oidc' | 'pending'>(
    'all'
  )

  interface CacheStats {
    browse_max_items?: number
    browse_max_memory_mb?: number
    cache_ttl_minutes?: number
    cache_max_size_mb?: number
    redis_url?: string
  }

  // Fetch cache stats (which includes browse limits)
  const { data: cacheData, isLoading: cacheLoading } = useQuery({
    queryKey: ['cache-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getCacheStats()
      return response.data as CacheStats
    },
  })

  // Fetch system settings (which includes timeouts)
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
  const timeoutSources = systemData?.settings?.timeout_sources as
    | Record<string, string | null>
    | undefined
  const proxyAuthConfig = authConfigData

  // Helper to render source label with color
  const renderSourceLabel = (source: string | null | undefined) => {
    if (source === 'saved') {
      return (
        <Typography
          component="span"
          sx={{ color: 'success.main', fontSize: '0.7rem', fontWeight: 500 }}
        >
          {' '}
          {t('systemSettings.sourceCustomized')}
        </Typography>
      )
    }
    if (source === 'env') {
      return (
        <Typography
          component="span"
          sx={{ color: 'warning.main', fontSize: '0.7rem', fontWeight: 500 }}
        >
          {' '}
          {t('systemSettings.sourceFromEnv')}
        </Typography>
      )
    }
    return (
      <Typography component="span" sx={{ color: 'info.main', fontSize: '0.7rem', fontWeight: 500 }}>
        {' '}
        {t('systemSettings.sourceDefault')}
      </Typography>
    )
  }

  // Initialize form values from fetched settings
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

  // Track form changes
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

  // Validation constants
  const MIN_FILES = 100_000
  const MAX_FILES = 50_000_000
  const MIN_MEMORY = 100
  const MAX_MEMORY = 16384
  const MIN_TIMEOUT = 10
  const MAX_TIMEOUT = 86400 // 24 hours
  const MAX_STATS_REFRESH = 1440 // 24 hours in minutes
  const MAX_SCHEDULE_CONCURRENCY = 64
  const hasOidcActiveAdminSignal =
    systemSettings &&
    ('oidc_has_active_admin' in systemSettings ||
      'has_active_oidc_admin' in systemSettings ||
      'oidc_active_admin_available' in systemSettings ||
      'active_oidc_admin_available' in systemSettings ||
      'oidc_active_admin_count' in systemSettings)
  const hasActiveOidcAdmin =
    systemSettings?.oidc_has_active_admin === true ||
    systemSettings?.has_active_oidc_admin === true ||
    systemSettings?.oidc_active_admin_available === true ||
    systemSettings?.active_oidc_admin_available === true ||
    Number(systemSettings?.oidc_active_admin_count ?? 0) > 0

  const getValidationError = (): string | null => {
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
    if (timeouts.some((t) => t < MIN_TIMEOUT || t > MAX_TIMEOUT)) {
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
    if (oidcEnabled) {
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
    }
    return null
  }

  const validationError = getValidationError()

  // Save browse limits mutation
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
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = translateBackendKey(data.detail)
      }
      throw new Error(errorMsg)
    },
  })

  // Save timeouts and system settings mutation
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
        errorMsg = data.map((e: any) => e.msg).join(', ')
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

  const formatTimeout = (seconds: number): string => {
    if (seconds >= 3600) {
      const hours = seconds / 3600
      return `${hours.toFixed(1)} hour${hours !== 1 ? 's' : ''}`
    } else if (seconds >= 60) {
      const minutes = seconds / 60
      return `${minutes.toFixed(0)} minute${minutes !== 1 ? 's' : ''}`
    }
    return `${seconds} second${seconds !== 1 ? 's' : ''}`
  }

  // Handler for manual stats refresh
  const handleRefreshStats = async () => {
    setIsRefreshingStats(true)
    try {
      const response = await settingsAPI.refreshAllStats()
      const data = response.data
      toast.success(translateBackendKey(data.message) || t('systemSettings.statsRefreshStarted'))
      trackSystem(EventAction.START, { section: 'system_settings', operation: 'refresh_stats' })

      // Poll for completion by checking last_stats_refresh
      const startTime = Date.now()
      const maxWaitTime = 5 * 60 * 1000 // 5 minutes max polling
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
      }, 3000) // Poll every 3 seconds
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

  const isLoading = cacheLoading || systemLoading
  const isSaving = saveBrowseLimitsMutation.isPending || saveTimeoutsMutation.isPending
  const proxyAuthHeaderRows: Array<[string, string | null | undefined]> = [
    ['systemSettings.proxyAuthUsernameHeader', proxyAuthConfig?.proxy_auth_header],
    ['systemSettings.proxyAuthRoleHeader', proxyAuthConfig?.proxy_auth_role_header],
    [
      'systemSettings.proxyAuthAllRepositoriesRoleHeader',
      proxyAuthConfig?.proxy_auth_all_repositories_role_header,
    ],
    ['systemSettings.proxyAuthEmailHeader', proxyAuthConfig?.proxy_auth_email_header],
    ['systemSettings.proxyAuthFullNameHeader', proxyAuthConfig?.proxy_auth_full_name_header],
  ]
  const sectionTabs = [
    {
      label: t('systemSettings.operationTimeoutsTitle'),
      description: t('systemSettings.operationTimeoutsDescription'),
    },
    {
      label: t('systemSettings.repositoryMonitoringTitle'),
      description: t('systemSettings.repositoryMonitoringDescription'),
    },
    {
      label: t('systemSettings.metricsAccessTitle'),
      description: t('systemSettings.metricsAccessDescription'),
    },
    {
      label: t('systemSettings.archiveBrowsingLimitsTitle'),
      description: t('systemSettings.archiveBrowsingLimitsDescription'),
    },
    {
      label: t('systemSettings.proxyAuthTitle'),
      description: t('systemSettings.proxyAuthDescription'),
    },
    {
      label: t('systemSettings.oidcTitle'),
      description: t('systemSettings.oidcDescription'),
    },
  ]

  const formatAuthEventType = (eventType: string) => {
    const translationKey = `systemSettings.authEventTypes.${eventType}`
    const translated = t(translationKey)
    if (translated !== translationKey) {
      return translated
    }
    return eventType
      .split('_')
      .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
      .join(' ')
  }

  const formatAuthSource = (source: string) => {
    const translationKey = `systemSettings.authEventSources.${source}`
    const translated = t(translationKey)
    if (translated !== translationKey) {
      return translated
    }
    return source.charAt(0).toUpperCase() + source.slice(1)
  }

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

        <SettingsCard sx={{ overflow: 'hidden' }} contentSx={{ p: 0 }}>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs
              value={activeSection}
              onChange={(_, value) => setActiveSection(value)}
              variant="scrollable"
              scrollButtons="auto"
              allowScrollButtonsMobile
              sx={{ px: { xs: 1, md: 2 } }}
            >
              {[
                { label: sectionTabs[0].label, icon: <Clock size={15} /> },
                { label: sectionTabs[1].label, icon: <RefreshCw size={15} /> },
                { label: sectionTabs[2].label, icon: <Key size={15} /> },
                { label: sectionTabs[3].label, icon: <AlertTriangle size={15} /> },
                { label: sectionTabs[4].label, icon: <Settings size={15} /> },
                { label: sectionTabs[5].label, icon: <Key size={15} /> },
              ].map((section) => (
                <Tab
                  key={section.label}
                  label={section.label}
                  icon={section.icon}
                  iconPosition="start"
                  sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
                />
              ))}
            </Tabs>
          </Box>

          <Box sx={{ p: { xs: 2, md: 2.5 } }}>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {activeSection === 0 && <Clock size={22} />}
                {activeSection === 1 && <RefreshCw size={22} />}
                {activeSection === 2 && <Settings size={22} />}
                {activeSection === 3 && <AlertTriangle size={22} />}
                {activeSection === 4 && <Settings size={22} />}
                {activeSection === 5 && <Key size={22} />}
                <Typography variant="h6">{sectionTabs[activeSection].label}</Typography>
                {activeSection === 1 && (
                  <Tooltip title={t('systemSettings.manualRefreshAlert')} placement="right">
                    <Box
                      component="span"
                      sx={{ display: 'inline-flex', color: 'info.main', cursor: 'help', ml: 0.5 }}
                    >
                      <Info size={16} />
                    </Box>
                  </Tooltip>
                )}
                {activeSection === 2 && (
                  <Tooltip title={t('systemSettings.metricsHeaderHelp')} placement="right">
                    <Box
                      component="span"
                      sx={{ display: 'inline-flex', color: 'info.main', cursor: 'help', ml: 0.5 }}
                    >
                      <Info size={16} />
                    </Box>
                  </Tooltip>
                )}
                {activeSection === 3 && (
                  <Tooltip
                    title={
                      <>
                        <strong>{t('systemSettings.warningLabel')}</strong>{' '}
                        {t('systemSettings.largeLimitsWarning')}
                      </>
                    }
                    placement="right"
                  >
                    <Box
                      component="span"
                      sx={{
                        display: 'inline-flex',
                        color: 'warning.main',
                        cursor: 'help',
                        ml: 0.5,
                      }}
                    >
                      <AlertTriangle size={16} />
                    </Box>
                  </Tooltip>
                )}
              </Box>

              <Typography variant="body2" color="text.secondary">
                {sectionTabs[activeSection].description}
              </Typography>

              <Divider />

              {activeSection === 0 && (
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr', xl: '1fr 1fr 1fr' },
                    gap: 2,
                  }}
                >
                  <TextField
                    label={t('systemSettings.mountTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={mountTimeout}
                    onChange={(e) => setMountTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 10 }}
                    error={mountTimeout < MIN_TIMEOUT || mountTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.mountTimeoutHelper')} {formatTimeout(mountTimeout)}
                        {renderSourceLabel(timeoutSources?.mount_timeout)}
                      </>
                    }
                  />

                  <TextField
                    label={t('systemSettings.infoTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={infoTimeout}
                    onChange={(e) => setInfoTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                    error={infoTimeout < MIN_TIMEOUT || infoTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.infoTimeoutHelper')} {formatTimeout(infoTimeout)}
                        {renderSourceLabel(timeoutSources?.info_timeout)}
                      </>
                    }
                  />

                  <TextField
                    label={t('systemSettings.listTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={listTimeout}
                    onChange={(e) => setListTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                    error={listTimeout < MIN_TIMEOUT || listTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.listTimeoutHelper')} {formatTimeout(listTimeout)}
                        {renderSourceLabel(timeoutSources?.list_timeout)}
                      </>
                    }
                  />

                  <TextField
                    label={t('systemSettings.initTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={initTimeout}
                    onChange={(e) => setInitTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                    error={initTimeout < MIN_TIMEOUT || initTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.initTimeoutHelper')} {formatTimeout(initTimeout)}
                        {renderSourceLabel(timeoutSources?.init_timeout)}
                      </>
                    }
                  />

                  <TextField
                    label={t('systemSettings.backupTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={backupTimeout}
                    onChange={(e) => setBackupTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
                    error={backupTimeout < MIN_TIMEOUT || backupTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.backupTimeoutHelper')} {formatTimeout(backupTimeout)}
                        {renderSourceLabel(timeoutSources?.backup_timeout)}
                      </>
                    }
                  />

                  <TextField
                    label={t('systemSettings.sourceSizeTimeoutLabel')}
                    type="number"
                    fullWidth
                    value={sourceSizeTimeout}
                    onChange={(e) => setSourceSizeTimeout(Number(e.target.value))}
                    inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
                    error={sourceSizeTimeout < MIN_TIMEOUT || sourceSizeTimeout > MAX_TIMEOUT}
                    helperText={
                      <>
                        {t('systemSettings.sourceSizeTimeoutHelper')}{' '}
                        {formatTimeout(sourceSizeTimeout)}
                        {renderSourceLabel(timeoutSources?.source_size_timeout)}
                      </>
                    }
                  />
                </Box>
              )}

              {activeSection === 1 && (
                <Stack spacing={2.5}>
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', md: 'minmax(280px, 340px) auto' },
                      gap: 2,
                      alignItems: 'start',
                    }}
                  >
                    <TextField
                      label={t('systemSettings.statsRefreshIntervalLabel')}
                      type="number"
                      value={statsRefreshInterval}
                      onChange={(e) => setStatsRefreshInterval(Number(e.target.value))}
                      inputProps={{ min: 0, max: MAX_STATS_REFRESH, step: 15 }}
                      error={statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH}
                      helperText={
                        statsRefreshInterval === 0
                          ? t('systemSettings.statsRefreshDisabled')
                          : statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH
                            ? t('systemSettings.statsRefreshRangeError', {
                                max: MAX_STATS_REFRESH,
                              })
                            : t('systemSettings.statsRefreshIntervalHelper', {
                                interval: statsRefreshInterval,
                              })
                      }
                    />
                    <Button
                      variant="outlined"
                      onClick={handleRefreshStats}
                      disabled={isRefreshingStats}
                      startIcon={
                        isRefreshingStats ? <CircularProgress size={16} /> : <RefreshCw size={16} />
                      }
                      sx={{ justifySelf: { xs: 'stretch', md: 'start' }, height: 40 }}
                    >
                      {isRefreshingStats
                        ? t('systemSettings.refreshing')
                        : t('systemSettings.refreshNow')}
                    </Button>
                  </Box>

                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(240px, 320px))' },
                      gap: 2,
                    }}
                  >
                    <TextField
                      label={t('systemSettings.maxConcurrentScheduledBackupsLabel')}
                      type="number"
                      value={maxConcurrentScheduledBackups}
                      onChange={(e) => setMaxConcurrentScheduledBackups(Number(e.target.value))}
                      inputProps={{ min: 0, max: MAX_SCHEDULE_CONCURRENCY, step: 1 }}
                      error={
                        maxConcurrentScheduledBackups < 0 ||
                        maxConcurrentScheduledBackups > MAX_SCHEDULE_CONCURRENCY
                      }
                      helperText={t('systemSettings.maxConcurrentScheduledBackupsHelper')}
                    />

                    <TextField
                      label={t('systemSettings.maxConcurrentScheduledChecksLabel')}
                      type="number"
                      value={maxConcurrentScheduledChecks}
                      onChange={(e) => setMaxConcurrentScheduledChecks(Number(e.target.value))}
                      inputProps={{ min: 0, max: MAX_SCHEDULE_CONCURRENCY, step: 1 }}
                      error={
                        maxConcurrentScheduledChecks < 0 ||
                        maxConcurrentScheduledChecks > MAX_SCHEDULE_CONCURRENCY
                      }
                      helperText={t('systemSettings.maxConcurrentScheduledChecksHelper')}
                    />
                  </Box>

                  {systemSettings?.last_stats_refresh && (
                    <Alert severity="info">
                      <Typography variant="body2">
                        {t('systemSettings.lastRefreshed')}{' '}
                        {new Date(systemSettings.last_stats_refresh).toLocaleString()}
                      </Typography>
                    </Alert>
                  )}
                </Stack>
              )}

              {activeSection === 2 && (
                <Stack spacing={2}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={metricsEnabled}
                        onChange={(e) => {
                          const enabled = e.target.checked
                          setMetricsEnabled(enabled)
                          if (!enabled) {
                            setMetricsRequireAuth(false)
                            setRotateMetricsToken(false)
                          }
                        }}
                      />
                    }
                    label={t('systemSettings.metricsEnabledLabel')}
                  />

                  <FormControlLabel
                    control={
                      <Switch
                        checked={metricsRequireAuth}
                        disabled={!metricsEnabled}
                        onChange={(e) => {
                          const enabled = e.target.checked
                          setMetricsRequireAuth(enabled)
                          if (!enabled) {
                            setRotateMetricsToken(false)
                          }
                        }}
                      />
                    }
                    label={t('systemSettings.metricsRequireAuthLabel')}
                  />

                  <Box
                    sx={{
                      display: 'flex',
                      flexDirection: { xs: 'column', md: 'row' },
                      gap: 1.5,
                      alignItems: { xs: 'stretch', md: 'center' },
                    }}
                  >
                    <Button
                      variant="outlined"
                      startIcon={<Key size={16} />}
                      disabled={!metricsEnabled || !metricsRequireAuth}
                      onClick={() => setRotateMetricsToken(true)}
                    >
                      {systemSettings?.metrics_token_set
                        ? t('systemSettings.metricsRotateToken')
                        : t('systemSettings.metricsGenerateToken')}
                    </Button>
                    <Typography variant="body2" color="text.secondary">
                      {!metricsEnabled || !metricsRequireAuth
                        ? t('systemSettings.metricsTokenDisabledHelper')
                        : rotateMetricsToken
                          ? t('systemSettings.metricsTokenWillRotate')
                          : systemSettings?.metrics_token_set
                            ? t('systemSettings.metricsTokenConfigured')
                            : t('systemSettings.metricsTokenWillGenerate')}
                    </Typography>
                  </Box>

                  {newMetricsToken && (
                    <Box
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: 'success.main',
                        bgcolor: 'rgba(76, 175, 80, 0.06)',
                      }}
                    >
                      <Stack spacing={1.5}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                          <AlertTriangle size={13} color="orange" />
                          <Typography variant="caption" fontWeight={600} color="warning.main">
                            {t('systemSettings.metricsTokenDialogWarning')}
                          </Typography>
                        </Box>
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 1,
                            px: 1.5,
                            py: 1,
                            borderRadius: 1.5,
                            bgcolor: 'background.default',
                            border: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          <Typography
                            sx={{
                              flex: 1,
                              fontFamily: 'monospace',
                              fontSize: '0.78rem',
                              color: 'text.primary',
                              wordBreak: 'break-all',
                              lineHeight: 1.6,
                              userSelect: 'all',
                            }}
                          >
                            {newMetricsToken}
                          </Typography>
                          <Tooltip
                            title={
                              metricsTokenCopied
                                ? t('systemSettings.metricsTokenCopied')
                                : t('common.buttons.copy')
                            }
                          >
                            <IconButton
                              size="small"
                              onClick={handleCopyMetricsToken}
                              color={metricsTokenCopied ? 'success' : 'default'}
                              sx={{ flexShrink: 0 }}
                            >
                              {metricsTokenCopied ? <Check size={15} /> : <Copy size={15} />}
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </Stack>
                    </Box>
                  )}
                </Stack>
              )}

              {activeSection === 3 && (
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' },
                    gap: 2,
                  }}
                >
                  <TextField
                    label={t('systemSettings.maxFilesToLoadLabel')}
                    type="number"
                    fullWidth
                    value={browseMaxItems}
                    onChange={(e) => setBrowseMaxItems(Number(e.target.value))}
                    inputProps={{ min: MIN_FILES, max: MAX_FILES, step: 100_000 }}
                    error={browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES}
                    helperText={
                      browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES
                        ? t('systemSettings.maxFilesRangeError', {
                            min: MIN_FILES.toLocaleString(),
                            max: MAX_FILES.toLocaleString(),
                          })
                        : t('systemSettings.maxFilesHelperText', {
                            current: (browseMaxItems / 1_000_000).toFixed(1),
                          })
                    }
                  />

                  <TextField
                    label={t('systemSettings.maxMemoryLabel')}
                    type="number"
                    fullWidth
                    value={browseMaxMemoryMb}
                    onChange={(e) => setBrowseMaxMemoryMb(Number(e.target.value))}
                    inputProps={{ min: MIN_MEMORY, max: MAX_MEMORY, step: 128 }}
                    error={browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY}
                    helperText={
                      browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY
                        ? t('systemSettings.maxMemoryRangeError', {
                            min: MIN_MEMORY,
                            max: MAX_MEMORY,
                          })
                        : t('systemSettings.maxMemoryHelperText', {
                            current: (browseMaxMemoryMb / 1024).toFixed(2),
                          })
                    }
                  />
                </Box>
              )}

              {activeSection === 4 && (
                <Stack spacing={2}>
                  <Alert
                    severity={proxyAuthConfig?.proxy_auth_enabled ? 'info' : 'success'}
                    variant="outlined"
                  >
                    <Typography variant="body2">
                      {proxyAuthConfig?.proxy_auth_enabled
                        ? t('systemSettings.proxyAuthEnabledStatus')
                        : t('systemSettings.proxyAuthDisabledStatus')}
                    </Typography>
                  </Alert>

                  {proxyAuthConfig?.proxy_auth_enabled ? (
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                        gap: 2,
                      }}
                    >
                      {proxyAuthHeaderRows.map(([labelKey, value]) => (
                        <Box
                          key={labelKey}
                          sx={{
                            p: 2,
                            borderRadius: 2,
                            border: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            {t(labelKey)}
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{ mt: 0.5, fontFamily: 'monospace', wordBreak: 'break-word' }}
                          >
                            {value || t('systemSettings.proxyAuthNotConfigured')}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  ) : null}

                  {proxyAuthConfig?.proxy_auth_health?.warnings?.length ? (
                    <Alert severity="warning">
                      <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>
                        {t('systemSettings.proxyAuthWarningsTitle')}
                      </Typography>
                      <Stack spacing={0.75}>
                        {proxyAuthConfig.proxy_auth_health.warnings.map((warning) => (
                          <Typography key={warning.code} variant="body2">
                            • {warning.message}
                          </Typography>
                        ))}
                      </Stack>
                    </Alert>
                  ) : proxyAuthConfig?.proxy_auth_enabled ? (
                    <Alert severity="success">
                      <Typography variant="body2">
                        {t('systemSettings.proxyAuthNoWarnings')}
                      </Typography>
                    </Alert>
                  ) : null}
                </Stack>
              )}

              {activeSection === 5 && (
                <Stack spacing={2.5}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={oidcEnabled}
                        onChange={(e) => setOidcEnabled(e.target.checked)}
                      />
                    }
                    label={t('systemSettings.oidcEnabledLabel')}
                  />

                  <FormControlLabel
                    control={
                      <Switch
                        checked={oidcDisableLocalAuth}
                        disabled={!oidcEnabled}
                        onChange={(e) => setOidcDisableLocalAuth(e.target.checked)}
                      />
                    }
                    label={t('systemSettings.oidcDisableLocalAuthLabel')}
                  />

                  {oidcEnabled && oidcDisableLocalAuth && (
                    <Alert
                      severity={
                        hasOidcActiveAdminSignal && !hasActiveOidcAdmin ? 'error' : 'warning'
                      }
                    >
                      <Typography variant="body2">
                        {hasOidcActiveAdminSignal && !hasActiveOidcAdmin
                          ? t('systemSettings.oidcActiveAdminRequired')
                          : t('systemSettings.oidcDisableLocalAuthWarning')}
                      </Typography>
                    </Alert>
                  )}

                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' },
                      gap: 2,
                    }}
                  >
                    <TextField
                      label={t('systemSettings.oidcProviderNameLabel')}
                      value={oidcProviderName}
                      onChange={(e) => setOidcProviderName(e.target.value)}
                      helperText={t('systemSettings.oidcProviderNameHelper')}
                    />
                    <TextField
                      select
                      label={t('systemSettings.oidcTokenAuthMethodLabel')}
                      value={oidcTokenAuthMethod}
                      onChange={(e) => setOidcTokenAuthMethod(e.target.value)}
                      helperText={t('systemSettings.oidcTokenAuthMethodHelper')}
                    >
                      <MenuItem value="client_secret_post">
                        {t('systemSettings.oidcTokenAuthMethodPost')}
                      </MenuItem>
                      <MenuItem value="client_secret_basic">
                        {t('systemSettings.oidcTokenAuthMethodBasic')}
                      </MenuItem>
                    </TextField>
                    <TextField
                      label={t('systemSettings.oidcDiscoveryUrlLabel')}
                      value={oidcDiscoveryUrl}
                      onChange={(e) => setOidcDiscoveryUrl(e.target.value)}
                      helperText={t('systemSettings.oidcDiscoveryUrlHelper')}
                    />
                    <TextField
                      label={t('systemSettings.oidcClientIdLabel')}
                      value={oidcClientId}
                      onChange={(e) => setOidcClientId(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcClientSecretLabel')}
                      type="password"
                      value={oidcClientSecret}
                      onChange={(e) => setOidcClientSecret(e.target.value)}
                      helperText={
                        systemSettings?.oidc_client_secret_set
                          ? t('systemSettings.oidcClientSecretConfigured')
                          : t('systemSettings.oidcClientSecretRequiredHelper')
                      }
                    />
                    <TextField
                      label={t('systemSettings.oidcScopesLabel')}
                      value={oidcScopes}
                      onChange={(e) => setOidcScopes(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcRedirectUriOverrideLabel')}
                      value={oidcRedirectUriOverride}
                      onChange={(e) => setOidcRedirectUriOverride(e.target.value)}
                      helperText={t('systemSettings.oidcRedirectUriOverrideHelper')}
                    />
                    <TextField
                      label={t('systemSettings.oidcEndSessionEndpointOverrideLabel')}
                      value={oidcEndSessionEndpointOverride}
                      onChange={(e) => setOidcEndSessionEndpointOverride(e.target.value)}
                      helperText={t('systemSettings.oidcEndSessionEndpointOverrideHelper')}
                    />
                    <TextField
                      label={t('systemSettings.oidcClaimUsernameLabel')}
                      value={oidcClaimUsername}
                      onChange={(e) => setOidcClaimUsername(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcClaimEmailLabel')}
                      value={oidcClaimEmail}
                      onChange={(e) => setOidcClaimEmail(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcClaimFullNameLabel')}
                      value={oidcClaimFullName}
                      onChange={(e) => setOidcClaimFullName(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcGroupClaimLabel')}
                      value={oidcGroupClaim}
                      onChange={(e) => setOidcGroupClaim(e.target.value)}
                      helperText={t('systemSettings.oidcGroupClaimHelper')}
                    />
                    <TextField
                      label={t('systemSettings.oidcRoleClaimLabel')}
                      value={oidcRoleClaim}
                      onChange={(e) => setOidcRoleClaim(e.target.value)}
                    />
                    <TextField
                      label={t('systemSettings.oidcAdminGroupsLabel')}
                      value={oidcAdminGroups}
                      onChange={(e) => setOidcAdminGroups(e.target.value)}
                      helperText={t('systemSettings.oidcAdminGroupsHelper')}
                    />
                    <TextField
                      label={t('systemSettings.oidcAllRepositoriesRoleClaimLabel')}
                      value={oidcAllRepositoriesRoleClaim}
                      onChange={(e) => setOidcAllRepositoriesRoleClaim(e.target.value)}
                    />
                    <TextField
                      select
                      label={t('systemSettings.oidcNewUserModeLabel')}
                      value={oidcNewUserMode}
                      onChange={(e) => setOidcNewUserMode(e.target.value)}
                    >
                      <MenuItem value="deny">{t('systemSettings.oidcModeDeny')}</MenuItem>
                      <MenuItem value="viewer">{t('systemSettings.oidcModeViewer')}</MenuItem>
                      <MenuItem value="pending">{t('systemSettings.oidcModePending')}</MenuItem>
                      <MenuItem value="template">{t('systemSettings.oidcModeTemplate')}</MenuItem>
                    </TextField>
                    <TextField
                      label={t('systemSettings.oidcTemplateUsernameLabel')}
                      value={oidcTemplateUsername}
                      disabled={oidcNewUserMode !== 'template'}
                      onChange={(e) => setOidcTemplateUsername(e.target.value)}
                    />
                    <TextField
                      select
                      label={t('systemSettings.oidcDefaultRoleLabel')}
                      value={oidcDefaultRole}
                      onChange={(e) => setOidcDefaultRole(e.target.value)}
                    >
                      <MenuItem value="viewer">{t('systemSettings.roleViewer')}</MenuItem>
                      <MenuItem value="operator">{t('systemSettings.roleOperator')}</MenuItem>
                      <MenuItem value="admin">{t('systemSettings.roleAdmin')}</MenuItem>
                    </TextField>
                    <TextField
                      select
                      label={t('systemSettings.oidcDefaultAllRepositoriesRoleLabel')}
                      value={oidcDefaultAllRepositoriesRole}
                      onChange={(e) => setOidcDefaultAllRepositoriesRole(e.target.value)}
                    >
                      <MenuItem value="viewer">{t('systemSettings.roleViewer')}</MenuItem>
                      <MenuItem value="operator">{t('systemSettings.roleOperator')}</MenuItem>
                    </TextField>
                  </Box>

                  <FormControlLabel
                    control={
                      <Switch
                        checked={clearOidcClientSecret}
                        disabled={!systemSettings?.oidc_client_secret_set}
                        onChange={(e) => setClearOidcClientSecret(e.target.checked)}
                      />
                    }
                    label={t('systemSettings.oidcClearClientSecretLabel')}
                  />

                  <Divider />

                  <Stack spacing={1.25}>
                    <Stack
                      direction={{ xs: 'column', md: 'row' }}
                      spacing={1.5}
                      justifyContent="space-between"
                      alignItems={{ xs: 'stretch', md: 'flex-start' }}
                    >
                      <Box>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {t('systemSettings.oidcEventsTitle')}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {t('systemSettings.oidcEventsDescription')}
                        </Typography>
                      </Box>
                      <Tooltip title={t('systemSettings.oidcEventsRefresh')}>
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => refetchAuthEvents()}
                            disabled={authEventsLoading}
                          >
                            <RefreshCw size={16} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Stack>

                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={t('systemSettings.authEventSummary.total', {
                          count: authEventStats.total,
                        })}
                      />
                      <Chip
                        size="small"
                        color="success"
                        variant="outlined"
                        label={t('systemSettings.authEventSummary.success', {
                          count: authEventStats.success,
                        })}
                      />
                      <Chip
                        size="small"
                        color="error"
                        variant="outlined"
                        label={t('systemSettings.authEventSummary.failed', {
                          count: authEventStats.failed,
                        })}
                      />
                      <Chip
                        size="small"
                        color="warning"
                        variant="outlined"
                        label={t('systemSettings.authEventSummary.pending', {
                          count: authEventStats.pending,
                        })}
                      />
                    </Stack>

                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {(
                        [
                          ['all', 'systemSettings.authEventFilters.all'],
                          ['failed', 'systemSettings.authEventFilters.failed'],
                          ['oidc', 'systemSettings.authEventFilters.oidc'],
                          ['pending', 'systemSettings.authEventFilters.pending'],
                        ] as const
                      ).map(([value, labelKey]) => (
                        <Chip
                          key={value}
                          size="small"
                          label={t(labelKey)}
                          clickable
                          color={authEventFilter === value ? 'primary' : 'default'}
                          variant={authEventFilter === value ? 'filled' : 'outlined'}
                          onClick={() => setAuthEventFilter(value)}
                        />
                      ))}
                    </Stack>

                    {authEventsLoading ? (
                      <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                        <CircularProgress size={20} />
                      </Box>
                    ) : (authEventsData?.length ?? 0) === 0 ? (
                      <Alert severity="info">{t('systemSettings.oidcEventsEmpty')}</Alert>
                    ) : filteredAuthEvents.length === 0 ? (
                      <Alert severity="info">{t('systemSettings.oidcEventsFilteredEmpty')}</Alert>
                    ) : (
                      <Stack spacing={1}>
                        {filteredAuthEvents.map((event) => {
                          const isPendingEvent = event.event_type === 'oidc_user_pending'
                          return (
                            <Box
                              key={event.id}
                              sx={{
                                border: '1px solid',
                                borderColor: isPendingEvent ? 'warning.light' : 'divider',
                                borderRadius: 2,
                                px: 1.5,
                                py: 1.25,
                                bgcolor: isPendingEvent
                                  ? 'rgba(245, 158, 11, 0.06)'
                                  : 'transparent',
                              }}
                            >
                              <Stack
                                direction={{ xs: 'column', md: 'row' }}
                                spacing={1.5}
                                justifyContent="space-between"
                              >
                                <Stack spacing={0.4}>
                                  <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                    <Chip
                                      size="small"
                                      label={formatAuthEventType(event.event_type)}
                                      color={isPendingEvent ? 'warning' : 'default'}
                                      variant={isPendingEvent ? 'filled' : 'outlined'}
                                    />
                                    <Chip
                                      size="small"
                                      label={formatAuthSource(event.auth_source)}
                                      variant="outlined"
                                      color={event.auth_source === 'oidc' ? 'info' : 'default'}
                                    />
                                  </Stack>
                                  <Typography variant="body2" fontWeight={600}>
                                    {event.username ||
                                      event.email ||
                                      t('systemSettings.authEventAnonymous')}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {[
                                      event.email,
                                      event.actor_user_id
                                        ? t('systemSettings.authEventActor', {
                                            id: event.actor_user_id,
                                          })
                                        : null,
                                    ]
                                      .filter(Boolean)
                                      .join(' • ')}
                                  </Typography>
                                  {event.detail && (
                                    <Typography variant="caption" color="text.secondary">
                                      {event.detail}
                                    </Typography>
                                  )}
                                </Stack>
                                <Stack
                                  spacing={0.4}
                                  alignItems={{ xs: 'flex-start', md: 'flex-end' }}
                                >
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      color: isPendingEvent
                                        ? 'warning.main'
                                        : event.success
                                          ? 'success.main'
                                          : 'error.main',
                                      fontWeight: 600,
                                    }}
                                  >
                                    {isPendingEvent
                                      ? t('systemSettings.authEventPending')
                                      : event.success
                                        ? t('systemSettings.authEventSuccess')
                                        : t('systemSettings.authEventFailed')}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {new Date(event.created_at).toLocaleString()}
                                  </Typography>
                                </Stack>
                              </Stack>
                            </Box>
                          )
                        })}
                      </Stack>
                    )}
                  </Stack>
                </Stack>
              )}
            </Stack>
          </Box>
        </SettingsCard>
      </Stack>
    </Box>
  )
}

export default SystemSettingsTab
