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

  // Validation
  const MIN_FILES = 100_000
  const MAX_FILES = 50_000_000
  const MIN_MEMORY = 100
  const MAX_MEMORY = 16384

  const getValidationError = (): string | null => {
    if (browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES) {
      return `Max files must be between ${MIN_FILES.toLocaleString()} and ${MAX_FILES.toLocaleString()}`
    }
    if (browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY) {
      return `Max memory must be between ${MIN_MEMORY} MB and ${MAX_MEMORY} MB`
    }
    return null
  }

  const validationError = getValidationError()

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
      // Handle Pydantic validation errors (array format) or standard errors
      const data = error.response?.data
      let errorMsg = 'Failed to save settings'
      if (Array.isArray(data)) {
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = data.detail
      }
      toast.error(errorMsg)
    },
  })

  const handleSaveSettings = () => {
    if (validationError) {
      toast.error(validationError)
      return
    }
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
            disabled={!hasChanges || saveSettingsMutation.isPending || !!validationError}
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
