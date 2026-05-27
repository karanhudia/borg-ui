import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material'
import { Cloud, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

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
  onClose: () => void
  onCreate: (data: RcloneRemoteCreateInput) => Promise<void> | void
}

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

export default function RcloneRemoteDialog({
  open,
  mode = 'create',
  initialRemote = null,
  isCreating = false,
  error = null,
  disablePortal = false,
  onClose,
  onCreate,
}: RcloneRemoteDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [provider, setProvider] = useState('local')
  const [configJson, setConfigJson] = useState('{\n  "type": "local"\n}')
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const nextProvider = initialRemote?.provider || 'local'
    setName(initialRemote?.name || '')
    setProvider(nextProvider)
    setConfigJson(formatConfigJson(initialRemote?.redacted_config, nextProvider))
    setLocalError(null)
  }, [initialRemote, open])

  useEffect(() => {
    if (open) return
    setName('')
    setProvider('local')
    setConfigJson('{\n  "type": "local"\n}')
    setLocalError(null)
  }, [open])

  useEffect(() => {
    if (mode !== 'create') return
    try {
      const current = parseConfig(configJson, provider)
      if (!current.type || current.type === 'local') {
        setConfigJson(formatConfigJson({ ...current, type: provider }, provider))
      }
    } catch {
      return
    }
  }, [configJson, mode, provider])

  const handleSubmit = async () => {
    const remoteName = name.trim()
    const remoteProvider = provider.trim()
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

    setLocalError(null)
    await onCreate({
      name: remoteName,
      provider: remoteProvider,
      config_source: 'managed',
      redacted_config: redactedConfig,
    })
  }

  return (
    <Dialog
      open={open}
      onClose={isCreating ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      disablePortal={disablePortal}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Cloud size={18} />
        {mode === 'edit'
          ? t('wizard.location.rcloneEditRemoteTitle')
          : t('wizard.location.rcloneAddRemoteTitle')}
      </DialogTitle>
      <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
        {(localError || error) && <Alert severity="error">{localError || error}</Alert>}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) minmax(140px, 0.5fr)' },
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
            label={t('wizard.location.rcloneProviderLabel')}
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            required
            disabled={isCreating}
          />
        </Box>
        <TextField
          label={t('wizard.location.rcloneConfigJsonLabel')}
          value={configJson}
          onChange={(event) => setConfigJson(event.target.value)}
          multiline
          minRows={5}
          disabled={isCreating}
          helperText={t('wizard.location.rcloneConfigJsonHelper')}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={isCreating}>
          {t('common.buttons.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={isCreating}
          startIcon={
            isCreating ? <CircularProgress size={16} color="inherit" /> : <Plus size={16} />
          }
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
    </Dialog>
  )
}
