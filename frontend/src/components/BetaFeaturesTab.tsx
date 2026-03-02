import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
      toast.success(t('betaFeatures.settingUpdatedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
    },
    onError: (error: Error) => {
      toast.error(t('betaFeatures.failedToUpdateSetting', { message: error.message }))
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
          {t('betaFeatures.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('betaFeatures.description')}
        </Typography>
      </Box>

      <Card sx={{ maxWidth: 800 }}>
        <CardContent>
          <Stack spacing={3}>
            {/* Bypass Lock on Info Commands */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                {t('betaFeatures.bypassLocksInfoTitle')}
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
                      {t('betaFeatures.enableBypassLocksInfo')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('betaFeatures.bypassLocksInfoDescription')}
                    </Typography>
                  </Box>
                }
              />
            </Box>

            {/* Bypass Lock on List Commands */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                {t('betaFeatures.bypassLocksListTitle')}
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
                      {t('betaFeatures.enableBypassLocksList')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('betaFeatures.bypassLocksListDescription')}
                    </Typography>
                  </Box>
                }
              />
            </Box>

            {/* Show Restore Tab */}
            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                {t('betaFeatures.showLegacyRestoreTabTitle')}
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
                      {t('betaFeatures.showLegacyRestoreTabLabel')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('betaFeatures.showLegacyRestoreTabDescription')}
                    </Typography>
                  </Box>
                }
              />
            </Box>

            <Box>
              <Typography variant="h6" fontSize="1rem" sx={{ mb: 2 }}>
                {t('betaFeatures.mqttIntegrationTitle')}
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
                    <Typography variant="body1">{t('betaFeatures.enableMqtt')}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('betaFeatures.mqttIntegrationDescription')}
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
