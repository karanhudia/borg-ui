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
  LinearProgress,
  Divider,
  CircularProgress,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from '@mui/material'
import { Save, Trash2, AlertTriangle, Server, Zap, Database } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'

interface CacheStats {
  backend: string
  available: boolean
  hits: number
  misses: number
  hit_rate: number
  size_bytes: number
  entry_count: number
  cache_ttl_minutes: number
  cache_max_size_mb: number
  ttl_seconds?: number
  max_size_mb?: number
  connection_type?: string
  connection_info?: string
  redis_url?: string
}

const CacheManagementTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSystem, EventAction } = useAnalytics()

  // Local state for form values
  const [ttlMinutes, setTtlMinutes] = useState(120)
  const [maxSizeMb, setMaxSizeMb] = useState(2048)
  const [redisUrl, setRedisUrl] = useState('')
  const [hasChanges, setHasChanges] = useState(false)
  const [clearDialogOpen, setClearDialogOpen] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)

  // Fetch cache stats (refresh every 10s for real-time monitoring)
  const { data: cacheData, isLoading: loadingCache } = useQuery({
    queryKey: ['cache-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getCacheStats()
      return response.data
    },
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  const stats: CacheStats | undefined = cacheData

  // Initialize form values from fetched settings
  useEffect(() => {
    if (stats) {
      setTtlMinutes(stats.cache_ttl_minutes || 120)
      setMaxSizeMb(stats.cache_max_size_mb || 2048)
      setRedisUrl(stats.redis_url || '')
      setHasChanges(false)
    }
  }, [stats])

  // Track form changes
  useEffect(() => {
    if (stats) {
      const changed =
        ttlMinutes !== (stats.cache_ttl_minutes || 120) ||
        maxSizeMb !== (stats.cache_max_size_mb || 2048) ||
        redisUrl !== (stats.redis_url || '')
      setHasChanges(changed)
    }
  }, [ttlMinutes, maxSizeMb, redisUrl, stats])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateCacheSettings(ttlMinutes, maxSizeMb, redisUrl)
    },
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
      const message = response.data?.message || 'Cache settings saved successfully'
      toast.success(message, { duration: 5000 })
      setHasChanges(false)
      trackSystem(EventAction.EDIT, {
        section: 'cache',
        ttl_minutes: ttlMinutes,
        max_size_mb: maxSizeMb,
        backend: redisUrl ? 'redis' : 'memory',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('cache.failedToSaveCacheSettings')
      )
    },
  })

  // Clear cache mutation
  const clearCacheMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.clearCache()
    },
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
      const clearedCount = response.data?.cleared_count || 0
      toast.success(t('cache.clearSuccess', { count: clearedCount }))
      setClearDialogOpen(false)
      trackSystem(EventAction.DELETE, { section: 'cache', operation: 'clear_cache' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('cache.failedToClearCache')
      )
      setClearDialogOpen(false)
    },
  })

  const handleSaveSettings = () => {
    saveSettingsMutation.mutate()
  }

  const handleClearCache = () => {
    clearCacheMutation.mutate()
  }

  // Test Redis connection
  const handleTestConnection = async () => {
    if (!redisUrl.trim()) {
      toast.error(t('cache.pleaseEnterRedisUrl'))
      return
    }

    setTestingConnection(true)
    try {
      const response = await settingsAPI.updateCacheSettings(
        stats?.cache_ttl_minutes || ttlMinutes,
        stats?.cache_max_size_mb || maxSizeMb,
        redisUrl
      )

      const data = response.data
      if (data.backend === 'redis') {
        toast.success(t('cache.redisConnected', { info: data.connection_info }), { duration: 5000 })
        queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
        setHasChanges(false)
        trackSystem(EventAction.TEST, {
          section: 'cache',
          operation: 'test_connection',
          backend: 'redis',
          success: true,
        })
      } else {
        toast.error(
          t('cache.redisConnectFailed', {
            message: translateBackendKey(data.message) || t('cache.usingInMemoryFallback'),
          }),
          {
            duration: 5000,
          }
        )
        trackSystem(EventAction.TEST, {
          section: 'cache',
          operation: 'test_connection',
          backend: 'redis',
          success: false,
        })
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      const errorMsg =
        translateBackendKey(error.response?.data?.detail) || t('cache.connectionTestFailed')
      toast.error(errorMsg, { duration: 5000 })
      trackSystem(EventAction.TEST, {
        section: 'cache',
        operation: 'test_connection',
        backend: 'redis',
        success: false,
      })
    } finally {
      setTestingConnection(false)
    }
  }

  // Calculate metrics
  const sizeMb = stats ? stats.size_bytes / (1024 * 1024) : 0
  const maxSizeFromStats = stats?.cache_max_size_mb || 2048
  const usagePercent = (sizeMb / maxSizeFromStats) * 100
  const totalRequests = stats ? stats.hits + stats.misses : 0
  const hitRate = stats?.hit_rate || 0

  // Format TTL display
  const formatTtl = (minutes: number) => {
    if (minutes >= 1440) {
      const days = Math.floor(minutes / 1440)
      return `${days} day${days > 1 ? 's' : ''}`
    } else if (minutes >= 60) {
      const hours = Math.floor(minutes / 60)
      return `${hours} hour${hours > 1 ? 's' : ''}`
    } else {
      return `${minutes} minute${minutes > 1 ? 's' : ''}`
    }
  }

  if (loadingCache) {
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
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            gap: 1.5,
            mb: 3,
          }}
        >
          <Box>
            <Typography variant="h6" fontWeight={600}>
              {t('cacheManagement.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('cache.subtitle')}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={
              saveSettingsMutation.isPending ? <CircularProgress size={16} /> : <Save size={16} />
            }
            onClick={handleSaveSettings}
            disabled={!hasChanges || saveSettingsMutation.isPending}
            sx={{ width: { xs: '100%', sm: 'auto' } }}
          >
            {saveSettingsMutation.isPending
              ? t('cacheManagement.saving')
              : t('cacheManagement.save')}
          </Button>
        </Box>

        {/* Cache Status Card */}
        <SettingsCard>
          <Stack spacing={2}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Server size={24} />
                <Typography variant="h6">{t('cache.cacheStatus')}</Typography>
              </Box>
              {stats && (
                <Chip
                  label={stats.backend === 'redis' ? 'Redis' : 'In-Memory'}
                  color={stats.backend === 'redis' ? 'success' : 'warning'}
                  size="small"
                  icon={stats.backend === 'redis' ? <Database size={16} /> : <Zap size={16} />}
                />
              )}
            </Box>

            {/* Connection Info */}
            {stats && stats.connection_info && (
              <Alert severity="info" sx={{ py: 0.5 }}>
                <Typography variant="caption">
                  <strong>Connection:</strong> {stats.connection_info}
                  {stats.connection_type === 'external_url' && ' (External Redis)'}
                  {stats.connection_type === 'local' && ' (Local Docker)'}
                </Typography>
              </Alert>
            )}

            <Divider />

            {/* Status Grid */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr 1fr' },
                gap: 2,
              }}
            >
              <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="h4" color="primary">
                  {stats?.entry_count || 0}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('cache.cachedArchives')}
                </Typography>
              </Box>

              <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="h4" color="primary">
                  {sizeMb.toFixed(1)} MB
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('cache.memoryUsed')}
                </Typography>
              </Box>

              <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="h4" color="primary">
                  {hitRate.toFixed(1)}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('cache.hitRate')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('cache.totalRequests', { count: totalRequests })}
                </Typography>
              </Box>

              <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="h4" color="primary">
                  {stats ? formatTtl(stats.cache_ttl_minutes) : '2 hours'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('cache.cacheTtl')}
                </Typography>
              </Box>
            </Box>

            {/* Usage Progress Bar */}
            <Box>
              <Box
                sx={{
                  display: 'flex',
                  flexDirection: { xs: 'column', sm: 'row' },
                  justifyContent: 'space-between',
                  gap: 0.5,
                  mb: 1,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {t('cache.cacheUsage')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('cache.cacheUsageDetail', {
                    used: sizeMb.toFixed(1),
                    max: maxSizeFromStats,
                    percent: usagePercent.toFixed(1),
                  })}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(usagePercent, 100)}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'action.hover',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: usagePercent >= 80 ? 'error.main' : 'primary.main',
                  },
                }}
              />
            </Box>

            {/* Warning if usage is high */}
            {usagePercent >= 80 && (
              <Alert severity="warning" icon={<AlertTriangle size={20} />}>
                {t('cache.highUsageWarning', { percent: usagePercent.toFixed(1) })}
              </Alert>
            )}

            {/* Backend Info */}
            {stats?.backend === 'in-memory' && (
              <Alert severity="info">{t('cache.inMemoryWarning')}</Alert>
            )}

            {/* Clear Cache Button */}
            <Box>
              <Button
                variant="outlined"
                color="error"
                startIcon={<Trash2 size={20} />}
                onClick={() => setClearDialogOpen(true)}
                disabled={!stats || stats.entry_count === 0 || clearCacheMutation.isPending}
              >
                {t('cache.clearAllCache')}
              </Button>
            </Box>
          </Stack>
        </SettingsCard>

        {/* Configuration Card */}
        <SettingsCard>
          <Stack spacing={3}>
            <Typography variant="h6">{t('cache.cacheConfiguration')}</Typography>
            <Divider />

            <Box
              sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}
            >
              <TextField
                label={t('cache.ttlLabel')}
                type="number"
                fullWidth
                value={ttlMinutes}
                onChange={(e) => setTtlMinutes(Number(e.target.value))}
                inputProps={{ min: 1, max: 10080 }}
                helperText={t('cache.ttlHelperText', { current: formatTtl(ttlMinutes) })}
              />

              <TextField
                label={t('cache.maxSizeLabel')}
                type="number"
                fullWidth
                value={maxSizeMb}
                onChange={(e) => setMaxSizeMb(Number(e.target.value))}
                inputProps={{ min: 100, max: 10240 }}
                helperText={t('cache.maxSizeHelperText', {
                  current: (maxSizeMb / 1024).toFixed(2),
                })}
              />
            </Box>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
              <TextField
                label={t('cache.redisUrlLabel')}
                fullWidth
                value={redisUrl}
                onChange={(e) => setRedisUrl(e.target.value)}
                placeholder="redis://192.168.1.100:6379/0"
                helperText={t('cache.redisUrlHelperText')}
                error={
                  redisUrl.trim() !== '' &&
                  !redisUrl.startsWith('redis://') &&
                  !redisUrl.startsWith('rediss://') &&
                  !redisUrl.startsWith('unix://')
                }
              />
              <Button
                variant="outlined"
                size="small"
                onClick={handleTestConnection}
                disabled={!redisUrl.trim() || testingConnection}
                sx={{ minWidth: 120, mt: 2.5, flexShrink: 0 }}
              >
                {testingConnection ? t('cache.testing') : t('cache.testConnection')}
              </Button>
            </Stack>

            <Alert severity="info">
              <strong>{t('cache.noteLabel')}</strong> {t('cache.ttlNoteText')}
            </Alert>
          </Stack>
        </SettingsCard>
      </Stack>

      {/* Clear Cache Confirmation Dialog */}
      <Dialog open={clearDialogOpen} onClose={() => setClearDialogOpen(false)}>
        <DialogTitle>{t('cache.clearDialogTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('cache.clearConfirmCount', { count: stats?.entry_count || 0 })}
            <br />
            <br />
            {t('cache.clearConfirmQuestion')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearDialogOpen(false)} color="inherit">
            {t('cache.cancel')}
          </Button>
          <Button
            onClick={handleClearCache}
            color="error"
            variant="contained"
            disabled={clearCacheMutation.isPending}
          >
            {clearCacheMutation.isPending
              ? t('cacheManagement.clearing')
              : t('cacheManagement.clearCache')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default CacheManagementTab
