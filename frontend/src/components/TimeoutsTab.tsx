import React, { useState, useEffect } from 'react'
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Stack,
  Divider,
  InputAdornment,
} from '@mui/material'
import { Save, Clock } from 'lucide-react'
import { settingsAPI } from '../services/api'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

interface SystemSettings {
  backup_timeout: number
  max_concurrent_backups: number
  borg_info_timeout: number
  borg_list_timeout: number
  borg_init_timeout: number
  borg_general_timeout: number
}

export const TimeoutsTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState<Partial<SystemSettings>>({
    backup_timeout: 3600,
    borg_info_timeout: 600,
    borg_list_timeout: 300,
    borg_init_timeout: 300,
    borg_general_timeout: 600,
  })
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch current settings
  const { data: settings, isLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  // Update form data when settings load
  useEffect(() => {
    if (settings) {
      setFormData({
        backup_timeout: settings.backup_timeout || 3600,
        borg_info_timeout: settings.borg_info_timeout || 600,
        borg_list_timeout: settings.borg_list_timeout || 300,
        borg_init_timeout: settings.borg_init_timeout || 300,
        borg_general_timeout: settings.borg_general_timeout || 600,
      })
    }
  }, [settings])

  // Update settings mutation
  const updateMutation = useMutation({
    mutationFn: async (data: Partial<SystemSettings>) => {
      return await settingsAPI.updateSystemSettings(data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      setSuccess(true)
      setError(null)
      setTimeout(() => setSuccess(false), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update settings')
      setSuccess(false)
    },
  })

  const handleSubmit = () => {
    // Validate timeouts are positive integers
    if (
      formData.backup_timeout! < 60 ||
      formData.borg_info_timeout! < 60 ||
      formData.borg_list_timeout! < 60 ||
      formData.borg_init_timeout! < 60 ||
      formData.borg_general_timeout! < 60
    ) {
      setError('All timeouts must be at least 60 seconds')
      return
    }

    updateMutation.mutate(formData)
  }

  const formatSeconds = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Clock size={24} />
        Operation Timeouts
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure timeout values for Borg operations. Increase these values if you have large repositories
        or slow network connections. All values are in seconds.
      </Typography>

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(false)}>
          Timeout settings updated successfully
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Stack spacing={3}>
            {/* Backup Timeout */}
            <Box>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Backup Operation Timeout
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Maximum time allowed for a backup operation to complete.
                Current: {formatSeconds(formData.backup_timeout || 3600)}
              </Typography>
              <TextField
                fullWidth
                type="number"
                value={formData.backup_timeout || ''}
                onChange={(e) =>
                  setFormData({ ...formData, backup_timeout: parseInt(e.target.value) || 0 })
                }
                InputProps={{
                  endAdornment: <InputAdornment position="end">seconds</InputAdornment>,
                }}
                helperText="Recommended: 3600 (1 hour) or more for large backups"
              />
            </Box>

            <Divider />

            {/* Borg Info Timeout */}
            <Box>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Repository Info Timeout (borg info)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Timeout for repository verification and info operations.
                Current: {formatSeconds(formData.borg_info_timeout || 600)}
              </Typography>
              <TextField
                fullWidth
                type="number"
                value={formData.borg_info_timeout || ''}
                onChange={(e) =>
                  setFormData({ ...formData, borg_info_timeout: parseInt(e.target.value) || 0 })
                }
                InputProps={{
                  endAdornment: <InputAdornment position="end">seconds</InputAdornment>,
                }}
                helperText="For very large repos (e.g., 166 min cache build), use 10800 (3 hours) or more"
              />
            </Box>

            <Divider />

            {/* Borg List Timeout */}
            <Box>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Archive List Timeout (borg list)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Timeout for listing archives in a repository.
                Current: {formatSeconds(formData.borg_list_timeout || 300)}
              </Typography>
              <TextField
                fullWidth
                type="number"
                value={formData.borg_list_timeout || ''}
                onChange={(e) =>
                  setFormData({ ...formData, borg_list_timeout: parseInt(e.target.value) || 0 })
                }
                InputProps={{
                  endAdornment: <InputAdornment position="end">seconds</InputAdornment>,
                }}
                helperText="Recommended: 300 (5 minutes) for most cases"
              />
            </Box>

            <Divider />

            {/* Borg Init Timeout */}
            <Box>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Repository Init Timeout (borg init)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Timeout for initializing new repositories.
                Current: {formatSeconds(formData.borg_init_timeout || 300)}
              </Typography>
              <TextField
                fullWidth
                type="number"
                value={formData.borg_init_timeout || ''}
                onChange={(e) =>
                  setFormData({ ...formData, borg_init_timeout: parseInt(e.target.value) || 0 })
                }
                InputProps={{
                  endAdornment: <InputAdornment position="end">seconds</InputAdornment>,
                }}
                helperText="Recommended: 300 (5 minutes) for most cases"
              />
            </Box>

            <Divider />

            {/* General Borg Timeout */}
            <Box>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                General Borg Timeout
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Default timeout for other Borg operations (check, compact, prune, etc.).
                Current: {formatSeconds(formData.borg_general_timeout || 600)}
              </Typography>
              <TextField
                fullWidth
                type="number"
                value={formData.borg_general_timeout || ''}
                onChange={(e) =>
                  setFormData({ ...formData, borg_general_timeout: parseInt(e.target.value) || 0 })
                }
                InputProps={{
                  endAdornment: <InputAdornment position="end">seconds</InputAdornment>,
                }}
                helperText="Recommended: 600 (10 minutes) or more"
              />
            </Box>
          </Stack>

          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              startIcon={<Save size={18} />}
              onClick={handleSubmit}
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? 'Saving...' : 'Save Settings'}
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Box>
  )
}

export default TimeoutsTab
