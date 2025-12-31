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
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  TextField,
  Slider,
  Checkbox,
  LinearProgress,
  Divider,
  CircularProgress,
} from '@mui/material'
import { Save, Trash2, AlertTriangle, HardDrive } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

interface LogStorage {
  total_size_mb: number
  file_count: number
  oldest_log_date: string | null
  newest_log_date: string | null
  usage_percent: number
  files_by_type: Record<string, number>
  limit_mb: number
  retention_days: number
}

interface SystemSettings {
  log_retention_days: number
  log_save_policy: string
  log_max_total_size_mb: number
  log_cleanup_on_startup: boolean
}

const LogManagementTab: React.FC = () => {
  const queryClient = useQueryClient()

  // Local state for form values
  const [logSavePolicy, setLogSavePolicy] = useState('failed_and_warnings')
  const [retentionDays, setRetentionDays] = useState(30)
  const [maxTotalSizeMb, setMaxTotalSizeMb] = useState(500)
  const [cleanupOnStartup, setCleanupOnStartup] = useState(true)
  const [hasChanges, setHasChanges] = useState(false)

  // Fetch system settings
  const { data: settingsData, isLoading: loadingSettings } = useQuery({
    queryKey: ['system-settings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  // Fetch log storage stats (refresh every 30s)
  const { data: logStorageData, isLoading: loadingStorage } = useQuery({
    queryKey: ['log-storage-stats'],
    queryFn: async () => {
      const response = await settingsAPI.getLogStorageStats()
      return response.data
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const logStorage: LogStorage | undefined = logStorageData?.storage || settingsData?.log_storage
  const settings: SystemSettings | undefined = settingsData?.settings

  // Initialize form values from fetched settings
  useEffect(() => {
    if (settings) {
      setLogSavePolicy(settings.log_save_policy || 'failed_and_warnings')
      setRetentionDays(settings.log_retention_days || 30)
      setMaxTotalSizeMb(settings.log_max_total_size_mb || 500)
      setCleanupOnStartup(settings.log_cleanup_on_startup ?? true)
      setHasChanges(false)
    }
  }, [settings])

  // Track form changes
  useEffect(() => {
    if (settings) {
      const changed =
        logSavePolicy !== (settings.log_save_policy || 'failed_and_warnings') ||
        retentionDays !== (settings.log_retention_days || 30) ||
        maxTotalSizeMb !== (settings.log_max_total_size_mb || 500) ||
        cleanupOnStartup !== (settings.log_cleanup_on_startup ?? true)
      setHasChanges(changed)
    }
  }, [logSavePolicy, retentionDays, maxTotalSizeMb, cleanupOnStartup, settings])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      const response = await settingsAPI.updateSystemSettings({
        log_save_policy: logSavePolicy,
        log_retention_days: retentionDays,
        log_max_total_size_mb: maxTotalSizeMb,
        log_cleanup_on_startup: cleanupOnStartup,
      })
      return response.data
    },
    onSuccess: (data) => {
      toast.success('Log management settings saved successfully')
      if (data.warnings && data.warnings.length > 0) {
        data.warnings.forEach((warning: string) => {
          toast.error(warning, { duration: 6000 })
        })
      }
      queryClient.invalidateQueries({ queryKey: ['system-settings'] })
      queryClient.invalidateQueries({ queryKey: ['log-storage-stats'] })
      setHasChanges(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  // Manual cleanup mutation
  const cleanupMutation = useMutation({
    mutationFn: async () => {
      const response = await settingsAPI.manualLogCleanup()
      return response.data
    },
    onSuccess: (data) => {
      toast.success(data.message || 'Log cleanup completed successfully')
      queryClient.invalidateQueries({ queryKey: ['log-storage-stats'] })
      queryClient.invalidateQueries({ queryKey: ['system-settings'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run log cleanup')
    },
  })

  const handleSaveSettings = () => {
    saveSettingsMutation.mutate()
  }

  const handleCleanup = () => {
    if (
      window.confirm(
        'Are you sure you want to run log cleanup? This will delete old log files according to your settings.'
      )
    ) {
      cleanupMutation.mutate()
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  if (loadingSettings) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    )
  }

  const usagePercent = logStorage?.usage_percent || 0
  const isHighUsage = usagePercent >= 80

  return (
    <Box>
      {/* Header Section */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>
            Log Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Configure log storage, retention, and cleanup policies for job logs
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={saveSettingsMutation.isPending ? <CircularProgress size={16} /> : <Save size={16} />}
          onClick={handleSaveSettings}
          disabled={!hasChanges || saveSettingsMutation.isPending}
        >
          {saveSettingsMutation.isPending ? 'Saving...' : 'Save Settings'}
        </Button>
      </Box>

      <Stack spacing={3}>
        {/* Current Usage Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <HardDrive size={20} />
                  <Typography variant="subtitle1" fontWeight={600}>
                    Storage Usage
                  </Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Current log storage utilization and statistics
                </Typography>
              </Box>

              <Divider />

              {loadingStorage ? (
                <Box py={2}>
                  <LinearProgress />
                </Box>
              ) : (
                <>
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(4, 1fr)' },
                      gap: 3,
                    }}
                  >
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 600 }}>
                        Total Size
                      </Typography>
                      <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                        {logStorage?.total_size_mb || 0} MB
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 600 }}>
                        File Count
                      </Typography>
                      <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                        {logStorage?.file_count || 0}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 600 }}>
                        Oldest Log
                      </Typography>
                      <Typography variant="body1" sx={{ mt: 0.5 }}>
                        {formatDate(logStorage?.oldest_log_date || null)}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 600 }}>
                        Newest Log
                      </Typography>
                      <Typography variant="body1" sx={{ mt: 0.5 }}>
                        {formatDate(logStorage?.newest_log_date || null)}
                      </Typography>
                    </Box>
                  </Box>

                  <Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" fontWeight={600}>
                        {usagePercent}% of {logStorage?.limit_mb || 0} MB
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {Math.max(0, (logStorage?.limit_mb || 0) - (logStorage?.total_size_mb || 0))} MB available
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={Math.min(usagePercent, 100)}
                      color={isHighUsage ? 'warning' : 'primary'}
                      sx={{ height: 8, borderRadius: 4 }}
                    />
                  </Box>

                  {isHighUsage && (
                    <Alert severity="warning" icon={<AlertTriangle size={20} />}>
                      Log storage usage is at {usagePercent}%. Consider running cleanup or increasing the
                      size limit.
                    </Alert>
                  )}

                  <Box sx={{ pt: 1 }}>
                    <Button
                      variant="outlined"
                      color="error"
                      startIcon={cleanupMutation.isPending ? <CircularProgress size={16} /> : <Trash2 size={16} />}
                      onClick={handleCleanup}
                      disabled={cleanupMutation.isPending}
                    >
                      {cleanupMutation.isPending ? 'Running Cleanup...' : 'Run Cleanup Now'}
                    </Button>
                  </Box>
                </>
              )}
            </Stack>
          </CardContent>
        </Card>

        {/* Log Storage Policy */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                  Log Storage Policy
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Choose which job types should have their logs saved to disk
                </Typography>
              </Box>

              <Divider />

              <FormControl component="fieldset">
                <RadioGroup value={logSavePolicy} onChange={(e) => setLogSavePolicy(e.target.value)}>
                  <FormControlLabel
                    value="failed_only"
                    control={<Radio />}
                    label={
                      <Box sx={{ py: 1 }}>
                        <Typography variant="body1" fontWeight={500}>
                          Failed Jobs Only
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Save logs only for failed or cancelled jobs (minimal disk usage)
                        </Typography>
                      </Box>
                    }
                    sx={{ mb: 1, alignItems: 'flex-start', '.MuiRadio-root': { mt: 1.25 } }}
                  />
                  <FormControlLabel
                    value="failed_and_warnings"
                    control={<Radio />}
                    label={
                      <Box sx={{ py: 1 }}>
                        <Typography variant="body1" fontWeight={500}>
                          Failed Jobs and Warnings (Recommended)
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Save logs for failed jobs and any job with warnings or errors
                        </Typography>
                      </Box>
                    }
                    sx={{ mb: 1, alignItems: 'flex-start', '.MuiRadio-root': { mt: 1.25 } }}
                  />
                  <FormControlLabel
                    value="all_jobs"
                    control={<Radio />}
                    label={
                      <Box sx={{ py: 1 }}>
                        <Typography variant="body1" fontWeight={500}>
                          All Jobs
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Save logs for all jobs, including successful ones (maximum disk usage)
                        </Typography>
                      </Box>
                    }
                    sx={{ alignItems: 'flex-start', '.MuiRadio-root': { mt: 1.25 } }}
                  />
                </RadioGroup>
              </FormControl>
            </Stack>
          </CardContent>
        </Card>

        {/* Retention Settings */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                  Retention Settings
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Configure how long logs are kept and maximum storage size
                </Typography>
              </Box>

              <Divider />

              <Box>
                <Typography variant="body2" fontWeight={600} gutterBottom>
                  Log Retention Period: {retentionDays} days
                </Typography>
                <Box sx={{ px: 1, pt: 1 }}>
                  <Slider
                    value={retentionDays}
                    onChange={(_, value) => setRetentionDays(value as number)}
                    min={7}
                    max={90}
                    step={1}
                    marks={[
                      { value: 7, label: '7d' },
                      { value: 30, label: '30d' },
                      { value: 60, label: '60d' },
                      { value: 90, label: '90d' },
                    ]}
                    valueLabelDisplay="auto"
                  />
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Logs older than this will be automatically deleted during cleanup
                </Typography>
              </Box>

              <Box>
                <TextField
                  label="Maximum Total Size (MB)"
                  type="number"
                  value={maxTotalSizeMb}
                  onChange={(e) => setMaxTotalSizeMb(Math.max(10, parseInt(e.target.value) || 10))}
                  inputProps={{ min: 10, max: 10000, step: 50 }}
                  fullWidth
                  helperText="Total size limit for all log files. Min: 10 MB, Max: 10,000 MB (10 GB)"
                />
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Cleanup Options */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                  Automatic Cleanup
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Configure when log cleanup runs automatically
                </Typography>
              </Box>

              <Divider />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={cleanupOnStartup}
                    onChange={(e) => setCleanupOnStartup(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" fontWeight={500}>
                      Run cleanup on application startup
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Automatically clean old logs when the application starts
                    </Typography>
                  </Box>
                }
              />
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  )
}

export default LogManagementTab
