import React, { useState, useEffect } from 'react'
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
  IconButton,
  Tooltip,
  Tabs,
  Tab,
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
import { authAPI, settingsAPI } from '../services/api'
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

  // Local state for stats refresh
  const [statsRefreshInterval, setStatsRefreshInterval] = useState(60)
  const [isRefreshingStats, setIsRefreshingStats] = useState(false)
  const [metricsEnabled, setMetricsEnabled] = useState(false)
  const [metricsRequireAuth, setMetricsRequireAuth] = useState(false)
  const [rotateMetricsToken, setRotateMetricsToken] = useState(false)
  const [newMetricsToken, setNewMetricsToken] = useState<string | null>(null)
  const [metricsTokenCopied, setMetricsTokenCopied] = useState(false)

  const [hasChanges, setHasChanges] = useState(false)
  const [browseChanged, setBrowseChanged] = useState(false)
  const [systemChanged, setSystemChanged] = useState(false)
  const [activeSection, setActiveSection] = useState(0)

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
      setStatsRefreshInterval(systemSettings.stats_refresh_interval_minutes ?? 60)
      setMetricsEnabled(systemSettings.metrics_enabled ?? false)
      setMetricsRequireAuth(systemSettings.metrics_require_auth ?? false)
      setRotateMetricsToken(false)
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
        sourceSizeTimeout !== (systemSettings.source_size_timeout || 3600)

      const statsRefreshDirty =
        statsRefreshInterval !== (systemSettings.stats_refresh_interval_minutes ?? 60)

      const metricsDirty =
        metricsEnabled !== (systemSettings.metrics_enabled ?? false) ||
        metricsRequireAuth !== (systemSettings.metrics_require_auth ?? false) ||
        rotateMetricsToken

      setBrowseChanged(browseDirty)
      setSystemChanged(timeoutDirty || statsRefreshDirty || metricsDirty)
      setHasChanges(browseDirty || timeoutDirty || statsRefreshDirty || metricsDirty)
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
    statsRefreshInterval,
    metricsEnabled,
    metricsRequireAuth,
    rotateMetricsToken,
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
        stats_refresh_interval_minutes: statsRefreshInterval,
        metrics_enabled: metricsEnabled,
        metrics_require_auth: metricsRequireAuth,
        rotate_metrics_token: rotateMetricsToken,
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
        stats_refresh_interval_minutes: statsRefreshInterval,
        metrics_enabled: metricsEnabled,
        metrics_require_auth: metricsRequireAuth,
        rotate_metrics_token: rotateMetricsToken,
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
  ]

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
            </Stack>
          </Box>
        </SettingsCard>
      </Stack>
    </Box>
  )
}

export default SystemSettingsTab
