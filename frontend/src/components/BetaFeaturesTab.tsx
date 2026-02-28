import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Stack,
  Switch,
  FormControlLabel,
  CircularProgress,
} from '@mui/material'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

const BetaFeaturesTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [bypassLockOnInfo, setBypassLockOnInfo] = useState(false)
  const [bypassLockOnList, setBypassLockOnList] = useState(false)
  const [showRestoreTab, setShowRestoreTab] = useState(false)
  const [mqttBetaEnabled, setMqttBetaEnabled] = useState(false)

  // Fetch system settings
  const { data: systemData, isLoading: systemLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  const systemSettings = systemData?.settings

  // Initialize state from fetched data
  useEffect(() => {
    if (systemSettings) {
      setBypassLockOnInfo(systemSettings.bypass_lock_on_info ?? false)
      setBypassLockOnList(systemSettings.bypass_lock_on_list ?? false)
      setShowRestoreTab(systemSettings.show_restore_tab ?? false)
      setMqttBetaEnabled(systemSettings.mqtt_beta_enabled ?? false)
    }
  }, [systemSettings])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async (settings: {
      bypass_lock_on_info?: boolean
      bypass_lock_on_list?: boolean
      show_restore_tab?: boolean
      mqtt_beta_enabled?: boolean
    }) => {
      await settingsAPI.updateSystemSettings(settings)
    },
    onSuccess: () => {
      toast.success('Setting updated successfully')
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    onError: (error: Error) => {
      toast.error(`Failed to update setting: ${error.message}`)
      // Revert on error
      if (systemSettings) {
        setBypassLockOnInfo(systemSettings.bypass_lock_on_info ?? false)
        setBypassLockOnList(systemSettings.bypass_lock_on_list ?? false)
        setShowRestoreTab(systemSettings.show_restore_tab ?? false)
        setMqttBetaEnabled(systemSettings.mqtt_beta_enabled ?? false)
      }
    },
  })

  const handleToggle = (checked: boolean) => {
    setBypassLockOnInfo(checked)
    saveSettingsMutation.mutate({ bypass_lock_on_info: checked })
  }

  const handleListToggle = (checked: boolean) => {
    setBypassLockOnList(checked)
    saveSettingsMutation.mutate({ bypass_lock_on_list: checked })
  }

  const handleRestoreTabToggle = (checked: boolean) => {
    setShowRestoreTab(checked)
    saveSettingsMutation.mutate({ show_restore_tab: checked })
  }

  const handleMQTTBetaToggle = (checked: boolean) => {
    setMqttBetaEnabled(checked)
    saveSettingsMutation.mutate({ mqtt_beta_enabled: checked })
  }

  if (systemLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          Beta Features
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Try experimental features before they're released to everyone. These features are still in
          development and may change.
        </Typography>
      </Box>

      <Card sx={{ maxWidth: 800 }}>
        <CardContent>
          <Stack spacing={3}>
            {/* Bypass Lock on Info Commands */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                Bypass Locks for Info Commands
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={bypassLockOnInfo}
                    onChange={(e) => handleToggle(e.target.checked)}
                    disabled={saveSettingsMutation.isPending}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1">
                      Enable bypass-lock for all borg info commands
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Adds <code>--bypass-lock</code> to all <code>borg info</code> commands. This
                      prevents lock contention when multiple operations try to access SSH
                      repositories simultaneously. Enable if you see "Repository is locked" errors.
                    </Typography>
                  </Box>
                }
              />
            </Box>

            {/* Bypass Lock on List Commands */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                Bypass Locks for List Commands
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={bypassLockOnList}
                    onChange={(e) => handleListToggle(e.target.checked)}
                    disabled={saveSettingsMutation.isPending}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1">
                      Enable bypass-lock for all borg list commands
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Adds <code>--bypass-lock</code> to all <code>borg list</code> commands. This
                      prevents lock contention when multiple read operations (like info + list) run
                      simultaneously. Enable if you see "Failed to acquire lock" errors. Note: May
                      show stale data if a backup is actively running.
                    </Typography>
                  </Box>
                }
              />
            </Box>

            {/* Show Restore Tab */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                Show Legacy Restore Tab
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={showRestoreTab}
                    onChange={(e) => handleRestoreTabToggle(e.target.checked)}
                    disabled={saveSettingsMutation.isPending}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1">
                      Show the dedicated Restore tab in navigation
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Enable this to access the legacy Restore tab. Restore functionality is now
                      integrated into the Archives page, but this option allows you to use the old
                      interface if preferred.
                    </Typography>
                  </Box>
                }
              />
            </Box>

            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                MQTT Integration
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={mqttBetaEnabled}
                    onChange={(e) => handleMQTTBetaToggle(e.target.checked)}
                    disabled={saveSettingsMutation.isPending}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1">Enable MQTT</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Activates MQTT integration in the UI.
                    </Typography>
                  </Box>
                }
              />
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}

export default BetaFeaturesTab
