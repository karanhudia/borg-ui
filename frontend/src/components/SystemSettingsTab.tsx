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
import { Save, AlertTriangle, Settings } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

const SystemSettingsTab: React.FC = () => {
  const queryClient = useQueryClient()

  // Local state for form values
  const [browseMaxItems, setBrowseMaxItems] = useState(1_000_000)
  const [browseMaxMemoryMb, setBrowseMaxMemoryMb] = useState(1024)
  const [hasChanges, setHasChanges] = useState(false)

  // Fetch cache stats (which includes browse limits)
  const { data: cacheData, isLoading } = useQuery({
    queryKey: ['cache-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getCacheStats()
      return response.data
    },
  })

  const stats = cacheData as any

  // Initialize form values from fetched settings
  useEffect(() => {
    if (stats) {
      setBrowseMaxItems(stats.browse_max_items || 1_000_000)
      setBrowseMaxMemoryMb(stats.browse_max_memory_mb || 1024)
      setHasChanges(false)
    }
  }, [stats])

  // Track form changes
  useEffect(() => {
    if (stats) {
      const changed =
        browseMaxItems !== (stats.browse_max_items || 1_000_000) ||
        browseMaxMemoryMb !== (stats.browse_max_memory_mb || 1024)
      setHasChanges(changed)
    }
  }, [browseMaxItems, browseMaxMemoryMb, stats])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateCacheSettings(
        stats?.cache_ttl_minutes || 120, // Keep existing TTL
        stats?.cache_max_size_mb || 2048, // Keep existing max size
        (stats as any)?.redis_url || '', // Keep existing Redis URL
        browseMaxItems,
        browseMaxMemoryMb
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
      toast.success('Browse limits saved successfully')
      setHasChanges(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  const handleSaveSettings = () => {
    saveSettingsMutation.mutate()
  }

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
              Configure system-wide settings and resource limits
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
                  label="Max Items to Load"
                  type="number"
                  fullWidth
                  value={browseMaxItems}
                  onChange={(e) => setBrowseMaxItems(Number(e.target.value))}
                  inputProps={{ min: 100_000, max: 50_000_000, step: 100_000 }}
                  helperText={`Maximum number of files to list when browsing. Range: 100k to 50M. Current: ${(browseMaxItems / 1_000_000).toFixed(1)}M files`}
                />

                <TextField
                  label="Max Memory (MB)"
                  type="number"
                  fullWidth
                  value={browseMaxMemoryMb}
                  onChange={(e) => setBrowseMaxMemoryMb(Number(e.target.value))}
                  inputProps={{ min: 100, max: 16384, step: 128 }}
                  helperText={`Maximum memory for archive browsing. Range: 100 MB to 16 GB. Current: ${(browseMaxMemoryMb / 1024).toFixed(2)} GB`}
                />
              </Box>

              <Alert severity="warning" icon={<AlertTriangle size={20} />}>
                <strong>Warning:</strong> Increasing these limits significantly can cause
                out-of-memory errors and crash the server. Only increase if you have sufficient RAM
                and need to browse very large archives.
              </Alert>

              <Alert severity="info">
                <strong>Recommendations based on available RAM:</strong>
                <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
                  <li>1M items ≈ 200MB RAM (default, safe for most systems)</li>
                  <li>5M items ≈ 1GB RAM (requires at least 4GB total RAM)</li>
                  <li>10M items ≈ 2GB RAM (requires at least 8GB total RAM)</li>
                </ul>
                For archives exceeding these limits, use command-line tools or{' '}
                <code>borg mount</code>.
              </Alert>
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  )
}

export default SystemSettingsTab
