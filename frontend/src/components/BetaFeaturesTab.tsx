import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Box, Typography, Stack, Switch, FormControlLabel, CircularProgress } from '@mui/material'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import SettingsCard from './SettingsCard'

const BetaFeaturesTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSettings, EventAction } = useAnalytics()
  const [bypassLockOnInfo, setBypassLockOnInfo] = useState(false)
  const [bypassLockOnList, setBypassLockOnList] = useState(false)
  const [showRestoreTab, setShowRestoreTab] = useState(false)
  const [borg2FastBrowseBetaEnabled, setBorg2FastBrowseBetaEnabled] = useState(false)
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
      setBorg2FastBrowseBetaEnabled(systemSettings.borg2_fast_browse_beta_enabled ?? false)
      setMqttBetaEnabled(systemSettings.mqtt_beta_enabled ?? false)
    }
  }, [systemSettings])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async (settings: {
      bypass_lock_on_info?: boolean
      bypass_lock_on_list?: boolean
      show_restore_tab?: boolean
      borg2_fast_browse_beta_enabled?: boolean
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
        setBorg2FastBrowseBetaEnabled(systemSettings.borg2_fast_browse_beta_enabled ?? false)
        setMqttBetaEnabled(systemSettings.mqtt_beta_enabled ?? false)
      }
    },
  })

  const handleToggle = (checked: boolean) => {
    setBypassLockOnInfo(checked)
    trackSettings(EventAction.EDIT, {
      section: 'beta_features',
      feature: 'bypass_lock_on_info',
      enabled: checked,
    })
    saveSettingsMutation.mutate({ bypass_lock_on_info: checked })
  }

  const handleListToggle = (checked: boolean) => {
    setBypassLockOnList(checked)
    trackSettings(EventAction.EDIT, {
      section: 'beta_features',
      feature: 'bypass_lock_on_list',
      enabled: checked,
    })
    saveSettingsMutation.mutate({ bypass_lock_on_list: checked })
  }

  const handleRestoreTabToggle = (checked: boolean) => {
    setShowRestoreTab(checked)
    trackSettings(EventAction.EDIT, {
      section: 'beta_features',
      feature: 'show_restore_tab',
      enabled: checked,
    })
    saveSettingsMutation.mutate({ show_restore_tab: checked })
  }

  const handleBorg2FastBrowseToggle = (checked: boolean) => {
    setBorg2FastBrowseBetaEnabled(checked)
    trackSettings(EventAction.EDIT, {
      section: 'beta_features',
      feature: 'borg2_fast_browse_beta_enabled',
      enabled: checked,
    })
    saveSettingsMutation.mutate({ borg2_fast_browse_beta_enabled: checked })
  }

  const handleMQTTBetaToggle = (checked: boolean) => {
    setMqttBetaEnabled(checked)
    trackSettings(EventAction.EDIT, {
      section: 'beta_features',
      feature: 'mqtt_beta_enabled',
      enabled: checked,
    })
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

      <SettingsCard sx={{ maxWidth: 800 }}>
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
                  <Typography variant="body1">{t('betaFeatures.enableBypassLocksInfo')}</Typography>
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
                  <Typography variant="body1">{t('betaFeatures.enableBypassLocksList')}</Typography>
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
              {t('betaFeatures.borg2FastBrowseTitle')}
            </Typography>

            <FormControlLabel
              control={
                <Switch
                  checked={borg2FastBrowseBetaEnabled}
                  onChange={(e) => handleBorg2FastBrowseToggle(e.target.checked)}
                  disabled={saveSettingsMutation.isPending}
                  color="primary"
                />
              }
              label={
                <Box>
                  <Typography variant="body1">{t('betaFeatures.enableBorg2FastBrowse')}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t('betaFeatures.borg2FastBrowseDescription')}
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
      </SettingsCard>
    </Box>
  )
}

export default BetaFeaturesTab
