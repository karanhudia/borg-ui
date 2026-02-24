import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Stack,
  Alert,
  TextField,
  Divider,
  CircularProgress,
} from '@mui/material'
import { Save, AlertTriangle, Settings, Clock, RefreshCw } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

const SystemSettingsTab: React.FC = () => {
  const queryClient = useQueryClient()

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

  const [hasChanges, setHasChanges] = useState(false)

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

  const cacheStats = cacheData
  const systemSettings = systemData?.settings
  const timeoutSources = systemData?.settings?.timeout_sources as
    | Record<string, string | null>
    | undefined

  // Helper to render source label with color
  const renderSourceLabel = (source: string | null | undefined) => {
    if (source === 'saved') {
      return (
        <Typography
          component="span"
          sx={{ color: 'success.main', fontSize: '0.7rem', fontWeight: 500 }}
        >
          {' '}
          [customized]
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
          [from env]
        </Typography>
      )
    }
    return (
      <Typography component="span" sx={{ color: 'info.main', fontSize: '0.7rem', fontWeight: 500 }}>
        {' '}
        [default]
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
      setHasChanges(false)
    }
  }, [systemSettings])

  // Track form changes
  useEffect(() => {
    if (cacheStats && systemSettings) {
      const browseChanged =
        browseMaxItems !== (cacheStats.browse_max_items || 1_000_000) ||
        browseMaxMemoryMb !== (cacheStats.browse_max_memory_mb || 1024)

      const timeoutChanged =
        mountTimeout !== (systemSettings.mount_timeout || 120) ||
        infoTimeout !== (systemSettings.info_timeout || 600) ||
        listTimeout !== (systemSettings.list_timeout || 600) ||
        initTimeout !== (systemSettings.init_timeout || 300) ||
        backupTimeout !== (systemSettings.backup_timeout || 3600) ||
        sourceSizeTimeout !== (systemSettings.source_size_timeout || 3600)

      const statsRefreshChanged =
        statsRefreshInterval !== (systemSettings.stats_refresh_interval_minutes ?? 60)

      setHasChanges(browseChanged || timeoutChanged || statsRefreshChanged)
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
      let errorMsg = 'Failed to save browse limits'
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = data.detail
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
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = 'Failed to save timeout settings'
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = data.detail
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
      await Promise.all([
        saveBrowseLimitsMutation.mutateAsync(),
        saveTimeoutsMutation.mutateAsync(),
      ])
      toast.success('System settings saved successfully')
      setHasChanges(false)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.message || 'Failed to save settings')
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
      toast.success(data.message || 'Stats refresh started')

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
            toast.success('Stats refresh completed')
            queryClient.invalidateQueries({ queryKey: ['repositories'] })
            queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
          }
        } catch {
          // Ignore polling errors
        }
      }, 3000) // Poll every 3 seconds
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to start stats refresh')
      setIsRefreshingStats(false)
    }
  }

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
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box>
            <Typography variant="h5" fontWeight={700} gutterBottom>
              System Settings
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Configure system-wide settings, resource limits, and operation timeouts
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={isSaving ? <CircularProgress size={16} /> : <Save size={16} />}
            onClick={handleSaveSettings}
            disabled={!hasChanges || isSaving || !!validationError}
          >
            {isSaving ? 'Saving...' : 'Save Settings'}
          </Button>
        </Box>

        {/* Operation Timeouts Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Clock size={24} />
                <Typography variant="h6">Operation Timeouts</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Configure timeouts for various borg operations. Increase these for very large
                repositories (multi-terabyte, hundreds of archives) that may take longer to process.
              </Typography>
              <Divider />

              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' },
                  gap: 3,
                }}
              >
                <TextField
                  label="Mount Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={mountTimeout}
                  onChange={(e) => setMountTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 10 }}
                  error={mountTimeout < MIN_TIMEOUT || mountTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For mounting archives. {formatTimeout(mountTimeout)}
                      {renderSourceLabel(timeoutSources?.mount_timeout)}
                    </>
                  }
                />

                <TextField
                  label="Info Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={infoTimeout}
                  onChange={(e) => setInfoTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={infoTimeout < MIN_TIMEOUT || infoTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For borg info commands. {formatTimeout(infoTimeout)}
                      {renderSourceLabel(timeoutSources?.info_timeout)}
                    </>
                  }
                />

                <TextField
                  label="List Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={listTimeout}
                  onChange={(e) => setListTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={listTimeout < MIN_TIMEOUT || listTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For listing archives. {formatTimeout(listTimeout)}
                      {renderSourceLabel(timeoutSources?.list_timeout)}
                    </>
                  }
                />

                <TextField
                  label="Init Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={initTimeout}
                  onChange={(e) => setInitTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={initTimeout < MIN_TIMEOUT || initTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For repository init. {formatTimeout(initTimeout)}
                      {renderSourceLabel(timeoutSources?.init_timeout)}
                    </>
                  }
                />

                <TextField
                  label="Backup/Restore Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={backupTimeout}
                  onChange={(e) => setBackupTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
                  error={backupTimeout < MIN_TIMEOUT || backupTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For backup/restore. {formatTimeout(backupTimeout)}
                      {renderSourceLabel(timeoutSources?.backup_timeout)}
                    </>
                  }
                />

                <TextField
                  label="Source Size Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={sourceSizeTimeout}
                  onChange={(e) => setSourceSizeTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
                  error={sourceSizeTimeout < MIN_TIMEOUT || sourceSizeTimeout > MAX_TIMEOUT}
                  helperText={
                    <>
                      For source size calculation (du). {formatTimeout(sourceSizeTimeout)}
                      {renderSourceLabel(timeoutSources?.source_size_timeout)}
                    </>
                  }
                />
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Repository Monitoring Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <RefreshCw size={24} />
                <Typography variant="h6">Repository Monitoring</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Configure automatic refresh of repository statistics. This keeps dashboard data
                up-to-date, especially useful for observe-only repositories where backups are
                managed externally.
              </Typography>
              <Divider />

              <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
                <TextField
                  label="Stats Refresh Interval (minutes)"
                  type="number"
                  value={statsRefreshInterval}
                  onChange={(e) => setStatsRefreshInterval(Number(e.target.value))}
                  inputProps={{ min: 0, max: MAX_STATS_REFRESH, step: 15 }}
                  error={statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH}
                  helperText={
                    statsRefreshInterval === 0
                      ? 'Automatic stats refresh is disabled'
                      : statsRefreshInterval < 0 || statsRefreshInterval > MAX_STATS_REFRESH
                        ? `Must be between 0 and ${MAX_STATS_REFRESH} minutes`
                        : `Repository stats (archive count, size, last backup) will be refreshed every ${statsRefreshInterval} minutes`
                  }
                  sx={{ width: 300 }}
                />
                <Button
                  variant="outlined"
                  onClick={handleRefreshStats}
                  disabled={isRefreshingStats}
                  startIcon={
                    isRefreshingStats ? <CircularProgress size={16} /> : <RefreshCw size={16} />
                  }
                  sx={{ height: 40 }}
                >
                  {isRefreshingStats ? 'Refreshing...' : 'Refresh Now'}
                </Button>
              </Box>

              {systemSettings?.last_stats_refresh && (
                <Typography variant="body2" color="text.secondary">
                  Last refreshed: {new Date(systemSettings.last_stats_refresh).toLocaleString()}
                </Typography>
              )}

              <Alert severity="info">
                Set to 0 to disable automatic refresh. The scheduler refreshes stats for all
                repositories, including observe-only ones where backups happen externally.
              </Alert>
            </Stack>
          </CardContent>
        </Card>

        {/* Archive Browsing Limits Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Settings size={24} />
                <Typography variant="h6">Archive Browsing Limits</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                These limits prevent out-of-memory errors when browsing archives with millions of
                files. The borg process is terminated early if limits are exceeded.
              </Typography>
              <Divider />

              <Box
                sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}
              >
                <TextField
                  label="Max Files to Load"
                  type="number"
                  fullWidth
                  value={browseMaxItems}
                  onChange={(e) => setBrowseMaxItems(Number(e.target.value))}
                  inputProps={{ min: MIN_FILES, max: MAX_FILES, step: 100_000 }}
                  error={browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES}
                  helperText={
                    browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES
                      ? `Must be between ${MIN_FILES.toLocaleString()} and ${MAX_FILES.toLocaleString()}`
                      : `Maximum files when browsing. Current: ${(browseMaxItems / 1_000_000).toFixed(1)}M files`
                  }
                />

                <TextField
                  label="Max Memory (MB)"
                  type="number"
                  fullWidth
                  value={browseMaxMemoryMb}
                  onChange={(e) => setBrowseMaxMemoryMb(Number(e.target.value))}
                  inputProps={{ min: MIN_MEMORY, max: MAX_MEMORY, step: 128 }}
                  error={browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY}
                  helperText={
                    browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY
                      ? `Must be between ${MIN_MEMORY} MB and ${MAX_MEMORY} MB`
                      : `Maximum memory for browsing. Current: ${(browseMaxMemoryMb / 1024).toFixed(2)} GB`
                  }
                />
              </Box>

              <Alert severity="warning" icon={<AlertTriangle size={20} />}>
                <strong>Warning:</strong> Increasing these limits significantly can cause
                out-of-memory errors and crash the server. Only increase if you have sufficient RAM
                and need to browse very large archives.
              </Alert>
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  )
}

export default SystemSettingsTab
