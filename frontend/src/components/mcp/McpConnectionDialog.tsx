import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { McpConfig, McpConnection, McpLevel } from '../../services/api'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import McpLevelCards from './McpLevelCards'

export interface McpConnectionBody {
  name: string
  access_level: McpLevel
  skip_routine_confirmations: boolean
}

interface McpConnectionDialogProps {
  open: boolean
  mode: 'create' | 'edit'
  connection?: McpConnection
  config: McpConfig
  onClose: () => void
  /** Rejects with the backend error message to show. */
  onSubmit: (body: McpConnectionBody) => Promise<void>
}

export default function McpConnectionDialog({
  open,
  mode,
  connection,
  config,
  onClose,
  onSubmit,
}: McpConnectionDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [level, setLevel] = useState<McpLevel>('read')
  const [skip, setSkip] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setName(connection?.name ?? '')
    setLevel(connection?.access_level ?? 'read')
    setSkip(connection?.skip_routine_confirmations ?? false)
    setError(null)
  }, [open, connection])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        name: name.trim(),
        access_level: level,
        skip_routine_confirmations: level === 'full' && skip,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      footer={
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>{t('mcp.dialog.cancel')}</Button>
          <Button variant="contained" onClick={submit} disabled={!name.trim() || busy}>
            {mode === 'create' ? t('mcp.dialog.create') : t('mcp.dialog.save')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>
        {mode === 'create' ? t('mcp.dialog.createTitle') : t('mcp.dialog.editTitle')}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          <TextField
            label={t('mcp.dialog.name')}
            placeholder={t('mcp.dialog.namePlaceholder')}
            helperText={t('mcp.dialog.nameHelp')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            fullWidth
            slotProps={{ htmlInput: { maxLength: 100 } }}
          />
          <Stack spacing={1}>
            <Typography variant="subtitle2">{t('mcp.levels.groupLabel')}</Typography>
            <McpLevelCards
              value={level}
              onChange={setLevel}
              available={config.available_levels}
              cap={config.max_access_level}
            />
          </Stack>
          {level === 'full' && (
            <Stack spacing={0.5}>
              <FormControlLabel
                control={<Switch checked={skip} onChange={(e) => setSkip(e.target.checked)} />}
                label={t('mcp.dialog.skip')}
              />
              <Typography variant="body2" color="text.secondary">
                {t('mcp.dialog.skipHelp')}
              </Typography>
            </Stack>
          )}
          {error && (
            <Alert severity="error" role="alert">
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
