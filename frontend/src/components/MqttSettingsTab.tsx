import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  Stack,
  TextField,
  Divider,
  CircularProgress,
  Alert,
  FormControlLabel,
  Checkbox,
  InputAdornment,
  IconButton,
} from '@mui/material'
import { Save, Wifi, Lock, Key, Shield, AlertTriangle, Eye, EyeOff } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'

const MqttSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackSystem, EventAction } = useAnalytics()

  // MQTT form state
  const [mqttEnabled, setMqttEnabled] = useState(false)
  const [mqttBrokerUrl, setMqttBrokerUrl] = useState('')
  const [mqttBrokerPort, setMqttBrokerPort] = useState(1883)
  const [mqttUsername, setMqttUsername] = useState('')
  const [mqttPassword, setMqttPassword] = useState('')
  const [mqttClientId, setMqttClientId] = useState('borg-ui')
  const [mqttQos, setMqttQos] = useState(1)
  const [mqttRetain, setMqttRetain] = useState(false)
  const [mqttTlsEnabled, setMqttTlsEnabled] = useState(false)
  const [mqttTlsCaCert, setMqttTlsCaCert] = useState('')
  const [mqttTlsClientCert, setMqttTlsClientCert] = useState('')
  const [mqttTlsClientKey, setMqttTlsClientKey] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)

  // Fetch system settings
  const { data: systemData, isLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  const systemSettings = systemData?.settings

  // Initialize form values from fetched settings
  useEffect(() => {
    if (systemSettings) {
      setMqttEnabled(systemSettings.mqtt_enabled || false)
      setMqttBrokerUrl(systemSettings.mqtt_broker_url || '')
      setMqttBrokerPort(systemSettings.mqtt_broker_port || 1883)
      setMqttUsername(systemSettings.mqtt_username || '')
      setMqttClientId(systemSettings.mqtt_client_id || 'borg-ui')
      setMqttQos(systemSettings.mqtt_qos || 1)
      setMqttRetain(systemSettings.mqtt_retain || false)
      setMqttTlsEnabled(systemSettings.mqtt_tls_enabled || false)
      setMqttTlsCaCert(systemSettings.mqtt_tls_ca_cert || '')
      setMqttTlsClientCert(systemSettings.mqtt_tls_client_cert || '')
      setMqttTlsClientKey(systemSettings.mqtt_tls_client_key || '')
      setPasswordChanged(false)
      setHasChanges(false)
    }
  }, [systemSettings])

  // Track form changes
  useEffect(() => {
    if (systemSettings) {
      const changesDetected =
        mqttEnabled !== (systemSettings.mqtt_enabled || false) ||
        mqttBrokerUrl !== (systemSettings.mqtt_broker_url || '') ||
        mqttBrokerPort !== (systemSettings.mqtt_broker_port || 1883) ||
        mqttUsername !== (systemSettings.mqtt_username || '') ||
        mqttClientId !== (systemSettings.mqtt_client_id || 'borg-ui') ||
        mqttQos !== (systemSettings.mqtt_qos || 1) ||
        mqttRetain !== (systemSettings.mqtt_retain || false) ||
        mqttTlsEnabled !== (systemSettings.mqtt_tls_enabled || false) ||
        mqttTlsCaCert !== (systemSettings.mqtt_tls_ca_cert || '') ||
        mqttTlsClientCert !== (systemSettings.mqtt_tls_client_cert || '') ||
        mqttTlsClientKey !== (systemSettings.mqtt_tls_client_key || '') ||
        passwordChanged

      setHasChanges(changesDetected)
    }
  }, [
    mqttEnabled,
    mqttBrokerUrl,
    mqttBrokerPort,
    mqttUsername,
    mqttClientId,
    mqttQos,
    mqttRetain,
    mqttTlsEnabled,
    mqttTlsCaCert,
    mqttTlsClientCert,
    mqttTlsClientKey,
    passwordChanged,
    systemSettings,
  ])

  // Save MQTT settings mutation
  const saveMqttSettingsMutation = useMutation({
    mutationFn: async () => {
      return await settingsAPI.updateSystemSettings({
        mqtt_enabled: mqttEnabled,
        mqtt_broker_url: mqttBrokerUrl || null,
        mqtt_broker_port: mqttBrokerPort,
        mqtt_username: mqttUsername || null,
        mqtt_password: passwordChanged ? mqttPassword : undefined,
        mqtt_client_id: mqttClientId,
        mqtt_qos: mqttQos,
        mqtt_retain: mqttRetain,
        mqtt_tls_enabled: mqttTlsEnabled,
        mqtt_tls_ca_cert: mqttTlsCaCert || null,
        mqtt_tls_client_cert: mqttTlsClientCert || null,
        mqtt_tls_client_key: mqttTlsClientKey || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      toast.success(t('mqttSettings.savedSuccessfully'))
      setHasChanges(false)
      setPasswordChanged(false)
      trackSystem(EventAction.EDIT, {
        section: 'mqtt',
        enabled: mqttEnabled,
        tls_enabled: mqttTlsEnabled,
        qos: mqttQos,
        retain: mqttRetain,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = t('mqtt.failedToSaveMqttSettings')
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = translateBackendKey(data.detail)
      }
      toast.error(errorMsg)
    },
  })

  const handleSaveSettings = () => {
    saveMqttSettingsMutation.mutate()
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMqttPassword(e.target.value)
    setPasswordChanged(true)
  }

  const togglePasswordVisibility = () => {
    setShowPassword(!showPassword)
  }

  const isSaving = saveMqttSettingsMutation.isPending

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
              {t('mqttSettings.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('mqtt.subtitle')}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={isSaving ? <CircularProgress size={16} /> : <Save size={16} />}
            onClick={handleSaveSettings}
            disabled={!hasChanges || isSaving}
          >
            {isSaving ? t('mqttSettings.saving') : t('mqttSettings.save')}
          </Button>
        </Box>

        {/* MQTT Connection Card */}
        <SettingsCard>
          <Stack spacing={3}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Wifi size={24} />
              <Typography variant="h6">{t('mqtt.connectionTitle')}</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {t('mqtt.connectionDescription')}
            </Typography>
            <Divider />

            <FormControlLabel
              sx={{ ml: -1 }}
              control={
                <Checkbox
                  checked={mqttEnabled}
                  onChange={(e) => setMqttEnabled(e.target.checked)}
                  color="primary"
                />
              }
              label={t('mqtt.enableMqttPublishing')}
            />

            {mqttEnabled && (
              <>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                    gap: 3,
                  }}
                >
                  <TextField
                    label={t('mqtt.brokerUrlLabel')}
                    placeholder={t('mqtt.brokerUrlPlaceholder')}
                    value={mqttBrokerUrl}
                    onChange={(e) => setMqttBrokerUrl(e.target.value)}
                    fullWidth
                    required
                    helperText={t('mqtt.brokerUrlHelper')}
                  />

                  <TextField
                    label={t('mqtt.brokerPortLabel')}
                    type="number"
                    value={mqttBrokerPort}
                    onChange={(e) => setMqttBrokerPort(Number(e.target.value))}
                    fullWidth
                    inputProps={{ min: 1, max: 65535, step: 1 }}
                    helperText={t('mqtt.brokerPortHelper')}
                  />

                  <TextField
                    label={t('mqtt.usernameLabel')}
                    placeholder={t('mqtt.usernamePlaceholder')}
                    value={mqttUsername}
                    onChange={(e) => setMqttUsername(e.target.value)}
                    fullWidth
                    helperText={t('mqtt.usernameHelper')}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <Key size={16} color="#666" />
                        </InputAdornment>
                      ),
                    }}
                  />

                  <TextField
                    label={t('mqtt.passwordLabel')}
                    type={showPassword ? 'text' : 'password'}
                    value={mqttPassword}
                    onChange={handlePasswordChange}
                    fullWidth
                    helperText={
                      systemSettings?.mqtt_password_set
                        ? t('mqtt.passwordIsSet')
                        : t('mqtt.passwordHelper')
                    }
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <Lock size={16} color="#666" />
                        </InputAdornment>
                      ),
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton onClick={togglePasswordVisibility} edge="end" size="small">
                            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />

                  <TextField
                    label={t('mqtt.clientIdLabel')}
                    value={mqttClientId}
                    onChange={(e) => setMqttClientId(e.target.value)}
                    fullWidth
                    helperText={t('mqtt.clientIdHelper')}
                  />

                  <TextField
                    label={t('mqtt.qosLevelLabel')}
                    type="number"
                    value={mqttQos}
                    onChange={(e) => setMqttQos(Math.min(Math.max(0, Number(e.target.value)), 2))}
                    fullWidth
                    inputProps={{ min: 0, max: 2, step: 1 }}
                    helperText={t('mqtt.qosLevelHelper')}
                  />
                </Box>

                <FormControlLabel
                  sx={{ ml: -1 }}
                  control={
                    <Checkbox
                      checked={mqttRetain}
                      onChange={(e) => setMqttRetain(e.target.checked)}
                      color="primary"
                    />
                  }
                  label={t('mqtt.retainMessages')}
                />
              </>
            )}
          </Stack>
        </SettingsCard>

        {/* TLS/SSL Card */}
        {mqttEnabled && (
          <SettingsCard>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Shield size={24} />
                <Typography variant="h6">{t('mqtt.tlsConfigTitle')}</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {t('mqtt.tlsConfigDescription')}
              </Typography>
              <Divider />

              <FormControlLabel
                sx={{ ml: -1 }}
                control={
                  <Checkbox
                    checked={mqttTlsEnabled}
                    onChange={(e) => setMqttTlsEnabled(e.target.checked)}
                    color="primary"
                  />
                }
                label={t('mqtt.enableTls')}
              />

              {mqttTlsEnabled && (
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr', gap: 3 }}>
                  <TextField
                    label={t('mqtt.caCertPathLabel')}
                    placeholder="/path/to/ca.crt"
                    value={mqttTlsCaCert}
                    onChange={(e) => setMqttTlsCaCert(e.target.value)}
                    fullWidth
                    helperText={t('mqtt.caCertPathHelper')}
                  />

                  <TextField
                    label={t('mqtt.clientCertPathLabel')}
                    placeholder="/path/to/client.crt"
                    value={mqttTlsClientCert}
                    onChange={(e) => setMqttTlsClientCert(e.target.value)}
                    fullWidth
                    helperText={t('mqtt.clientCertPathHelper')}
                  />

                  <TextField
                    label={t('mqtt.clientKeyPathLabel')}
                    placeholder="/path/to/client.key"
                    value={mqttTlsClientKey}
                    onChange={(e) => setMqttTlsClientKey(e.target.value)}
                    fullWidth
                    helperText={t('mqtt.clientKeyPathHelper')}
                  />

                  <Alert severity="info" icon={<AlertTriangle size={20} />}>
                    <strong>{t('mqtt.noteLabel')}</strong> {t('mqtt.dockerVolumesWarning')}
                  </Alert>
                </Box>
              )}
            </Stack>
          </SettingsCard>
        )}
      </Stack>
    </Box>
  )
}

export default MqttSettingsTab
