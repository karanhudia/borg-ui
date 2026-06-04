import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  Collapse,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  CheckCircle,
  ChevronDown,
  Cloud,
  ExternalLink,
  Info,
  KeyRound,
  Pencil,
  Plus,
  RefreshCcw,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import CodeEditor from '../shared/CodeEditor'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import RcloneProviderIcon from '../shared/RcloneProviderIcon'
import type {
  RcloneOAuthCredentialUpdate,
  RcloneOAuthSession,
  RcloneOAuthTokenStatus,
  RcloneProvider,
} from '../../services/api'
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
  onSaveOAuthCredentials?: (
    provider: string,
    data: RcloneOAuthCredentialUpdate
  ) => Promise<unknown> | unknown
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

const OAUTH_AUTO_POLL_INTERVAL_MS = 750

const formatTokenExpiry = (expiresAt?: string | null) => {
  if (!expiresAt) return null
  const date = new Date(expiresAt)
  if (Number.isNaN(date.getTime())) return expiresAt
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
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
  onSaveOAuthCredentials,
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
  const [borgUiOAuthSessionId, setBorgUiOAuthSessionId] = useState<string | null>(null)
  const [oauthTokenStatus, setOauthTokenStatus] = useState<RcloneOAuthTokenStatus | null>(null)
  const [oauthClientId, setOauthClientId] = useState('')
  const [oauthClientSecret, setOauthClientSecret] = useState('')
  const [oauthCredentialsError, setOauthCredentialsError] = useState<string | null>(null)
  const [isSavingOAuthCredentials, setIsSavingOAuthCredentials] = useState(false)
  const [credentialsExpanded, setCredentialsExpanded] = useState(false)
  const oauthRequestIdRef = useRef(0)
  const resolvedProviderRef = useRef('local')
  const initializedRemoteKeyRef = useRef<string | null>(null)

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
  const bothOAuthCredsSaved = useMemo(
    () => !!selectedProvider.oauth_client_id_set && !!selectedProvider.oauth_client_secret_set,
    [selectedProvider.oauth_client_id_set, selectedProvider.oauth_client_secret_set]
  )
  const canClearOAuthCredentials =
    selectedProvider.oauth_credentials_source === 'database' &&
    (!!selectedProvider.oauth_client_id_set || !!selectedProvider.oauth_client_secret_set)

  useEffect(() => {
    setCredentialsExpanded(!bothOAuthCredsSaved)
  }, [bothOAuthCredsSaved, providerType])

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
    setBorgUiOAuthSessionId(null)
    setOauthTokenStatus(null)
  }, [])

  const resetOAuthCredentialForm = useCallback(() => {
    setOauthClientId('')
    setOauthClientSecret('')
    setOauthCredentialsError(null)
    setIsSavingOAuthCredentials(false)
  }, [])

  const isCurrentOAuthRequest = useCallback((requestId: number, provider: string) => {
    return requestId === oauthRequestIdRef.current && provider === resolvedProviderRef.current
  }, [])

  useEffect(() => {
    if (!open) return
    const initialRemoteKey = JSON.stringify({
      mode,
      name: initialRemote?.name || '',
      provider: initialRemote?.provider || '',
      redacted_config: initialRemote?.redacted_config || null,
    })
    if (initializedRemoteKeyRef.current === initialRemoteKey) return
    initializedRemoteKeyRef.current = initialRemoteKey

    const nextProvider = initialRemote?.provider || 'local'
    const providerIsKnown = providerOptions.some((provider) => provider.type === nextProvider)
    const nextProviderType = providerIsKnown ? nextProvider : 'custom'
    setName(initialRemote?.name || '')
    setProviderType(nextProviderType)
    setCustomProvider(nextProviderType === 'custom' ? nextProvider : '')
    setConfigJson(formatConfigJson(initialRemote?.redacted_config, nextProvider))
    setLocalError(null)
    resetOAuthState()
    resetOAuthCredentialForm()
  }, [initialRemote, mode, open, providerOptions, resetOAuthCredentialForm, resetOAuthState])

  useEffect(() => {
    if (open) return
    initializedRemoteKeyRef.current = null
    setName('')
    setProviderType('local')
    setCustomProvider('')
    setConfigJson('{\n  "type": "local"\n}')
    setLocalError(null)
    resetOAuthState()
    resetOAuthCredentialForm()
  }, [open, resetOAuthCredentialForm, resetOAuthState])

  const handleProviderTypeChange = (nextProviderType: string) => {
    const nextProvider =
      providerOptions.find((provider) => provider.type === nextProviderType) ?? providerOptions[0]
    setProviderType(nextProvider.type)
    resetOAuthState()
    resetOAuthCredentialForm()
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

  const applyOAuthConfig = useCallback(
    (session: RcloneOAuthSession, requestProvider: string, requestId: number) => {
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
      const sessionMarker =
        typeof sessionConfig._borg_ui_oauth_session_id === 'string'
          ? sessionConfig._borg_ui_oauth_session_id
          : null
      const isBorgUiSessionMarker = marker === requestProvider && !!sessionMarker
      const visibleSessionConfig = Object.fromEntries(
        Object.entries(sessionConfig).filter(([key]) => !key.startsWith('_borg_ui_oauth'))
      )
      if (isBorgUiSessionMarker) {
        setBorgUiOAuthProvider(marker)
        setBorgUiOAuthSessionId(sessionMarker)
        setOauthTokenStatus(session.token_status ?? null)
      } else {
        setBorgUiOAuthProvider(null)
        setBorgUiOAuthSessionId(null)
        setOauthTokenStatus(session.token_status ?? null)
      }
      setConfigJson((currentJson) => {
        let currentConfig: Record<string, unknown>
        try {
          currentConfig = parseConfig(currentJson, requestProvider)
        } catch {
          currentConfig = { type: requestProvider }
        }
        if (isBorgUiSessionMarker) {
          delete currentConfig.token
        }
        const nextConfig: Record<string, unknown> = {
          ...currentConfig,
          ...visibleSessionConfig,
          type: visibleSessionConfig.type || requestProvider,
        }
        if (isBorgUiSessionMarker) {
          delete nextConfig.token
        }
        return formatConfigJson(nextConfig, requestProvider)
      })
    },
    [isCurrentOAuthRequest]
  )

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
    setOauthSession(null)
    setBorgUiOAuthProvider(null)
    setBorgUiOAuthSessionId(null)
    setOauthTokenStatus(null)
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

  const handleCheckOAuth = useCallback(async () => {
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
  }, [applyOAuthConfig, isCurrentOAuthRequest, oauthSession, onGetOAuthSession, t])

  useEffect(() => {
    if (
      !open ||
      !oauthSession ||
      oauthSession.oauth_mode !== 'borg_ui' ||
      oauthSession.status !== 'awaiting_callback'
    ) {
      return
    }
    const timer = window.setTimeout(() => {
      void handleCheckOAuth()
    }, OAUTH_AUTO_POLL_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [handleCheckOAuth, oauthSession, open])

  const handleSaveOAuthCredentials = async () => {
    if (!onSaveOAuthCredentials || !resolvedProvider) return
    const clientId = oauthClientId.trim()
    const clientSecret = oauthClientSecret.trim()
    if (!clientId && !clientSecret) {
      setOauthCredentialsError(t('wizard.location.rcloneOAuthCredentialsRequired'))
      return
    }
    if (!clientId || !clientSecret) {
      setOauthCredentialsError(t('wizard.location.rcloneOAuthCredentialsRequired'))
      return
    }

    setOauthCredentialsError(null)
    setIsSavingOAuthCredentials(true)
    try {
      await onSaveOAuthCredentials(resolvedProvider, {
        client_id: clientId || null,
        client_secret: clientSecret || null,
      })
      setOauthClientSecret('')
    } catch {
      setOauthCredentialsError(t('wizard.location.rcloneOAuthCredentialsSaveFailed'))
    } finally {
      setIsSavingOAuthCredentials(false)
    }
  }

  const handleClearOAuthCredentials = async () => {
    if (!onSaveOAuthCredentials || !resolvedProvider) return
    setOauthCredentialsError(null)
    setIsSavingOAuthCredentials(true)
    try {
      await onSaveOAuthCredentials(resolvedProvider, {
        client_id: null,
        client_secret: null,
      })
      resetOAuthCredentialForm()
    } catch {
      setOauthCredentialsError(t('wizard.location.rcloneOAuthCredentialsSaveFailed'))
    } finally {
      setIsSavingOAuthCredentials(false)
    }
  }

  const oauthStatusMessage = (() => {
    if (oauthError) return oauthError
    if (!oauthSession) return null
    if (isCheckingOAuth) return t('wizard.location.rcloneOAuthChecking')
    if (oauthSession.status === 'authorized') {
      return borgUiOAuthProvider === oauthSession.provider && borgUiOAuthSessionId
        ? t('wizard.location.rcloneOAuthTokenReady')
        : t('wizard.location.rcloneOAuthAuthorized')
    }
    if (oauthSession.status === 'failed') {
      return oauthSession.error || t('wizard.location.rcloneOAuthFailed')
    }
    if (oauthSession.status === 'starting') return t('wizard.location.rcloneOAuthStarting')
    return t('wizard.location.rcloneOAuthWaiting')
  })()

  const oauthTokenStatusMessage = (() => {
    if (!oauthTokenStatus) return null
    const expiry = formatTokenExpiry(oauthTokenStatus.expires_at)
    const status = t(`wizard.location.rcloneOAuthTokenStatus.${oauthTokenStatus.status}`, {
      defaultValue: oauthTokenStatus.status,
    })
    if (expiry) {
      return t('wizard.location.rcloneOAuthTokenStatusWithExpiry', {
        status,
        expiresAt: expiry,
      })
    }
    return status
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
    if (borgUiOAuthProvider === remoteProvider && borgUiOAuthSessionId) {
      redactedConfig._borg_ui_oauth_provider = borgUiOAuthProvider
      redactedConfig._borg_ui_oauth_session_id = borgUiOAuthSessionId
      delete redactedConfig.token
    } else {
      delete redactedConfig._borg_ui_oauth_provider
      delete redactedConfig._borg_ui_oauth_session_id
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
      PaperProps={{
        sx: {
          borderRadius: 3,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          height: { xs: 'auto', md: 'min(720px, calc(100vh - 64px))' },
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Cloud size={18} />
        {mode === 'edit'
          ? t('wizard.location.rcloneEditRemoteTitle')
          : t('wizard.location.rcloneAddRemoteTitle')}
      </DialogTitle>
      <DialogContent
        sx={{
          p: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 2.25,
              px: 3,
              pt: 1.25,
              pb: 1,
            }}
          >
            {(localError || error) && <Alert severity="error">{localError || error}</Alert>}

            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) minmax(180px, 0.7fr)' },
                gap: 2,
                mt: 0.5,
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
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                      <RcloneProviderIcon provider={provider.type} size={28} iconSize={15} />
                      <Typography component="span" noWrap>
                        {provider.label}
                      </Typography>
                    </Box>
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
                borderRadius: 2,
                p: 2,
                display: 'grid',
                gap: 1.25,
              }}
            >
              <Stack direction="row" spacing={1.5} alignItems="flex-start">
                <RcloneProviderIcon provider={resolvedProvider || selectedProvider.type} />
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ lineHeight: 1.25 }}>
                    {providerTypeLabel}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {authLabel}
                    {selectedProvider.auth_type === 'oauth_token'
                      ? ` · ${
                          usesBorgUiOAuth
                            ? t('wizard.location.rcloneOAuthModeBorgUi')
                            : t('wizard.location.rcloneOAuthModeLoopback')
                        }`
                      : ''}
                  </Typography>
                </Box>
              </Stack>
              {selectedProvider.description ? (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ overflowWrap: 'anywhere' }}
                >
                  {selectedProvider.description}
                </Typography>
              ) : null}
              {selectedProvider.docs_url ? (
                <Link
                  href={selectedProvider.docs_url}
                  target="_blank"
                  rel="noreferrer"
                  variant="caption"
                  sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
                >
                  <ExternalLink size={12} />
                  {t('wizard.location.rcloneProviderDocs')}
                </Link>
              ) : null}
            </Box>

            {selectedProvider.auth_type === 'oauth_token' && usesBorgUiOAuth ? (
              <Box
                sx={{
                  border: '1px solid',
                  borderColor: bothOAuthCredsSaved ? 'success.light' : 'divider',
                  borderRadius: 2,
                  bgcolor: bothOAuthCredsSaved
                    ? (theme) =>
                        theme.palette.mode === 'dark'
                          ? 'rgba(46, 125, 50, 0.08)'
                          : 'rgba(46, 125, 50, 0.05)'
                    : 'background.paper',
                }}
              >
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={1}
                  sx={{ px: 2, py: 1.25, minHeight: 48 }}
                >
                  {bothOAuthCredsSaved ? (
                    <CheckCircle size={18} color="var(--mui-palette-success-main, #2e7d32)" />
                  ) : (
                    <KeyRound size={18} />
                  )}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle2" fontWeight={600}>
                      {t('wizard.location.rcloneOAuthCredentialsTitle')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                      {t('wizard.location.rcloneOAuthCredentialsScopeHint', {
                        provider: selectedProvider.label,
                      })}
                    </Typography>
                    {bothOAuthCredsSaved ? (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block' }}
                      >
                        {t(
                          `wizard.location.rcloneOAuthCredentialSources.${
                            selectedProvider.oauth_credentials_source || 'unset'
                          }`,
                          { defaultValue: selectedProvider.oauth_credentials_source || 'unset' }
                        )}
                      </Typography>
                    ) : null}
                  </Box>
                  {bothOAuthCredsSaved ? (
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => setCredentialsExpanded((prev) => !prev)}
                      startIcon={<Pencil size={14} />}
                    >
                      {t('wizard.location.rcloneOAuthEditCredentials')}
                    </Button>
                  ) : null}
                </Stack>
                <Collapse in={credentialsExpanded || !bothOAuthCredsSaved} unmountOnExit>
                  <Box
                    sx={{
                      px: 2,
                      pb: 2,
                      pt: 0.5,
                      borderTop: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Box
                      sx={{
                        mt: 1.5,
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) minmax(0, 1fr)' },
                        gap: 1.25,
                      }}
                    >
                      <TextField
                        label={t('wizard.location.rcloneOAuthClientIdLabel')}
                        value={oauthClientId}
                        onChange={(event) => setOauthClientId(event.target.value)}
                        disabled={isCreating || isSavingOAuthCredentials}
                        autoComplete="off"
                        size="small"
                      />
                      <TextField
                        label={t('wizard.location.rcloneOAuthClientSecretLabel')}
                        value={oauthClientSecret}
                        onChange={(event) => setOauthClientSecret(event.target.value)}
                        disabled={isCreating || isSavingOAuthCredentials}
                        autoComplete="new-password"
                        type="password"
                        size="small"
                      />
                    </Box>
                    {oauthCredentialsError ? (
                      <Alert severity="error" sx={{ mt: 1 }}>
                        {oauthCredentialsError}
                      </Alert>
                    ) : null}
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1}
                      alignItems={{ xs: 'stretch', sm: 'center' }}
                      sx={{ mt: 1.5 }}
                    >
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={handleSaveOAuthCredentials}
                        disabled={!onSaveOAuthCredentials || isCreating || isSavingOAuthCredentials}
                        startIcon={
                          isSavingOAuthCredentials ? (
                            <CircularProgress size={14} color="inherit" />
                          ) : (
                            <KeyRound size={14} />
                          )
                        }
                      >
                        {isSavingOAuthCredentials
                          ? t('wizard.location.rcloneOAuthCredentialsSaving')
                          : t('wizard.location.rcloneOAuthCredentialsSave')}
                      </Button>
                      {canClearOAuthCredentials ? (
                        <Button
                          size="small"
                          variant="text"
                          color="error"
                          onClick={handleClearOAuthCredentials}
                          disabled={
                            !onSaveOAuthCredentials || isCreating || isSavingOAuthCredentials
                          }
                          startIcon={<Trash2 size={14} />}
                        >
                          {t('wizard.location.rcloneOAuthCredentialsClear')}
                        </Button>
                      ) : null}
                    </Stack>
                  </Box>
                </Collapse>
              </Box>
            ) : null}

            {selectedProvider.auth_type === 'oauth_token' ? (
              <Box
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  p: 2,
                  display: 'grid',
                  gap: 1.5,
                }}
              >
                <Stack direction="row" alignItems="center" spacing={0.5}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    {t('wizard.location.rcloneConnectSectionTitle')}
                  </Typography>
                  <Tooltip
                    title={t('wizard.location.rcloneOAuthHelpTooltip')}
                    arrow
                    placement="top"
                    componentsProps={{
                      tooltip: { sx: { maxWidth: 320, whiteSpace: 'pre-line' } },
                    }}
                  >
                    <IconButton size="small" aria-label={t('wizard.location.rcloneOAuthHelpLabel')}>
                      <Info size={14} />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {usesBorgUiOAuth
                    ? borgUiOAuthConfigured
                      ? t('wizard.location.rcloneOAuthBorgUiHelper')
                      : setupMessage
                    : t('wizard.location.rcloneOAuthLoopbackHelper')}
                </Typography>

                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5}
                  useFlexGap
                  flexWrap="wrap"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Button
                    variant="contained"
                    onClick={() => handleStartOAuth()}
                    disabled={
                      !onStartOAuth || isCreating || isStartingOAuth || !canStartPrimaryOAuth
                    }
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
                    <Link
                      component="button"
                      type="button"
                      variant="body2"
                      onClick={() => handleStartOAuth('rclone_loopback')}
                      disabled={!onStartOAuth || isCreating || isStartingOAuth}
                      sx={{
                        background: 'none',
                        border: 'none',
                        p: 0,
                        cursor: 'pointer',
                        textAlign: 'left',
                        '&:disabled': { opacity: 0.5, cursor: 'not-allowed' },
                      }}
                    >
                      {t('wizard.location.rcloneOAuthUseLoopback')}
                    </Link>
                  ) : null}
                  {oauthSession?.authorization_url ? (
                    <Link
                      component="button"
                      type="button"
                      variant="body2"
                      onClick={() => openAuthorizationUrl(oauthSession.authorization_url)}
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 0.5,
                        background: 'none',
                        border: 'none',
                        p: 0,
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <ExternalLink size={13} />
                      {t('wizard.location.rcloneOAuthOpen')}
                    </Link>
                  ) : null}
                  {oauthSession &&
                  oauthSession.oauth_mode !== 'borg_ui' &&
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

                {usesBorgUiOAuth && callbackUrl ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}
                  >
                    {t('wizard.location.rcloneOAuthCallbackUrl', { url: callbackUrl })}
                  </Typography>
                ) : null}

                {(oauthStatusMessage || oauthTokenStatusMessage || oauthError) && (
                  <Alert
                    severity={
                      oauthSession?.status === 'authorized'
                        ? 'success'
                        : oauthError
                          ? 'error'
                          : 'info'
                    }
                    sx={{ py: 0.5 }}
                  >
                    <Stack spacing={0.25}>
                      {oauthStatusMessage ? (
                        <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
                          {oauthStatusMessage}
                        </Typography>
                      ) : null}
                      {oauthTokenStatusMessage ? (
                        <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
                          {oauthTokenStatusMessage}
                        </Typography>
                      ) : null}
                    </Stack>
                  </Alert>
                )}
              </Box>
            ) : null}

            <Accordion
              disableGutters
              elevation={0}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
                overflow: 'hidden',
                '&:before': { display: 'none' },
                '&.MuiAccordion-root': { borderRadius: 2 },
                '&.Mui-expanded': { margin: 0, borderRadius: 2 },
                '& .MuiAccordionSummary-root': {
                  borderRadius: 2,
                },
                '&.Mui-expanded .MuiAccordionSummary-root': {
                  borderBottomLeftRadius: 0,
                  borderBottomRightRadius: 0,
                },
                mb: 1,
              }}
            >
              <AccordionSummary
                expandIcon={<ChevronDown size={18} />}
                sx={{ px: 2, '& .MuiAccordionSummary-content': { my: 1.25 } }}
              >
                <Stack>
                  <Typography variant="subtitle2" fontWeight={600}>
                    {t('wizard.location.rcloneAdvancedTitle')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t('wizard.location.rcloneAdvancedHelper')}
                  </Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 2, pb: 2, pt: 0, display: 'grid', gap: 1.5 }}>
                {selectedProvider.fields.length ? (
                  <Box sx={{ display: 'grid', gap: 0.75 }}>
                    {selectedProvider.fields.map((field) => (
                      <Typography
                        key={field.name}
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', overflowWrap: 'anywhere' }}
                      >
                        <strong>{field.label}</strong>
                        {field.required ? ` ${t('wizard.location.rcloneRequiredFieldSuffix')}` : ''}
                        :{field.helper ? ` ${field.helper}` : ` ${field.name}`}
                      </Typography>
                    ))}
                  </Box>
                ) : null}
                <CodeEditor
                  label={t('wizard.location.rcloneConfigJsonLabel')}
                  value={configJson}
                  onChange={setConfigJson}
                  language="json"
                  height="220px"
                  helperText={t('wizard.location.rcloneConfigJsonHelper')}
                />
              </AccordionDetails>
            </Accordion>
          </Box>
        </Box>
      </DialogContent>
    </ResponsiveDialog>
  )
}
