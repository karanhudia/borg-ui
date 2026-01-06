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
  const [hasChanges, setHasChanges] = useState(false)
  const [clearDialogOpen, setClearDialogOpen] = useState(false)

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
      setHasChanges(false)
    }
  }, [stats])

  // Track form changes
  useEffect(() => {
    if (stats) {
      const changed =
        ttlMinutes !== (stats.cache_ttl_minutes || 120) ||
        maxSizeMb !== (stats.cache_max_size_mb || 2048)
      setHasChanges(changed)
    }
  }, [ttlMinutes, maxSizeMb, stats])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateCacheSettings(ttlMinutes, maxSizeMb)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
      toast.success('Cache settings saved successfully')
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
    <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
      <Stack spacing={3}>
        {/* Header */}
        <Box>
          <Typography variant="h5" gutterBottom>
            Archive Cache Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Monitor and configure the Redis-based archive caching system for faster browsing
          </Typography>
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
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr 1fr' }, gap: 2 }}>
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
                  Cache usage is at {usagePercent.toFixed(1)}%. Consider increasing the max size limit or
                  clearing old entries.
                </Alert>
              )}

              {/* Backend Info */}
              {stats?.backend === 'in-memory' && (
                <Alert severity="info">
                  Currently using in-memory cache. Redis is unavailable or not configured. In-memory cache is
                  limited and will be lost on restart.
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

              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}>
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

              <Alert severity="info">
                <strong>Note:</strong> TTL changes only affect new cache entries. Existing entries keep their
                original TTL until they expire.
              </Alert>

              <Box>
                <Button
                  variant="contained"
                  startIcon={<Save size={20} />}
                  onClick={handleSaveSettings}
                  disabled={!hasChanges || saveSettingsMutation.isPending}
                >
                  {saveSettingsMutation.isPending ? 'Saving...' : 'Save Settings'}
                </Button>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Info Card */}
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6">About Archive Caching</Typography>
              <Divider />

              <Typography variant="body2" color="text.secondary">
                Archive caching significantly improves browsing performance for large repositories by storing
                parsed archive contents in memory.
              </Typography>

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Performance Impact:
                </Typography>
                <Typography variant="body2" color="text.secondary" component="div">
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    <li>
                      <strong>Without cache:</strong> 60-90 seconds per folder navigation (runs borg list every
                      time)
                    </li>
                    <li>
                      <strong>With cache:</strong> &lt;100ms per navigation (600x faster!)
                    </li>
                    <li>
                      <strong>First load:</strong> Same as without cache (builds cache for future use)
                    </li>
                  </ul>
                </Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Backend Types:
                </Typography>
                <Typography variant="body2" color="text.secondary" component="div">
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    <li>
                      <strong>External Redis (URL):</strong> Connect to Redis on separate machine with more RAM
                      (configure via REDIS_URL env variable)
                    </li>
                    <li>
                      <strong>Local Redis (Docker):</strong> Redis container in docker-compose, persistent across
                      app restarts
                    </li>
                    <li>
                      <strong>In-Memory:</strong> Fallback mode when Redis unavailable, lost on app restart
                    </li>
                  </ul>
                </Typography>
              </Box>

              <Alert severity="success">
                <strong>Tip:</strong> For repositories with millions of files, caching can reduce browsing time
                from 10-15 minutes to under a minute!
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
            This will remove all {stats?.entry_count || 0} cached archive entries. The next time you browse an
            archive, it will need to rebuild the cache (60-90 seconds for large archives).
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
