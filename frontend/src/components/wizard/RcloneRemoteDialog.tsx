import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Cloud, ExternalLink, Plus, RefreshCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import CodeEditor from '../CodeEditor'
import ResponsiveDialog from '../ResponsiveDialog'
import type { RcloneOAuthSession, RcloneProvider } from '../../services/api'
import { buildDownloadUrl } from '../../utils/downloadUrl'
import { translateBackendKey } from '../../utils/translateBackendKey'

export interface RcloneRemoteCreateInput {
  name: string
  provider: string
  config_source: 'managed'
  redacted_config: Record<string, unknown>
}

interface RcloneRemoteDialogProps {
  open: boolean
  mode?: 'create' | 'edit'
  initialRemote?: RcloneRemoteCreateInput | null
  isCreating?: boolean
  error?: string | null
  disablePortal?: boolean
  providers?: RcloneProvider[]
  onClose: () => void
  onCreate: (data: RcloneRemoteCreateInput) => Promise<void> | void
  onStartOAuth?: (data: {
    provider: string
    config: Record<string, unknown>
    mode?: 'auto' | 'borg_ui' | 'rclone_loopback'
  }) => Promise<RcloneOAuthSession>
  onGetOAuthSession?: (sessionId: string) => Promise<RcloneOAuthSession>
}

const DEFAULT_PROVIDERS: RcloneProvider[] = [
  {
    type: 'local',
    label: 'Local filesystem',
    description: 'Local path remote.',
    auth_type: 'none',
    type_editable: false,
    docs_url: 'https://rclone.org/local/',
    config_template: { type: 'local' },
    fields: [],
  },
  {
    type: 'custom',
    label: 'Custom rclone backend',
    description: 'Manual setup for any rclone backend.',
    auth_type: 'manual',
    type_editable: true,
    docs_url: 'https://rclone.org/docs/',
    config_template: { type: '' },
    fields: [],
  },
]

const parseConfig = (value: string, provider: string): Record<string, unknown> => {
  const trimmed = value.trim()
  if (!trimmed) return { type: provider }

  const parsed = JSON.parse(trimmed) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Config must be an object')
  }
  return parsed as Record<string, unknown>
}

const formatConfigJson = (value: Record<string, unknown> | null | undefined, provider: string) =>
  JSON.stringify(value && Object.keys(value).length ? value : { type: provider }, null, 2)

const formatProviderTemplate = (provider: RcloneProvider, customProvider = '') => {
  const template = { ...provider.config_template }
  template.type = provider.type_editable ? customProvider : provider.type
  return template
}

const browserAuthorizationUrl = (url: string | null | undefined) => {
  if (!url) return null
  return url.startsWith('/rclone/') ? buildDownloadUrl(url) : url
}

export default function RcloneRemoteDialog({
  open,
  mode = 'create',
  initialRemote = null,
  isCreating = false,
  error = null,
  disablePortal = false,
  providers = DEFAULT_PROVIDERS,
  onClose,
  onCreate,
  onStartOAuth,
  onGetOAuthSession,
}: RcloneRemoteDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [providerType, setProviderType] = useState('local')
  const [customProvider, setCustomProvider] = useState('')
  const [configJson, setConfigJson] = useState('{\n  "type": "local"\n}')
  const [localError, setLocalError] = useState<string | null>(null)
  const [oauthSession, setOauthSession] = useState<RcloneOAuthSession | null>(null)
  const [oauthError, setOauthError] = useState<string | null>(null)
  const [isStartingOAuth, setIsStartingOAuth] = useState(false)
  const [isCheckingOAuth, setIsCheckingOAuth] = useState(false)
  const [borgUiOAuthProvider, setBorgUiOAuthProvider] = useState<string | null>(null)
  const oauthRequestIdRef = useRef(0)
  const resolvedProviderRef = useRef('local')

  const providerOptions = providers.length ? providers : DEFAULT_PROVIDERS
  const selectedProvider =
    providerOptions.find((provider) => provider.type === providerType) ?? providerOptions[0]
  const resolvedProvider = selectedProvider.type_editable
    ? customProvider.trim()
    : selectedProvider.type
  const providerTypeLabel = selectedProvider.type_editable
    ? customProvider.trim() || t('wizard.location.rcloneCustomProviderPlaceholder')
    : selectedProvider.type
  const authLabel = t(`wizard.location.rcloneAuthTypes.${selectedProvider.auth_type}`, {
    defaultValue: selectedProvider.auth_type,
  })
  const selectedOAuthMode =
    selectedProvider.auth_type === 'oauth_token'
      ? selectedProvider.oauth_mode || 'rclone_loopback'
      : 'manual'
  const usesBorgUiOAuth = selectedOAuthMode === 'borg_ui'
  const borgUiOAuthConfigured = usesBorgUiOAuth && selectedProvider.oauth_configured === true
  const canStartPrimaryOAuth = !usesBorgUiOAuth || borgUiOAuthConfigured
  const callbackUrl = selectedProvider.oauth_callback_url || ''
  const setupMessage = selectedProvider.oauth_setup_key
    ? translateBackendKey(selectedProvider.oauth_setup_key)
    : t('wizard.location.rcloneOAuthSetupMissing')

  useEffect(() => {
    resolvedProviderRef.current = resolvedProvider
  }, [resolvedProvider])

  const resetOAuthState = useCallback(() => {
    oauthRequestIdRef.current += 1
    setOauthSession(null)
    setOauthError(null)
    setIsStartingOAuth(false)
    setIsCheckingOAuth(false)
    setBorgUiOAuthProvider(null)
  }, [])

  const isCurrentOAuthRequest = useCallback((requestId: number, provider: string) => {
    return requestId === oauthRequestIdRef.current && provider === resolvedProviderRef.current
  }, [])

  useEffect(() => {
    if (!open) return
    const nextProvider = initialRemote?.provider || 'local'
    const providerIsKnown = providerOptions.some((provider) => provider.type === nextProvider)
    const nextProviderType = providerIsKnown ? nextProvider : 'custom'
    setName(initialRemote?.name || '')
    setProviderType(nextProviderType)
    setCustomProvider(nextProviderType === 'custom' ? nextProvider : '')
    setConfigJson(formatConfigJson(initialRemote?.redacted_config, nextProvider))
    setLocalError(null)
    resetOAuthState()
  }, [initialRemote, open, providerOptions, resetOAuthState])

  useEffect(() => {
    if (open) return
    setName('')
    setProviderType('local')
    setCustomProvider('')
    setConfigJson('{\n  "type": "local"\n}')
    setLocalError(null)
    resetOAuthState()
  }, [open, resetOAuthState])

  const handleProviderTypeChange = (nextProviderType: string) => {
    const nextProvider =
      providerOptions.find((provider) => provider.type === nextProviderType) ?? providerOptions[0]
    setProviderType(nextProvider.type)
    resetOAuthState()
    if (nextProvider.type_editable) {
      setCustomProvider('')
    }
    if (mode === 'create') {
      setConfigJson(formatConfigJson(formatProviderTemplate(nextProvider), nextProvider.type))
    }
  }

  const openAuthorizationUrl = (url: string | null | undefined) => {
    const browserUrl = browserAuthorizationUrl(url)
    if (!browserUrl) return
    window.open(browserUrl, '_blank', 'noopener,noreferrer')
  }

  const applyOAuthConfig = (
    session: RcloneOAuthSession,
    requestProvider: string,
    requestId: number
  ) => {
    const sessionConfig = session.config
    if (
      session.status !== 'authorized' ||
      !sessionConfig ||
      session.provider !== requestProvider ||
      !isCurrentOAuthRequest(requestId, requestProvider)
    ) {
      return
    }
    const marker =
      typeof sessionConfig._borg_ui_oauth_provider === 'string'
        ? sessionConfig._borg_ui_oauth_provider
        : null
    const visibleSessionConfig = Object.fromEntries(
      Object.entries(sessionConfig).filter(([key]) => !key.startsWith('_borg_ui_oauth'))
    )
    if (marker === requestProvider) {
      setBorgUiOAuthProvider(marker)
    }
    setConfigJson((currentJson) => {
      let currentConfig: Record<string, unknown>
      try {
        currentConfig = parseConfig(currentJson, requestProvider)
      } catch {
        currentConfig = { type: requestProvider }
      }
      return formatConfigJson(
        {
          ...currentConfig,
          ...visibleSessionConfig,
          type: visibleSessionConfig.type || requestProvider,
        },
        requestProvider
      )
    })
  }

  const handleStartOAuth = async (modeOverride?: 'borg_ui' | 'rclone_loopback') => {
    if (!onStartOAuth || !resolvedProvider) return
    const requestProvider = resolvedProvider
    const requestMode =
      modeOverride ?? (usesBorgUiOAuth && borgUiOAuthConfigured ? 'borg_ui' : 'rclone_loopback')
    const requestId = (oauthRequestIdRef.current += 1)
    let currentConfig: Record<string, unknown>
    try {
      currentConfig = parseConfig(configJson, requestProvider)
    } catch {
      setLocalError(t('wizard.location.rcloneConfigInvalidJson'))
      return
    }
    setLocalError(null)
    setOauthError(null)
    setIsStartingOAuth(true)
    try {
      const session = await onStartOAuth({
        provider: requestProvider,
        config: currentConfig,
        mode: requestMode,
      })
      if (!isCurrentOAuthRequest(requestId, requestProvider)) return
      setOauthSession(session)
      applyOAuthConfig(session, requestProvider, requestId)
      openAuthorizationUrl(session.authorization_url)
    } catch {
      if (isCurrentOAuthRequest(requestId, requestProvider)) {
        setOauthError(t('wizard.location.rcloneOAuthFailed'))
      }
    } finally {
      if (isCurrentOAuthRequest(requestId, requestProvider)) {
        setIsStartingOAuth(false)
      }
    }
  }

  const handleCheckOAuth = async () => {
    if (!onGetOAuthSession || !oauthSession) return
    const requestProvider = oauthSession.provider
    const requestId = oauthRequestIdRef.current
    setOauthError(null)
    setIsCheckingOAuth(true)
    try {
      const session = await onGetOAuthSession(oauthSession.session_id)
      if (!isCurrentOAuthRequest(requestId, requestProvider)) return
      setOauthSession(session)
      applyOAuthConfig(session, requestProvider, requestId)
      if (session.status === 'failed') {
        setOauthError(session.error || t('wizard.location.rcloneOAuthFailed'))
      }
    } catch {
      if (isCurrentOAuthRequest(requestId, requestProvider)) {
        setOauthError(t('wizard.location.rcloneOAuthFailed'))
      }
    } finally {
      if (isCurrentOAuthRequest(requestId, requestProvider)) {
        setIsCheckingOAuth(false)
      }
    }
  }

  const oauthStatusMessage = (() => {
    if (oauthError) return oauthError
    if (!oauthSession) return null
    if (oauthSession.status === 'authorized') return t('wizard.location.rcloneOAuthAuthorized')
    if (oauthSession.status === 'failed') {
      return oauthSession.error || t('wizard.location.rcloneOAuthFailed')
    }
    if (oauthSession.status === 'starting') return t('wizard.location.rcloneOAuthStarting')
    return t('wizard.location.rcloneOAuthWaiting')
  })()

  const handleCustomProviderChange = (value: string) => {
    setCustomProvider(value)
    if (mode !== 'create' || !selectedProvider.type_editable) return
    try {
      const current = parseConfig(configJson, value.trim())
      if (!current.type || current.type === customProvider) {
        setConfigJson(formatConfigJson({ ...current, type: value.trim() }, value.trim()))
      }
    } catch {
      return
    }
  }

  const handleSubmit = async () => {
    const remoteName = name.trim()
    const remoteProvider = resolvedProvider
    if (!remoteName) {
      setLocalError(t('wizard.location.rcloneRemoteNameRequired'))
      return
    }
    if (!remoteProvider) {
      setLocalError(t('wizard.location.rcloneProviderRequired'))
      return
    }

    let redactedConfig: Record<string, unknown>
    try {
      redactedConfig = parseConfig(configJson, remoteProvider)
    } catch {
      setLocalError(t('wizard.location.rcloneConfigInvalidJson'))
      return
    }
    if (borgUiOAuthProvider === remoteProvider) {
      redactedConfig._borg_ui_oauth_provider = borgUiOAuthProvider
    }

    setLocalError(null)
    await onCreate({
      name: remoteName,
      provider: remoteProvider,
      config_source: 'managed',
      redacted_config: redactedConfig,
    })
  }

  const dialogActions = (
    <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
      <Button onClick={onClose} disabled={isCreating}>
        {t('common.buttons.cancel')}
      </Button>
      <Button
        variant="contained"
        onClick={handleSubmit}
        disabled={isCreating}
        startIcon={isCreating ? <CircularProgress size={16} color="inherit" /> : <Plus size={16} />}
      >
        {isCreating
          ? mode === 'edit'
            ? t('wizard.location.rcloneSavingRemote')
            : t('wizard.location.rcloneCreatingRemote')
          : mode === 'edit'
            ? t('wizard.location.rcloneSaveRemote')
            : t('wizard.location.rcloneCreateRemote')}
      </Button>
    </DialogActions>
  )

  return (
    <ResponsiveDialog
      open={open}
      onClose={isCreating ? undefined : () => onClose()}
      maxWidth="md"
      fullWidth
      disablePortal={disablePortal}
      footer={dialogActions}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Cloud size={18} />
        {mode === 'edit'
          ? t('wizard.location.rcloneEditRemoteTitle')
          : t('wizard.location.rcloneAddRemoteTitle')}
      </DialogTitle>
      <DialogContent sx={{ display: 'grid', gap: 2, pt: 1, pb: 0 }}>
        {(localError || error) && <Alert severity="error">{localError || error}</Alert>}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) minmax(180px, 0.7fr)' },
            gap: 2,
          }}
        >
          <TextField
            label={t('wizard.location.rcloneRemoteNameLabel')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            disabled={isCreating}
          />
          <TextField
            select
            label={t('wizard.location.rcloneProviderLabel')}
            value={providerType}
            onChange={(event) => handleProviderTypeChange(event.target.value)}
            required
            disabled={isCreating}
            sx={{
              '& .MuiSelect-select': {
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              },
            }}
          >
            {providerOptions.map((provider) => (
              <MenuItem key={provider.type} value={provider.type}>
                {provider.label}
              </MenuItem>
            ))}
          </TextField>
        </Box>

        {selectedProvider.type_editable ? (
          <TextField
            label={t('wizard.location.rcloneCustomProviderLabel')}
            value={customProvider}
            onChange={(event) => handleCustomProviderChange(event.target.value)}
            required
            disabled={isCreating}
            placeholder={t('wizard.location.rcloneCustomProviderPlaceholder')}
          />
        ) : null}

        <Box
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            p: 1.5,
            bgcolor: 'action.hover',
          }}
        >
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
            <Chip size="small" label={providerTypeLabel} />
            <Chip size="small" label={authLabel} variant="outlined" />
            {selectedProvider.auth_type === 'oauth_token' ? (
              <Chip
                size="small"
                variant={usesBorgUiOAuth ? 'filled' : 'outlined'}
                color={usesBorgUiOAuth && borgUiOAuthConfigured ? 'success' : 'default'}
                label={
                  usesBorgUiOAuth
                    ? t('wizard.location.rcloneOAuthModeBorgUi')
                    : t('wizard.location.rcloneOAuthModeLoopback')
                }
              />
            ) : null}
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
            {selectedProvider.description}
          </Typography>
          {selectedProvider.auth_type === 'oauth_token' ? (
            <Alert
              severity={
                oauthSession?.status === 'authorized' ? 'success' : oauthError ? 'error' : 'info'
              }
              sx={{ mt: 1.5 }}
            >
              <Stack spacing={1}>
                <Typography variant="body2">
                  {usesBorgUiOAuth
                    ? borgUiOAuthConfigured
                      ? t('wizard.location.rcloneOAuthBorgUiHelper')
                      : setupMessage
                    : t('wizard.location.rcloneOAuthLoopbackHelper')}
                </Typography>
                {usesBorgUiOAuth && callbackUrl ? (
                  <Typography
                    variant="caption"
                    sx={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}
                  >
                    {t('wizard.location.rcloneOAuthCallbackUrl', { url: callbackUrl })}
                  </Typography>
                ) : null}
                {oauthStatusMessage ? (
                  <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
                    {oauthStatusMessage}
                  </Typography>
                ) : null}
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  useFlexGap
                  flexWrap="wrap"
                >
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => handleStartOAuth()}
                    disabled={!onStartOAuth || isCreating || isStartingOAuth || !canStartPrimaryOAuth}
                    startIcon={
                      isStartingOAuth ? (
                        <CircularProgress size={14} color="inherit" />
                      ) : (
                        <ExternalLink size={14} />
                      )
                    }
                  >
                    {isStartingOAuth
                      ? t('wizard.location.rcloneOAuthStarting')
                      : usesBorgUiOAuth
                        ? t('wizard.location.rcloneOAuthStartBorgUi')
                        : t('wizard.location.rcloneOAuthStart')}
                  </Button>
                  {usesBorgUiOAuth ? (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => handleStartOAuth('rclone_loopback')}
                      disabled={!onStartOAuth || isCreating || isStartingOAuth}
                      startIcon={<ExternalLink size={14} />}
                    >
                      {t('wizard.location.rcloneOAuthUseLoopback')}
                    </Button>
                  ) : null}
                  {oauthSession?.authorization_url ? (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => openAuthorizationUrl(oauthSession.authorization_url)}
                      startIcon={<ExternalLink size={14} />}
                    >
                      {t('wizard.location.rcloneOAuthOpen')}
                    </Button>
                  ) : null}
                  {oauthSession &&
                  oauthSession.status !== 'authorized' &&
                  oauthSession.status !== 'failed' ? (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={handleCheckOAuth}
                      disabled={!onGetOAuthSession || isCheckingOAuth}
                      startIcon={
                        isCheckingOAuth ? (
                          <CircularProgress size={14} color="inherit" />
                        ) : (
                          <RefreshCcw size={14} />
                        )
                      }
                    >
                      {t('wizard.location.rcloneOAuthCheck')}
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            </Alert>
          ) : null}
          {selectedProvider.fields.length ? (
            <Box sx={{ mt: 1.5, display: 'grid', gap: 0.75 }}>
              {selectedProvider.fields.map((field) => (
                <Typography
                  key={field.name}
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', overflowWrap: 'anywhere' }}
                >
                  <strong>{field.label}</strong>
                  {field.required ? ` ${t('wizard.location.rcloneRequiredFieldSuffix')}` : ''}:
                  {field.helper ? ` ${field.helper}` : ` ${field.name}`}
                </Typography>
              ))}
            </Box>
          ) : null}
          {selectedProvider.docs_url ? (
            <Link
              href={selectedProvider.docs_url}
              target="_blank"
              rel="noreferrer"
              variant="caption"
              sx={{ display: 'inline-block', mt: 1 }}
            >
              {t('wizard.location.rcloneProviderDocs')}
            </Link>
          ) : null}
        </Box>

        <CodeEditor
          label={t('wizard.location.rcloneConfigJsonLabel')}
          value={configJson}
          onChange={setConfigJson}
          language="json"
          height="220px"
          helperText={t('wizard.location.rcloneConfigJsonHelper')}
        />
      </DialogContent>
    </ResponsiveDialog>
  )
}
