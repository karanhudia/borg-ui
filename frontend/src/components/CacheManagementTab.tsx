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
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

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
}

const CacheManagementTab: React.FC = () => {
  const queryClient = useQueryClient()

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
      setRedisUrl((stats as any).redis_url || '')
      setHasChanges(false)
    }
  }, [stats])

  // Track form changes
  useEffect(() => {
    if (stats) {
      const changed =
        ttlMinutes !== (stats.cache_ttl_minutes || 120) ||
        maxSizeMb !== (stats.cache_max_size_mb || 2048) ||
        redisUrl !== ((stats as any).redis_url || '')
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
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save cache settings')
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
      toast.success(`Cache cleared successfully (${clearedCount} entries removed)`)
      setClearDialogOpen(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to clear cache')
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
      toast.error('Please enter a Redis URL first')
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
        toast.success(`✓ Connected to Redis: ${data.connection_info}`, { duration: 5000 })
        queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
        setHasChanges(false)
      } else {
        toast.error(`Failed to connect: ${data.message || 'Using in-memory fallback'}`, {
          duration: 5000,
        })
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || 'Connection test failed'
      toast.error(errorMsg, { duration: 5000 })
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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Archive Cache Management
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Monitor and configure the Redis-based archive caching system for faster browsing
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={
              saveSettingsMutation.isPending ? <CircularProgress size={16} /> : <Save size={16} />
            }
            onClick={handleSaveSettings}
            disabled={!hasChanges || saveSettingsMutation.isPending}
          >
            {saveSettingsMutation.isPending ? 'Saving...' : 'Save Settings'}
          </Button>
        </Box>

        {/* Cache Status Card */}
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Server size={24} />
                  <Typography variant="h6">Cache Status</Typography>
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
                    Cached Archives
                  </Typography>
                </Box>

                <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                  <Typography variant="h4" color="primary">
                    {sizeMb.toFixed(1)} MB
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Memory Used
                  </Typography>
                </Box>

                <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                  <Typography variant="h4" color="primary">
                    {hitRate.toFixed(1)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Hit Rate
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {totalRequests} total requests
                  </Typography>
                </Box>

                <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                  <Typography variant="h4" color="primary">
                    {stats ? formatTtl(stats.cache_ttl_minutes) : '2 hours'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Cache TTL
                  </Typography>
                </Box>
              </Box>

              {/* Usage Progress Bar */}
              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    Cache Usage
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {sizeMb.toFixed(1)} MB / {maxSizeFromStats} MB ({usagePercent.toFixed(1)}%)
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
                  Cache usage is at {usagePercent.toFixed(1)}%. Consider increasing the max size
                  limit or clearing old entries.
                </Alert>
              )}

              {/* Backend Info */}
              {stats?.backend === 'in-memory' && (
                <Alert severity="info">
                  Currently using in-memory cache. Redis is unavailable or not configured. In-memory
                  cache is limited and will be lost on restart.
                </Alert>
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
                  Clear All Cache
                </Button>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Configuration Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Typography variant="h6">Cache Configuration</Typography>
              <Divider />

              <Box
                sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}
              >
                <TextField
                  label="Cache TTL (minutes)"
                  type="number"
                  fullWidth
                  value={ttlMinutes}
                  onChange={(e) => setTtlMinutes(Number(e.target.value))}
                  inputProps={{ min: 1, max: 10080 }}
                  helperText={`Time before cached entries expire. Range: 1 minute to 7 days. Current: ${formatTtl(ttlMinutes)}`}
                />

                <TextField
                  label="Max Cache Size (MB)"
                  type="number"
                  fullWidth
                  value={maxSizeMb}
                  onChange={(e) => setMaxSizeMb(Number(e.target.value))}
                  inputProps={{ min: 100, max: 10240 }}
                  helperText={`Maximum cache size. Range: 100 MB to 10 GB. Current: ${(maxSizeMb / 1024).toFixed(2)} GB`}
                />
              </Box>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                <TextField
                  label="External Redis URL (Optional)"
                  fullWidth
                  value={redisUrl}
                  onChange={(e) => setRedisUrl(e.target.value)}
                  placeholder="redis://192.168.1.100:6379/0"
                  helperText="Format: redis://[password@]host:port/db, rediss:// for TLS, or unix:// for Unix sockets"
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
                  {testingConnection ? 'Testing...' : 'Test Connection'}
                </Button>
              </Stack>

              <Alert severity="info">
                <strong>Note:</strong> TTL changes only affect new cache entries. Existing entries
                keep their original TTL until they expire.
              </Alert>
            </Stack>
          </CardContent>
        </Card>
      </Stack>

      {/* Clear Cache Confirmation Dialog */}
      <Dialog open={clearDialogOpen} onClose={() => setClearDialogOpen(false)}>
        <DialogTitle>Clear All Cache?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will remove all {stats?.entry_count || 0} cached archive entries. The next time you
            browse an archive, it will need to rebuild the cache (60-90 seconds for large archives).
            <br />
            <br />
            Are you sure you want to continue?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearDialogOpen(false)} color="inherit">
            Cancel
          </Button>
          <Button
            onClick={handleClearCache}
            color="error"
            variant="contained"
            disabled={clearCacheMutation.isPending}
          >
            {clearCacheMutation.isPending ? 'Clearing...' : 'Clear Cache'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default CacheManagementTab
