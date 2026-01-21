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
import { Save, AlertTriangle, Settings, Clock } from 'lucide-react'
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

  const [hasChanges, setHasChanges] = useState(false)

  // Fetch cache stats (which includes browse limits)
  const { data: cacheData, isLoading: cacheLoading } = useQuery({
    queryKey: ['cache-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getCacheStats()
      return response.data
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

  const cacheStats = cacheData as any
  const systemSettings = systemData?.settings
  const timeoutSources = systemData?.settings?.timeout_sources as Record<string, string | null> | undefined

  // Helper to render source label with color
  const renderSourceLabel = (source: string | null | undefined) => {
    if (source === 'saved') {
      return (
        <Typography component="span" sx={{ color: 'success.main', fontSize: '0.7rem', fontWeight: 500 }}>
          {' '}[customized]
        </Typography>
      )
    }
    if (source === 'env') {
      return (
        <Typography component="span" sx={{ color: 'warning.main', fontSize: '0.7rem', fontWeight: 500 }}>
          {' '}[from env]
        </Typography>
      )
    }
    return (
      <Typography component="span" sx={{ color: 'info.main', fontSize: '0.7rem', fontWeight: 500 }}>
        {' '}[default]
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
        backupTimeout !== (systemSettings.backup_timeout || 3600)

      setHasChanges(browseChanged || timeoutChanged)
    }
  }, [
    browseMaxItems,
    browseMaxMemoryMb,
    mountTimeout,
    infoTimeout,
    listTimeout,
    initTimeout,
    backupTimeout,
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

  const getValidationError = (): string | null => {
    if (browseMaxItems < MIN_FILES || browseMaxItems > MAX_FILES) {
      return `Max files must be between ${MIN_FILES.toLocaleString()} and ${MAX_FILES.toLocaleString()}`
    }
    if (browseMaxMemoryMb < MIN_MEMORY || browseMaxMemoryMb > MAX_MEMORY) {
      return `Max memory must be between ${MIN_MEMORY} MB and ${MAX_MEMORY} MB`
    }
    const timeouts = [mountTimeout, infoTimeout, listTimeout, initTimeout, backupTimeout]
    if (timeouts.some((t) => t < MIN_TIMEOUT || t > MAX_TIMEOUT)) {
      return `Timeouts must be between ${MIN_TIMEOUT} seconds and ${MAX_TIMEOUT} seconds (24 hours)`
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
        (cacheStats as any)?.redis_url || '',
        browseMaxItems,
        browseMaxMemoryMb
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache-stats'] })
    },
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = 'Failed to save browse limits'
      if (Array.isArray(data)) {
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = data.detail
      }
      throw new Error(errorMsg)
    },
  })

  // Save timeouts mutation
  const saveTimeoutsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateSystemSettings({
        mount_timeout: mountTimeout,
        info_timeout: infoTimeout,
        list_timeout: listTimeout,
        init_timeout: initTimeout,
        backup_timeout: backupTimeout,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = 'Failed to save timeout settings'
      if (Array.isArray(data)) {
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
                  helperText={<>For mounting archives. {formatTimeout(mountTimeout)}{renderSourceLabel(timeoutSources?.mount_timeout)}</>}
                />

                <TextField
                  label="Info Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={infoTimeout}
                  onChange={(e) => setInfoTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={infoTimeout < MIN_TIMEOUT || infoTimeout > MAX_TIMEOUT}
                  helperText={<>For borg info commands. {formatTimeout(infoTimeout)}{renderSourceLabel(timeoutSources?.info_timeout)}</>}
                />

                <TextField
                  label="List Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={listTimeout}
                  onChange={(e) => setListTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={listTimeout < MIN_TIMEOUT || listTimeout > MAX_TIMEOUT}
                  helperText={<>For listing archives. {formatTimeout(listTimeout)}{renderSourceLabel(timeoutSources?.list_timeout)}</>}
                />

                <TextField
                  label="Init Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={initTimeout}
                  onChange={(e) => setInitTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 60 }}
                  error={initTimeout < MIN_TIMEOUT || initTimeout > MAX_TIMEOUT}
                  helperText={<>For repository init. {formatTimeout(initTimeout)}{renderSourceLabel(timeoutSources?.init_timeout)}</>}
                />

                <TextField
                  label="Backup/Restore Timeout (seconds)"
                  type="number"
                  fullWidth
                  value={backupTimeout}
                  onChange={(e) => setBackupTimeout(Number(e.target.value))}
                  inputProps={{ min: MIN_TIMEOUT, max: MAX_TIMEOUT, step: 300 }}
                  error={backupTimeout < MIN_TIMEOUT || backupTimeout > MAX_TIMEOUT}
                  helperText={<>For backup/restore. {formatTimeout(backupTimeout)}{renderSourceLabel(timeoutSources?.backup_timeout)}</>}
                />
              </Box>
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
