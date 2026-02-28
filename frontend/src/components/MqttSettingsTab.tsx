import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
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
import { toast } from 'react-hot-toast'
import { settingsAPI } from '../services/api'

const MqttSettingsTab: React.FC = () => {
  const queryClient = useQueryClient()

  // MQTT form state
  const [mqttEnabled, setMqttEnabled] = useState(false)
  const [mqttBrokerUrl, setMqttBrokerUrl] = useState('')
  const [mqttBrokerPort, setMqttBrokerPort] = useState(1883)
  const [mqttUsername, setMqttUsername] = useState('')
  const [mqttPassword, setMqttPassword] = useState('')
  const [mqttClientId, setMqttClientId] = useState('borg-ui')
  const [mqttQos, setMqttQos] = useState(1)
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
        mqtt_tls_enabled: mqttTlsEnabled,
        mqtt_tls_ca_cert: mqttTlsCaCert || null,
        mqtt_tls_client_cert: mqttTlsClientCert || null,
        mqtt_tls_client_key: mqttTlsClientKey || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      toast.success('MQTT settings saved successfully')
      setHasChanges(false)
      setPasswordChanged(false)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const data = error.response?.data
      let errorMsg = 'Failed to save MQTT settings'
      if (Array.isArray(data)) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        errorMsg = data.map((e: any) => e.msg).join(', ')
      } else if (data?.detail) {
        errorMsg = data.detail
      }
      throw new Error(errorMsg)
    },
  })

  const handleSaveSettings = async () => {
    try {
      await saveMqttSettingsMutation.mutateAsync()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.message || 'Failed to save MQTT settings')
    }
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
              MQTT Settings
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Configure MQTT broker connection for Home Assistant state publishing
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={isSaving ? <CircularProgress size={16} /> : <Save size={16} />}
            onClick={handleSaveSettings}
            disabled={!hasChanges || isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Settings'}
          </Button>
        </Box>

        {/* MQTT Connection Card */}
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Wifi size={24} />
                <Typography variant="h6">MQTT Connection</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Configure connection to your MQTT broker.
              </Typography>
              <Divider />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={mqttEnabled}
                    onChange={(e) => setMqttEnabled(e.target.checked)}
                    color="primary"
                  />
                }
                label="Enable MQTT Publishing"
              />

              {mqttEnabled && (
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                    gap: 3,
                  }}
                >
                  <TextField
                    label="Broker URL"
                    placeholder="broker.example.com or localhost"
                    value={mqttBrokerUrl}
                    onChange={(e) => setMqttBrokerUrl(e.target.value)}
                    fullWidth
                    required
                    helperText="MQTT broker hostname or IP address"
                  />

                  <TextField
                    label="Broker Port"
                    type="number"
                    value={mqttBrokerPort}
                    onChange={(e) => setMqttBrokerPort(Number(e.target.value))}
                    fullWidth
                    inputProps={{ min: 1, max: 65535, step: 1 }}
                    helperText="MQTT broker port (1883 for standard, 8883 for TLS)"
                  />

                  <TextField
                    label="Username"
                    placeholder="Optional username"
                    value={mqttUsername}
                    onChange={(e) => setMqttUsername(e.target.value)}
                    fullWidth
                    helperText="Optional MQTT username"
                    InputProps={
                      mqttUsername
                        ? {
                            startAdornment: (
                              <InputAdornment position="start">
                                <Key size={16} color="#666" />
                              </InputAdornment>
                            ),
                          }
                        : {}
                    }
                  />

                  <TextField
                    label="Password"
                    type={showPassword ? 'text' : 'password'}
                    value={mqttPassword}
                    onChange={handlePasswordChange}
                    fullWidth
                    helperText={
                      systemSettings?.mqtt_password_set
                        ? 'Password is set'
                        : 'Optional MQTT password'
                    }
                    InputProps={
                      mqttPassword || systemSettings?.mqtt_password_set
                        ? {
                            startAdornment: (
                              <InputAdornment position="start">
                                <Lock size={16} color="#666" />
                              </InputAdornment>
                            ),
                            endAdornment: (
                              <InputAdornment position="end">
                                <IconButton
                                  onClick={togglePasswordVisibility}
                                  edge="end"
                                  size="small"
                                >
                                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                </IconButton>
                              </InputAdornment>
                            ),
                          }
                        : {}
                    }
                  />

                  <TextField
                    label="Client ID"
                    value={mqttClientId}
                    onChange={(e) => setMqttClientId(e.target.value)}
                    fullWidth
                    helperText="MQTT client identifier"
                  />

                  <TextField
                    label="QoS Level"
                    type="number"
                    value={mqttQos}
                    onChange={(e) => setMqttQos(Math.min(Math.max(0, Number(e.target.value)), 2))}
                    fullWidth
                    inputProps={{ min: 0, max: 2, step: 1 }}
                    helperText="Quality of Service (0 = at most once, 1 = at least once, 2 = exactly once)"
                  />
                </Box>
              )}
            </Stack>
          </CardContent>
        </Card>

        {/* TLS/SSL Card */}
        {mqttEnabled && (
          <Card>
            <CardContent>
              <Stack spacing={3}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Shield size={24} />
                  <Typography variant="h6">TLS/SSL Configuration</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Configure TLS/SSL for secure MQTT connections. Required for encrypted MQTT
                  brokers.
                </Typography>
                <Divider />

                <FormControlLabel
                  control={
                    <Checkbox
                      checked={mqttTlsEnabled}
                      onChange={(e) => setMqttTlsEnabled(e.target.checked)}
                      color="primary"
                    />
                  }
                  label="Enable TLS/SSL"
                />

                {mqttTlsEnabled && (
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr', gap: 3 }}>
                    <TextField
                      label="CA Certificate Path"
                      placeholder="/path/to/ca.crt"
                      value={mqttTlsCaCert}
                      onChange={(e) => setMqttTlsCaCert(e.target.value)}
                      fullWidth
                      helperText="Path to CA certificate file (optional)"
                    />

                    <TextField
                      label="Client Certificate Path"
                      placeholder="/path/to/client.crt"
                      value={mqttTlsClientCert}
                      onChange={(e) => setMqttTlsClientCert(e.target.value)}
                      fullWidth
                      helperText="Path to client certificate file (optional)"
                    />

                    <TextField
                      label="Client Key Path"
                      placeholder="/path/to/client.key"
                      value={mqttTlsClientKey}
                      onChange={(e) => setMqttTlsClientKey(e.target.value)}
                      fullWidth
                      helperText="Path to client key file (optional)"
                    />

                    <Alert severity="info" icon={<AlertTriangle size={20} />}>
                      <strong>Note:</strong> Certificate paths are relative to the container's
                      filesystem. For Docker deployments, mount your certificates to a volume and
                      reference the container path (e.g., /certs/ca.crt).
                    </Alert>
                  </Box>
                )}
              </Stack>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  )
}

export default MqttSettingsTab
